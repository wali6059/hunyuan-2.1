"""
Model worker for Hunyuan3D API server.
"""
import os
import time
import uuid
import base64
import trimesh
from io import BytesIO
from PIL import Image
import torch

# FIXED: Apply torchvision compatibility fix and set paths like original demo
import sys
sys.path.insert(0, './hy3dshape')
sys.path.insert(0, './hy3dpaint')

try:
    from torchvision_fix import apply_fix
    apply_fix()
except ImportError:
    print("Warning: torchvision_fix module not found, proceeding without compatibility fix")
except Exception as e:
    print(f"Warning: Failed to apply torchvision fix: {e}")

from hy3dshape import Hunyuan3DDiTFlowMatchingPipeline
from hy3dshape.rembg import BackgroundRemover
from hy3dshape.utils import logger
# Import texture pipeline - using relative import from root
import os
import sys

# Ensure we can import textureGenPipeline correctly
try:
    from textureGenPipeline import Hunyuan3DPaintPipeline, Hunyuan3DPaintConfig
except ImportError:
    # Try from hy3dpaint directory if root import fails
    sys.path.insert(0, os.path.join(os.getcwd(), 'hy3dpaint'))
    from textureGenPipeline import Hunyuan3DPaintPipeline, Hunyuan3DPaintConfig
# Import GLB conversion utilities - path already set above

try:
    from hy3dpaint.convert_utils import create_glb_with_pbr_materials
    HAS_GLB_UTILS = True
except ImportError:
    print("Warning: GLB conversion utils not found, using basic trimesh export")
    HAS_GLB_UTILS = False


def quick_convert_with_obj2gltf(obj_path: str, glb_path: str):
    """Convert OBJ to GLB with PBR materials if possible"""
    if HAS_GLB_UTILS:
        try:
            textures = {
                'albedo': obj_path.replace('.obj', '.jpg'),
                'metallic': obj_path.replace('.obj', '_metallic.jpg'),
                'roughness': obj_path.replace('.obj', '_roughness.jpg')
            }
            create_glb_with_pbr_materials(obj_path, textures, glb_path)
            return
        except Exception as e:
            print(f"Warning: PBR GLB conversion failed: {e}, using basic conversion")
    
    # Fallback to basic trimesh conversion
    import trimesh
    mesh = trimesh.load(obj_path)
    mesh.export(glb_path)


def load_image_from_base64(image):
    """
    Load an image from base64 encoded string.
    
    Args:
        image (str): Base64 encoded image string
        
    Returns:
        PIL.Image: Loaded image
    """
    if not isinstance(image, str):
        raise TypeError(f"Expected string, got {type(image)}")
    
    try:
        # Handle data URLs (e.g., "data:image/png;base64,...")
        if image.startswith('data:'):
            image = image.split(',')[1]
        
        return Image.open(BytesIO(base64.b64decode(image)))
    except Exception as e:
        raise ValueError(f"Failed to decode base64 image: {e}")


