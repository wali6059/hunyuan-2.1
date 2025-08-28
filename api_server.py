# Hunyuan 3D is licensed under the TENCENT HUNYUAN NON-COMMERCIAL LICENSE AGREEMENT

import boto3
from botocore.config import Config
import base64
import os
import sys
import uuid
import runpod
from io import BytesIO

# Add the current directory to Python path for imports
sys.path.insert(0, '.')
sys.path.insert(0, './hy3dshape')
sys.path.insert(0, './hy3dpaint')

# Apply torchvision fix before other imports
try:
    from torchvision_fix import apply_fix
    apply_fix()
except ImportError:
    print("Warning: torchvision_fix module not found, proceeding without compatibility fix")
except Exception as e:
    print(f"Warning: Failed to apply torchvision fix: {e}")

from model_worker import ModelWorker, load_image_from_base64


def upload_to_r2(file_path, object_name):
    """
    Upload a file to Cloudflare R2 bucket and return a presigned download URL.
    """
    # Check if file exists before attempting upload
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Generated file not found: {file_path}")
        
    with open(file_path, 'rb') as file:
        s3.upload_fileobj(
            Fileobj=file,
            Bucket=bucket_name,
            Key=object_name,
            ExtraArgs={"ContentType": "model/gltf-binary"},
        )
    
    # Return a one-hour presigned URL
    url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": bucket_name, "Key": object_name},
        ExpiresIn=3600,
    )
    return url


def worker_fn(input_data):
    """Main Runpod serverless function for Hunyuan3D 2.1"""
    try:
        print(f"Worker input: {input_data}")
        
        # Get parameters with defaults (matching api_models.py structure exactly)
        image_base64 = input_data.get('image')  # str, required
        remove_background = bool(input_data.get('remove_background', True))  # bool, default True
        texture = bool(input_data.get('texture', False))  # bool, default False (matches api_models.py!)
        seed = int(input_data.get('seed', 1234))  # int, default 1234
        octree_resolution = int(input_data.get('octree_resolution', 256))  # int, default 256
        num_inference_steps = int(input_data.get('num_inference_steps', 5))  # int, default 5
        guidance_scale = float(input_data.get('guidance_scale', 5.0))  # float, default 5.0
        face_count = int(input_data.get('face_count', 40000))  # int, default 40000
        
        if not image_base64:
            return {"error": "No image provided"}

        # Create parameters dict matching model_worker expectations
        params = {
            'image': image_base64,
            'remove_background': remove_background,
            'texture': texture,
            'seed': seed,
            'octree_resolution': octree_resolution,
            'num_inference_steps': num_inference_steps,
            'guidance_scale': guidance_scale,
            'face_count': face_count
        }
        
        # Generate 3D model using ModelWorker
        uid = uuid.uuid4()
        file_path, generation_uid = worker.generate(uid, params)
        
        print(f"Generated file: {file_path}")
        
        # Upload to R2
        object_name = f"hunyuan3d-21-{uuid.uuid4().hex[:8]}.glb"
        download_url = upload_to_r2(file_path, object_name)
        
        print(f"File uploaded to R2: {download_url}")
        
        # Clean up local file
        if os.path.exists(file_path):
            os.remove(file_path)
        
        return {
            "download_url": download_url,
            "textured": texture,
            "seed": seed,
            "uid": str(generation_uid)
        }
        
    except Exception as e:
        error_msg = f"Generation failed: {str(e)}"
        print(f"ERROR: {error_msg}")
        import traceback
        traceback.print_exc()
        return {"error": error_msg}


def init_models():
    """Initialize Hunyuan3D 2.1 models using ModelWorker"""
    global worker
    
    print("Initializing Hunyuan3D 2.1 models...")
    
    # Initialize ModelWorker with the same parameters as the official repo
    worker = ModelWorker(
        model_path='tencent/Hunyuan3D-2.1',
        subfolder='hunyuan3d-dit-v2-1',
        device='cuda',
        low_vram_mode=False,
        worker_id=None,
        model_semaphore=None,
        save_dir='/tmp'
    )
    
    print("All models initialized successfully!")


if __name__ == "__main__":
    # Initialize R2 credentials
    account_id = os.getenv('CF_R2_ACCOUNT_ID', '')
    access_key_id = os.getenv('CF_R2_ACCESS_KEY', '')
    secret_access_key = os.getenv('CF_R2_SECRET_KEY', '')
    bucket_name = os.getenv('CF_R2_BUCKET', 'hunyuan3d')
    
    # Validate required environment variables
    if not all([account_id, access_key_id, secret_access_key]):
        print("ERROR: Missing required R2 credentials. Set CF_R2_ACCOUNT_ID, CF_R2_ACCESS_KEY, CF_R2_SECRET_KEY")
        sys.exit(1)

    # Initialize S3 client for R2
    s3 = boto3.client(
        's3',
        region_name='auto',
        endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=Config(signature_version='s3v4')
    )
    
    # Initialize models
    init_models()
    
    # Start Runpod serverless worker
    print("Starting Hunyuan3D 2.1 Runpod worker...")
    runpod.serverless.start({"handler": worker_fn})