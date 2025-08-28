# Hunyuan3D 2.1 - Runpod Serverless Container

🎨 **Production-ready 3D asset generation from 2D images**

This container deploys **Hunyuan3D 2.1** - the most advanced open-source AI model for generating high-fidelity 3D assets with **physically-based rendering (PBR) textures** from single images. Perfect for game development, 3D printing, AR/VR, and digital content creation.

## 🚀 What This Container Does

### **Core Capabilities**
- **📸 Image-to-3D Generation**: Transform any 2D image into a detailed 3D mesh
- **🎨 PBR Texture Synthesis**: Generate realistic materials with proper lighting, reflections, and surface properties
- **🔄 Background Removal**: Automatic subject isolation using AI segmentation
- **⚡ Fast Inference**: Optimized for serverless deployment with pre-compiled CUDA extensions
- **📱 Production Ready**: Handles edge cases, error recovery, and scalable cloud storage

### **Advanced Features**
- **Multi-view Consistency**: Generates coherent geometry from all viewing angles
- **Mesh Optimization**: Automatic cleanup, degeneracy removal, and face reduction
- **Material Properties**: Albedo, metallic, roughness, and normal maps for realistic rendering
- **Format Support**: Exports standard GLB files compatible with all 3D software

### **Model Specifications**
- **Shape Generation**: Hunyuan3D-Shape-v2-1 (3.3B parameters)
- **Texture Synthesis**: Hunyuan3D-Paint-v2-1 (2B parameters) with PBR pipeline
- **Memory Requirement**: 29GB VRAM (RTX 4090, A6000, H100, or equivalent)
- **Processing Time**: 30-90 seconds per generation (warm container)

## Quick Start

### 1. Build Docker Image

```bash
# Build with CUDA support
docker build -t hunyuan3d-21:latest .

# Push to registry (replace with your registry)
docker tag hunyuan3d-21:latest your-registry/hunyuan3d-21:latest
docker push your-registry/hunyuan3d-21:latest
```

### 2. Deploy on Runpod

1. Create new Runpod template with:
   - **Container Image**: `your-registry/hunyuan3d-21:latest`
   - **GPU**: RTX 4090 or A6000 (minimum 29GB VRAM)
   - **Container Registry Credentials**: If using private registry

2. Set environment variables:
   ```
   CLOUDFLARE_ACCOUNT_ID=your_account_id
   CLOUDFLARE_ACCESS_KEY_ID=your_access_key
   CLOUDFLARE_SECRET_ACCESS_KEY=your_secret_key
   CLOUDFLARE_BUCKET_NAME=hunyuan3d
   CLOUDFLARE_ACCOUNT_HASH=your_account_hash
   ```

3. Deploy as serverless endpoint

## 📡 API Reference

### **Endpoint**
```
POST /generate
```

### **Request Format**
Send a JSON payload with base64-encoded image:

```json
{
  "image": "base64_encoded_image_data",
  "remove_background": true,
  "texture": true,
  "seed": 1234,
  "octree_resolution": 256,
  "num_inference_steps": 5,
  "guidance_scale": 5.0,
  "face_count": 40000
}
```

### **Request Parameters**

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `image` | string | **required** | - | Base64-encoded input image (PNG/JPG/JPEG) |
| `remove_background` | boolean | `true` | - | Automatically remove image background |
| `texture` | boolean | `true` | - | Generate PBR textures (false = shape only) |
| `seed` | integer | `1234` | 0-4294967295 | Random seed for reproducible results |
| `octree_resolution` | integer | `256` | 64-512 | Mesh detail level (higher = more detail) |
| `num_inference_steps` | integer | `5` | 1-20 | Generation quality vs speed tradeoff |
| `guidance_scale` | float | `5.0` | 0.1-20.0 | How closely to follow the input image |
| `face_count` | integer | `40000` | 1000-100000 | Maximum mesh faces for texture generation |

### **Response Format**
```json
{
  "download_url": "https://pub-abc123.r2.dev/hunyuan3d-21-xyz789.glb",
  "vertices": 15420,
  "faces": 30840,
  "textured": true,
  "seed": 1234
}
```

### **Response Fields**