class ModelWorker:
    """
    Worker class for handling 3D model generation tasks.
    """
    
    def __init__(self,
                 model_path='tencent/Hunyuan3D-2.1',
                 subfolder='hunyuan3d-dit-v2-1',
                 device='cuda',
                 low_vram_mode=False,
                 worker_id=None,
                 model_semaphore=None,
                 save_dir='gradio_cache'):
        """
        Initialize the model worker.
        
        Args:
            model_path (str): Path to the shape generation model
            subfolder (str): Subfolder containing the model files
            device (str): Device to run the model on ('cuda' or 'cpu')
            low_vram_mode (bool): Whether to use low VRAM mode
            worker_id (str): Unique identifier for this worker
            model_semaphore: Semaphore for controlling model concurrency
            save_dir (str): Directory to save generated files
        """
        self.model_path = model_path
        self.worker_id = worker_id or str(uuid.uuid4())[:6]
        self.device = device
        self.low_vram_mode = low_vram_mode
        self.model_semaphore = model_semaphore
        self.save_dir = save_dir
        
        logger.info(f"Loading the model {model_path} on worker {self.worker_id} ...")

        # Initialize background remover
        self.rembg = BackgroundRemover()
        
        # Initialize shape generation pipeline (matching demo.py)
        self.pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(model_path)
        
        # Initialize texture generation pipeline (matching demo.py)
        max_num_view = 6  # can be 6 to 9
        resolution = 512  # can be 768 or 512
        conf = Hunyuan3DPaintConfig(max_num_view, resolution)
        # Use default paths from config - no need to override
        self.paint_pipeline = Hunyuan3DPaintPipeline(conf)
        # clean cache in save_dir (create directory if not exists)
        os.makedirs(self.save_dir, exist_ok=True)
        if os.path.exists(self.save_dir):
            for file in os.listdir(self.save_dir):
                file_path = os.path.join(self.save_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
            
    def get_queue_length(self):
        """
        Get the current queue length for model processing.
        
        Returns:
            int: Number of tasks in the queue
        """
        if self.model_semaphore is None:
            return 0
        else:
            return (self.model_semaphore._value if hasattr(self.model_semaphore, '_value') else 0) + \
                   (len(self.model_semaphore._waiters) if hasattr(self.model_semaphore, '_waiters') and self.model_semaphore._waiters is not None else 0)

    def get_status(self):
        """
        Get the current status of the worker.
        
        Returns:
            dict: Status information including speed and queue length
        """
        return {
            "speed": 1,
            "queue_length": self.get_queue_length(),
        }

    @torch.inference_mode()
    def generate(self, uid, params):
        """
        Generate a 3D model from the given parameters.
        
        Args:
            uid: Unique identifier for this generation task
            params (dict): Generation parameters including image and options
            
        Returns:
            tuple: (file_path, uid) - Path to generated file and task ID
        """
        start_time = time.time()
        logger.info(f"Generating 3D model for uid: {uid}")
        # Handle input image
        if 'image' in params:
            image = params["image"]
            image = load_image_from_base64(image)
        else:
            raise ValueError("No input image provided")

        # Remove background if needed (do this before RGBA conversion)
        if params.get('remove_background', True):
            image = self.rembg(image)
        
        # Convert to RGBA after background removal
        image = image.convert("RGBA")

        # Extract generation parameters with type enforcement
        seed = int(params.get('seed', 1234))
        octree_resolution = int(params.get('octree_resolution', 256))
        num_inference_steps = int(params.get('num_inference_steps', 5))
        guidance_scale = float(params.get('guidance_scale', 5.0))
        face_count = int(params.get('face_count', 40000))
        
        # Set random seed (seed is now guaranteed to be int)
        if seed is not None:
            import random
            import numpy as np
            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            np.random.seed(seed)
            random.seed(seed)

        # Generate mesh with parameters
        try:
            result = self.pipeline(
                image=image,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                octree_resolution=octree_resolution
            )
            
            # FIXED: Match original demo.py - simple [0] extraction like demo
            # Original: mesh = pipeline_shapegen(image=image)[0]
            mesh = result[0]
                
            logger.info("---Shape generation takes %s seconds ---" % (time.time() - start_time))
        except Exception as e:
            logger.error(f"Shape generation failed: {e}")
            raise ValueError(f"Failed to generate 3D mesh: {str(e)}")
        
        # Apply face reduction if needed (ensure mesh has faces attribute)
        if face_count and hasattr(mesh, 'faces') and len(mesh.faces) > face_count:
            logger.info(f"Reducing faces from {len(mesh.faces)} to {face_count}")
            # Use trimesh built-in simplification
            try:
                mesh = mesh.simplify_quadratic_decimation(face_count)
            except Exception as e:
                logger.warning(f"Face reduction failed: {e}, keeping original mesh")

        # Export initial mesh
        initial_save_path = os.path.join(self.save_dir, f'{str(uid)}_initial.glb')
        mesh.export(initial_save_path)
        
        # Check if texture generation is requested (default False to match api_models.py)
        generate_texture = bool(params.get('texture', False))
        
        if generate_texture:
            # Generate textured mesh as obj (as in demo)
            try:
                output_mesh_path_obj = os.path.join(self.save_dir, f'{str(uid)}_texturing.obj')
                textured_path_obj = self.paint_pipeline(
                    mesh_path=initial_save_path,
                    image_path=image,
                    output_mesh_path=output_mesh_path_obj,
                    save_glb=False            
                )
                logger.info("---Texture generation takes %s seconds ---" % (time.time() - start_time))
                logger.info(f"output_mesh_path: {output_mesh_path_obj} textured_path: {textured_path_obj}")

                # Convert textured OBJ to GLB using obj2gltf with PBR support
                print("convert textured OBJ to GLB")
                glb_path_textured = os.path.join(self.save_dir, f'{str(uid)}_texturing.glb')
                quick_convert_with_obj2gltf(textured_path_obj, glb_path_textured)
                # now rename glb_path to uid_textured.glb
                print("done.")
                final_save_path = os.path.join(self.save_dir, f'{str(uid)}_textured.glb')
                os.rename(glb_path_textured, final_save_path)
                print(f"final_save_path: {final_save_path}")
                
            except Exception as e:
                logger.error(f"Texture generation failed: {e}")
                # Fall back to untextured mesh if texture generation fails
                final_save_path = initial_save_path
                logger.warning(f"Using untextured mesh as fallback: {final_save_path}")
        else:
            # Use untextured mesh
            final_save_path = initial_save_path
            logger.info("Texture generation skipped by request")

        if self.low_vram_mode:
            torch.cuda.empty_cache()
            
        logger.info("---Total generation takes %s seconds ---" % (time.time() - start_time))
        return final_save_path, uid 