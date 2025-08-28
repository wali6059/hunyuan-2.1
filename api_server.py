# Hunyuan 3D is licensed under the TENCENT HUNYUAN NON-COMMERCIAL LICENSE AGREEMENT
# except for the third-party components listed below.
# Hunyuan 3D does not impose any additional limitations beyond what is outlined
# in the repsective licenses of these third-party components.
# Users must comply with all terms and conditions of original licenses of these third-party
# components and must ensure that the usage of the third party components adheres to
# all relevant laws and regulations.

import boto3
from botocore.config import Config
import asyncio
import base64
import logging
import logging.handlers
import os
import sys
import threading
import traceback
import uuid
from io import BytesIO
import runpod

import torch
import trimesh
from PIL import Image

from hy3dgen.rembg import BackgroundRemover
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline, FloaterRemover, DegenerateFaceRemover, FaceReducer
from hy3dgen.texgen import Hunyuan3DPaintPipeline
from hy3dgen.texgen.pipelines import Hunyuan3DPaintConfig
import requests
from huggingface_hub import snapshot_download

def upload_to_r2(file_like, object_name):
    """
    Upload an in‑memory buffer to a Cloudflare R2 bucket and
    return a presigned download URL (compatible with Hunyuan 2.0).
    """

    # ---- upload ---------------------------------------------------------
    # file_like is a BytesIO already at position 0
    s3.upload_fileobj(
        Fileobj=file_like,
        Bucket=bucket_name,
        Key=object_name,
        ExtraArgs={"ContentType": "model/gltf-binary"},
    )
    
    # ---- return a one‑hour presigned URL -------------------------------
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
        
        # Get parameters with defaults
        image_base64 = input_data.get('image')
        remove_bg = input_data.get('remove_background', True)
        generate_texture = input_data.get('texture', True)
        seed = input_data.get('seed', 1234)
        octree_resolution = input_data.get('octree_resolution', 256)
        num_inference_steps = input_data.get('num_inference_steps', 5)
        guidance_scale = input_data.get('guidance_scale', 5.0)
        face_count = input_data.get('face_count', 40000)
        
        if not image_base64:
            return {"error": "No image provided"}

        # Decode image
        try:
            image_bytes = base64.b64decode(image_base64)
            image = Image.open(BytesIO(image_bytes)).convert('RGB')
            print(f"Input image size: {image.size}")
        except Exception as e:
            return {"error": f"Failed to decode image: {str(e)}"}

        # Background removal
        if remove_bg:
            print("Removing background...")
            image = bg_remover(image)
            print("Background removed")

        # Generate shape
        print("Generating 3D shape...")
        torch.manual_seed(seed)
        
        mesh_untextured = shape_pipeline(
            image=image,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            octree_resolution=octree_resolution,
        )[0]
        
        print(f"Shape generated. Vertices: {len(mesh_untextured.vertices)}, Faces: {len(mesh_untextured.faces)}")

        # Post-process mesh
        print("Post-processing mesh...")
        mesh_untextured = floater_remover(mesh_untextured)
        mesh_untextured = degenerate_remover(mesh_untextured)
        
        if len(mesh_untextured.faces) > face_count:
            print(f"Reducing faces from {len(mesh_untextured.faces)} to {face_count}")
            mesh_untextured = face_reducer(mesh_untextured, face_count)

        final_mesh = mesh_untextured

        # Generate texture if requested
        if generate_texture:
            print("Generating PBR texture...")
            try:
                final_mesh = paint_pipeline(
                    mesh_untextured, 
                    image_path=image,
                    max_num_view=6,
                    resolution=512
                )
                print("PBR texture generated")
            except Exception as e:
                print(f"Texture generation failed: {str(e)}")
                print("Returning untextured mesh")

        # Export mesh
        print("Exporting mesh...")
        buffer = BytesIO()
        final_mesh.export(buffer, file_type='glb')
        buffer.seek(0)

        # Upload to R2
        object_name = f"hunyuan3d-21-{uuid.uuid4().hex[:8]}.glb"
        download_url = upload_to_r2(buffer, object_name)
        
        print(f"Mesh uploaded successfully: {download_url}")
        
        return {
            "download_url": download_url,
            "vertices": len(final_mesh.vertices),
            "faces": len(final_mesh.faces),
            "textured": generate_texture,
            "seed": seed
        }
        
    except Exception as e:
        error_msg = f"Generation failed: {str(e)}"
        print(f"ERROR: {error_msg}")
        traceback.print_exc()
        return {"error": error_msg}


def init_models():
    """Initialize Hunyuan3D 2.1 models"""
    global shape_pipeline, paint_pipeline, bg_remover
    global floater_remover, degenerate_remover, face_reducer
    
    print("Initializing Hunyuan3D 2.1 models...")
    
    # Download models if needed
    model_path = "/app/weights"
    if not os.path.exists(f"{model_path}/tencent/Hunyuan3D-2.1"):
        print("Downloading Hunyuan3D 2.1 models...")
        os.system("python download_script.py")
    
    # Initialize background remover
    bg_remover = BackgroundRemover()
    print("Background remover initialized")
    
    # Initialize shape pipeline
    shape_pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        'tencent/Hunyuan3D-2.1',
        subfolder='hunyuan3d-dit-v2-1',
        torch_dtype=torch.float16,
        cache_dir=model_path
    )
    print("Shape pipeline initialized")
    
    # Initialize texture pipeline
    paint_config = Hunyuan3DPaintConfig(
        max_num_view=6,
        resolution=512
    )
    paint_pipeline = Hunyuan3DPaintPipeline(
        paint_config,
        model_path='tencent/Hunyuan3D-2.1',
        subfolder='hunyuan3d-paintpbr-v2-1',
        torch_dtype=torch.float16,
        cache_dir=model_path
    )
    print("Paint pipeline initialized")
    
    # Initialize postprocessors
    floater_remover = FloaterRemover()
    degenerate_remover = DegenerateFaceRemover()
    face_reducer = FaceReducer()
    print("Postprocessors initialized")
    
    print("All models initialized successfully!")


if __name__ == "__main__":
    # Initialize R2 credentials (compatible with Hunyuan 2.0 format)
    account_id = os.getenv('CF_R2_ACCOUNT_ID', '')
    access_key_id = os.getenv('CF_R2_ACCESS_KEY', '')
    secret_access_key = os.getenv('CF_R2_SECRET_KEY', '')
    bucket_name = os.getenv('CF_R2_BUCKET', 'hunyuan3d')

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