| Field | Type | Description |
|-------|------|-------------|
| `download_url` | string | Public URL to download the generated GLB file |
| `vertices` | integer | Number of vertices in the generated mesh |
| `faces` | integer | Number of triangular faces in the mesh |
| `textured` | boolean | Whether PBR textures were applied |
| `seed` | integer | Seed used for generation (for reproducibility) |

### **Error Response**
```json
{
  "error": "Description of what went wrong"
}
```

### **Example Request (Python)**
```python
import base64
import requests

# Encode image
with open("my_image.png", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

# Send request
response = requests.post("https://your-runpod-endpoint.com", json={
    "image": image_b64,
    "texture": True,
    "seed": 42
})

result = response.json()
print(f"Download: {result['download_url']}")
```

### **Example Request (cURL)**
```bash
# Encode image and send request
IMAGE_B64=$(base64 -i my_image.png)
curl -X POST "https://your-runpod-endpoint.com" \
  -H "Content-Type: application/json" \
  -d "{\"image\":\"$IMAGE_B64\",\"texture\":true}"
```

## 🏗️ Model Storage & Data Flow

### **Model Downloads**
Models are automatically downloaded on first container startup:

**Location**: `/app/weights/tencent/Hunyuan3D-2.1/`

**Models Downloaded**:
- `hunyuan3d-dit-v2-1/` - Shape generation model (~8GB)
- `hunyuan3d-paintpbr-v2-1/` - PBR texture model (~5GB) 
- `hunyuan3d-vae-v2-1/` - Variational autoencoder (~2GB)
- Additional utilities (background removal, etc.) (~3GB)

**Total Storage**: ~20GB models + ~15GB container = **35GB total**

### **Output Storage**
Generated 3D models are uploaded to **Cloudflare R2** storage:
- **Format**: GLB (standard 3D format)
- **Naming**: `hunyuan3d-21-{8-char-uuid}.glb`
- **Access**: Public URLs with instant global CDN distribution
- **Retention**: Configure based on your R2 bucket settings

### **Processing Pipeline**
1. 📥 **Input**: Base64 image received via API
2. 🔄 **Background Removal**: AI-powered subject isolation (optional)
3. 🧠 **Shape Generation**: 3.3B parameter model creates 3D geometry
4. ✂️ **Mesh Optimization**: Remove artifacts, reduce faces if needed
5. 🎨 **Texture Synthesis**: 2B parameter PBR model adds realistic materials
6. 📦 **Export**: GLB file with embedded textures
7. ☁️ **Upload**: Store in R2 with public download URL
8. 📤 **Response**: Return metadata and download link

## ⚡ Performance Metrics

| Operation | Time | Notes |
|-----------|------|-------|
| **Cold Start** | 2-3 minutes | Model download + loading |
| **Warm Container** | <5 seconds | Ready for inference |
| **Shape Only** | 15-30 seconds | Geometry generation |
| **Shape + PBR Texture** | 45-90 seconds | Full pipeline |
| **Background Removal** | +3-5 seconds | When enabled |
| **Mesh Optimization** | +2-5 seconds | Automatic cleanup |

**Concurrency**: Each container handles one request at a time for optimal GPU utilization

## 🔧 System Requirements

### **GPU Requirements**
| GPU Model | VRAM | Status |
|-----------|------|--------|
| RTX 4090 | 24GB | ❌ Insufficient |
| RTX 4090 (x2) | 48GB | ✅ Recommended |
| A6000 | 48GB | ✅ Recommended |
| H100 | 80GB | ✅ Optimal |
| A100 | 40GB/80GB | ✅ Production |

⚠️ **Note**: Despite documentation claiming 29GB requirement, actual memory usage often exceeds this. **48GB+ VRAM recommended** for reliable operation.

### **Infrastructure Requirements**
- **CUDA**: 12.1+ compatible drivers
- **Storage**: 35GB total (15GB container + 20GB models)
- **Network**: High bandwidth for model downloads (first run only)
- **Platform**: Runpod serverless GPU pods

### **Environment Variables**
```bash
# Required - Cloudflare R2 Storage
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_ACCESS_KEY_ID=your_access_key
CLOUDFLARE_SECRET_ACCESS_KEY=your_secret_key
CLOUDFLARE_BUCKET_NAME=hunyuan3d
CLOUDFLARE_ACCOUNT_HASH=your_account_hash

# Optional - Hugging Face (for private models)
HUGGINGFACE_TOKEN=hf_your_token_here
```

