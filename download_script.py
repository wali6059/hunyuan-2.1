from huggingface_hub import snapshot_download
import os

# Set base directory for model weights
base_dir = "weights/tencent/Hunyuan3D-2.1"
os.makedirs(base_dir, exist_ok=True)

print("Downloading Hunyuan3D 2.1 models...")

# Download shape generation model (3.3B parameters)
print("Downloading Hunyuan3D-Shape-v2-1...")
snapshot_download(
    repo_id="tencent/Hunyuan3D-2.1",
    allow_patterns=["hunyuan3d-dit-v2-1/*"],
    local_dir=base_dir,
)

# Download PBR texture generation model (2B parameters) 
print("Downloading Hunyuan3D-Paint-v2-1...")
snapshot_download(
    repo_id="tencent/Hunyuan3D-2.1",
    allow_patterns=["hunyuan3d-paintpbr-v2-1/*"],
    local_dir=base_dir,
)

# Download additional required models
print("Downloading additional models...")

# VAE for encoding/decoding
snapshot_download(
    repo_id="tencent/Hunyuan3D-2.1",
    allow_patterns=["hunyuan3d-vae-v2-1/*"],
    local_dir=base_dir,
)

# Delight model for image enhancement (if available)
try:
    snapshot_download(
        repo_id="tencent/Hunyuan3D-2.1", 
        allow_patterns=["hunyuan3d-delight-v2-1/*"],
        local_dir=base_dir,
    )
    print("Delight model downloaded")
except Exception as e:
    print(f"Delight model not available: {e}")

print("All models downloaded successfully!")
print(f"Models stored in: {os.path.abspath(base_dir)}")

# Verify downloads
for model_dir in ["hunyuan3d-dit-v2-1", "hunyuan3d-paintpbr-v2-1"]:
    model_path = os.path.join(base_dir, model_dir)
    if os.path.exists(model_path):
        files = os.listdir(model_path)
        print(f"{model_dir}: {len(files)} files")
    else:
        print(f"ERROR: {model_dir} not found!")