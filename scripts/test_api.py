#!/usr/bin/env python3
"""
Test script for Hunyuan3D 2.1 API deployment
"""
import base64
import json
import requests
import time
from pathlib import Path

def encode_image(image_path):
    """Encode image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def test_runpod_endpoint(endpoint_url, image_path, test_texture=True):
    """Test the Runpod serverless endpoint"""
    print(f"🧪 Testing Hunyuan3D 2.1 endpoint: {endpoint_url}")
    print(f"📸 Using image: {image_path}")
    
    # Encode image
    image_b64 = encode_image(image_path)
    
    # Prepare request
    payload = {
        "image": image_b64,
        "remove_background": True,
        "texture": test_texture,
        "seed": 1234,
        "octree_resolution": 256,
        "num_inference_steps": 5,
        "guidance_scale": 5.0,
        "face_count": 40000
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {RUNPOD_API_KEY}"  # Set this in environment
    }
    
    print("🚀 Sending request...")
    start_time = time.time()
    
    try:
        response = requests.post(endpoint_url, json=payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        end_time = time.time()
        
        print(f"✅ Request completed in {end_time - start_time:.1f} seconds")
        print(f"📊 Results:")
        print(f"   - Download URL: {result.get('download_url', 'N/A')}")
        print(f"   - Vertices: {result.get('vertices', 'N/A')}")
        print(f"   - Faces: {result.get('faces', 'N/A')}")
        print(f"   - Textured: {result.get('textured', 'N/A')}")
        print(f"   - Seed: {result.get('seed', 'N/A')}")
        
        if 'error' in result:
            print(f"❌ Error: {result['error']}")
            return False
            
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False

def test_local_docker(port=8080, image_path="test_image.png"):
    """Test local Docker container"""
    url = f"http://localhost:{port}/generate"
    print(f"🧪 Testing local Docker container: {url}")
    
    image_b64 = encode_image(image_path)
    
    payload = {
        "image": image_b64,
        "remove_background": True,
        "texture": False,  # Start with shape only for faster testing
        "seed": 1234,
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        # Save the GLB file
        with open("test_output.glb", "wb") as f:
            f.write(response.content)
            
        print("✅ Local test successful! Output saved as test_output.glb")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Local test failed: {e}")
        return False

if __name__ == "__main__":
    import sys
    import os
    
    # Configuration
    RUNPOD_API_KEY = os.getenv('RUNPOD_API_KEY')
    RUNPOD_ENDPOINT = os.getenv('RUNPOD_ENDPOINT')
    
    if len(sys.argv) < 2:
        print("Usage: python test_api.py <image_path> [endpoint_url]")
        print("Environment variables:")
        print("  RUNPOD_API_KEY - Your Runpod API key")
        print("  RUNPOD_ENDPOINT - Your Runpod endpoint URL")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    if not Path(image_path).exists():
        print(f"❌ Image not found: {image_path}")
        sys.exit(1)
    
    print("🎯 Hunyuan3D 2.1 API Test")
    print("=" * 50)
    
    # Test local Docker if running
    print("\n🔧 Testing local Docker container...")
    test_local_docker(image_path=image_path)
    
    # Test Runpod endpoint if configured
    if len(sys.argv) > 2 or RUNPOD_ENDPOINT:
        endpoint_url = sys.argv[2] if len(sys.argv) > 2 else RUNPOD_ENDPOINT
        print(f"\n☁️  Testing Runpod endpoint...")
        test_runpod_endpoint(endpoint_url, image_path)
    else:
        print("\n⚠️  Runpod endpoint not specified. Skipping cloud test.")
    
    print("\n✨ Testing complete!")