## 🏗️ Build Process

**Multi-stage Docker build** optimized for production:

1. **Builder Stage** (CUDA 12.4 devel):
   - Compiles CUDA extensions (`custom_rasterizer`, `differentiable_renderer`)
   - Builds Python wheels with GPU acceleration
   - Handles all compilation dependencies

2. **Runtime Stage** (CUDA 12.1 runtime):
   - Clean lightweight base image
   - Pre-compiled wheels installation via `uv`
   - Model download on first startup
   - Production-ready serverless handler

3. **Optimization Features**:
   - Pre-compiled CUDA kernels (no runtime compilation)
   - Fast Python package manager (`uv`)
   - Cached model storage
   - Minimal attack surface

## 🗂️ Project Structure

```
Hunyuan-2.1-Deploy/
├── 🐳 Dockerfile                    # Multi-stage optimized build
├── 🚀 api_server.py                 # Runpod serverless handler
├── 📥 download_script.py            # Automatic model downloader
├── ⚙️ pyproject.toml                # Package configuration
├── 📋 requirements.txt              # Development dependencies
├── 
├── 🧠 hy3dgen/                      # Core AI package
│   ├── __init__.py
│   ├── rembg.py                     # Background removal
│   ├── shapegen/                    # 3D shape generation
│   │   ├── __init__.py
│   │   ├── pipelines.py             # Shape generation pipeline
│   │   └── postprocessors.py        # Mesh optimization
│   └── texgen/                      # PBR texture synthesis  
│       ├── __init__.py
│       ├── pipelines.py             # Texture generation pipeline
│       ├── custom_rasterizer/       # CUDA-accelerated rasterizer
│       └── differentiable_renderer/ # Mesh rendering engine
│
├── 🛠️ scripts/                      # Deployment utilities
│   ├── build_wheels.sh              # CUDA compilation script
│   ├── deploy.sh                    # Automated deployment
│   └── test_api.py                  # API testing utility
│
├── 🔧 Configuration Files
│   ├── docker-compose.yml           # Local development
│   ├── .env.example                 # Environment template
│   └── .dockerignore                # Build optimization
│
└── 🎡 wheels/                       # Pre-compiled packages (generated)
    ├── custom_rasterizer_21-0.1.0-*.whl
    ├── differentiable_renderer_21-0.1.0-*.whl
    └── hunyuan3d_21-2.1.0-*.whl
```

## 🐛 Troubleshooting Guide

### **Memory Issues**
```bash
# Symptoms: CUDA OOM, container crashes
# Solutions:
- Use GPU with 48GB+ VRAM (not 29GB as documented)
- Reduce face_count: {"face_count": 20000}  
- Disable textures: {"texture": false}
- Lower resolution: {"octree_resolution": 128}
```

### **Model Loading Failures**
```bash
# Symptoms: Download errors, missing files
# Solutions:
- Check HuggingFace access (models are public)
- Verify disk space: 35GB+ required
- Check network connectivity
- Restart container to retry download
```

### **CUDA Compatibility**
```bash
# Symptoms: Import errors, runtime failures
# Solutions:
- Ensure CUDA 12.1+ drivers
- Check nvidia-docker installation
- Verify GPU compute capability
```

### **API Errors**
```bash
# Symptoms: 500 errors, timeout responses
# Solutions:
- Check Cloudflare R2 credentials
- Verify image encoding (base64)
- Reduce image size (<10MB recommended)
- Check container logs for details
```

## 📊 Cost Optimization

### **Runpod Pricing Estimates**
- **A6000 (48GB)**: ~$0.50-0.80/hour
- **H100 (80GB)**: ~$2.50-4.00/hour  
- **Per Generation**: $0.01-0.05 (30-90 seconds)

### **Cost Reduction Tips**
- Use **spot instances** for 50-70% savings
- **Shape-only mode** for faster/cheaper generation
- **Batch processing** multiple images
- **Auto-scaling** to zero when idle

## License

TENCENT HUNYUAN NON-COMMERCIAL LICENSE AGREEMENT

## Support

For issues and questions:
- GitHub Issues: [Hunyuan3D-2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1)
- Discord: [Hunyuan3D Community](https://discord.gg/dNBrdrGGMa)