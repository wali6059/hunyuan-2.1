# Hunyuan3D 2.1 Deployment Pipeline Flow

## Overview
This document describes the complete flow of the Hunyuan3D 2.1 deployment pipeline for Runpod serverless deployment with Cloudflare R2 storage.

## Architecture Components

### Core Files
- **`api_server.py`** - Main Runpod worker entry point
- **`model_worker.py`** - 3D generation pipeline orchestrator  
- **`textureGenPipeline.py`** - Texture generation pipeline
- **`torchvision_fix.py`** - Compatibility fixes

### Model Modules
- **`hy3dshape/`** - Shape generation using DiT flow matching
- **`hy3dpaint/`** - Texture generation using multiview diffusion

### Support Files
- **`api_models.py`** - Pydantic request/response models
- **`constants.py`** - Application constants
- **`logger_utils.py`** - Logging utilities

## Complete Pipeline Flow

### 1. Request Reception (`api_server.py`)

```
Function: worker_fn(input_data)
├── Input validation (base64 image required)
├── Parameter extraction:
│   ├── image (base64 encoded)
│   ├── remove_background (default: True)
│   ├── texture (default: True)  
│   ├── seed (default: 1234)
│   ├── octree_resolution (default: 256)
│   ├── num_inference_steps (default: 5)
│   ├── guidance_scale (default: 5.0)
│   └── face_count (default: 40000)
└── Pass to ModelWorker.generate()
```

### 2. Model Initialization (`model_worker.py`)

```
Class: ModelWorker.__init__()
├── Initialize BackgroundRemover (hy3dshape.rembg.BackgroundRemover)
├── Initialize Shape Pipeline (hy3dshape.Hunyuan3DDiTFlowMatchingPipeline.from_pretrained)
└── Initialize Texture Pipeline (textureGenPipeline.Hunyuan3DPaintPipeline)
    ├── Config: Hunyuan3DPaintConfig(max_num_view=6, resolution=512)
    └── Dependencies:
        ├── MeshRender (hy3dpaint.DifferentiableRenderer.MeshRender)
        ├── ViewProcessor (hy3dpaint.utils.pipeline_utils.ViewProcessor)
        ├── imageSuperNet (hy3dpaint.utils.image_super_utils.imageSuperNet)
        └── multiviewDiffusionNet (hy3dpaint.utils.multiview_utils.multiviewDiffusionNet)
```

### 3. Generation Pipeline (`model_worker.py`)

```
Function: ModelWorker.generate(uid, params)
│
├── 3.1 Image Processing
│   ├── load_image_from_base64(params['image']) -> PIL.Image
│   ├── image.convert("RGBA")
│   └── [if remove_background] self.rembg(image) -> Background removed image
│
├── 3.2 Seed Setting (for reproducibility)
│   ├── torch.manual_seed(seed)
│   ├── torch.cuda.manual_seed_all(seed)
│   ├── np.random.seed(seed)
│   └── random.seed(seed)
│
├── 3.3 Shape Generation
│   ├── self.pipeline(
│   │   image=image,
│   │   num_inference_steps=num_inference_steps,  # 5
│   │   guidance_scale=guidance_scale,            # 5.0
│   │   octree_resolution=octree_resolution       # 256
│   │   ) -> trimesh.Trimesh mesh
│   └── [if face_count] mesh.simplify_quadratic_decimation(face_count)
│
├── 3.4 Export Initial Mesh
│   └── mesh.export(f"{uid}_initial.glb") -> GLB file
│
└── 3.5 Texture Generation [if texture=True]
    ├── self.paint_pipeline(
    │   mesh_path=initial_save_path,
    │   image_path=image,
    │   output_mesh_path=f"{uid}_texturing.obj",
    │   save_glb=False
    │   ) -> OBJ with textures
    ├── quick_convert_with_obj2gltf(obj_path, glb_path)
    │   └── create_glb_with_pbr_materials() -> GLB with PBR materials
    └── Return final GLB path
```

### 4. Texture Generation Detail (`textureGenPipeline.py`)

```
Class: Hunyuan3DPaintPipeline.__call__()
│
├── 4.1 Input Processing
│   ├── Load mesh: trimesh.load(processed_mesh_path)
│   └── UV wrap: mesh_uv_wrap(mesh)
│
├── 4.2 View Selection
│   ├── self.view_processor.bake_view_selection() -> camera positions
│   ├── render_normal_multiview() -> normal maps
│   └── render_position_multiview() -> position maps  
│
├── 4.3 Style Preparation
│   ├── Resize image to (512, 512)
│   └── Convert RGBA -> RGB with white background
│
├── 4.4 Multiview Generation
│   ├── self.models["multiview_model"](image_style, normal_maps + position_maps)
│   └── -> {"albedo": [...], "mr": [...]} multiview images
│
├── 4.5 Enhancement
│   ├── self.models["super_model"](albedo_images) -> Enhanced albedo
│   └── self.models["super_model"](mr_images) -> Enhanced metallic/roughness
│
├── 4.6 Texture Baking  
│   ├── self.view_processor.bake_from_multiview(enhanced_albedo) -> albedo texture
│   ├── self.view_processor.bake_from_multiview(enhanced_mr) -> mr texture
│   └── texture_inpaint() -> Fill holes in textures
│
└── 4.7 Mesh Export
    ├── self.render.set_texture(texture)
    ├── self.render.set_texture_mr(texture_mr)  
    └── self.render.save_mesh(output_path) -> Textured OBJ
```

### 5. Upload and Response (`api_server.py`)

```
Function: upload_to_r2(file_path, object_name)
├── Upload GLB file to Cloudflare R2 bucket
├── Generate presigned URL (1 hour expiry)
└── Return download URL

Function: worker_fn() [continued]
├── Generate unique object name: f"hunyuan3d-21-{uuid}.glb"
├── upload_to_r2(file_path, object_name) -> download_url
├── Clean up local file: os.remove(file_path)
└── Return response:
    {
        "download_url": "https://...",
        "textured": bool,
        "seed": int,
        "uid": str
    }
```

## Key Dependencies Flow

### Shape Generation (`hy3dshape/`)
```
hy3dshape/__init__.py
├── pipelines.Hunyuan3DDiTFlowMatchingPipeline
├── postprocessors.{FaceReducer, FloaterRemover, DegenerateFaceRemover}
└── preprocessors.ImageProcessorV2

pipelines.py -> Hunyuan3DDiTFlowMatchingPipeline.__call__()
├── models/autoencoders/ -> ShapeVAE, SurfaceExtractors  
├── models/denoisers/ -> Hunyuan3DDiT
├── models/diffusion/ -> FlowMatching, Transport
└── schedulers.py -> Timestep scheduling
```

### Texture Generation (`hy3dpaint/`)
```
textureGenPipeline.py -> Hunyuan3DPaintPipeline
├── DifferentiableRenderer/MeshRender.py -> 3D rendering
├── utils/multiview_utils.py -> Multiview diffusion
├── utils/image_super_utils.py -> Image enhancement  
├── utils/pipeline_utils.py -> ViewProcessor
├── custom_rasterizer/ -> CUDA rasterization (compiled)
└── hunyuanpaintpbr/ -> PBR pipeline, UNet
```

## Build Process (`Dockerfile`)

### Build Stage
1. **System Setup**: CUDA 12.4.1-devel, Python 3.10, build tools
2. **Python Environment**: uv venv, PyTorch with CUDA 12.1
3. **Dependencies**: Install all packages from requirements.txt
4. **CUDA Compilation**: Build custom_rasterizer CUDA extensions
5. **Model Download**: Download Hunyuan3D-2.1 models to /app/weights

### Runtime Stage  
1. **Minimal Base**: CUDA 12.4.1-runtime (no build tools)
2. **Copy Artifacts**: 
   - Python environment (.venv)
   - Models (weights/)
   - Source code (hy3dshape/, hy3dpaint/)
   - Entry point (api_server.py)
3. **Environment**: Set CUDA paths, Python paths

## Error Handling

### Common Error Points & Solutions
1. **Import Errors**: Fixed relative imports in textureGenPipeline.py
2. **CUDA Extensions**: Pre-compiled in build stage
3. **Model Loading**: Models downloaded during build, cached
4. **Memory Issues**: Low VRAM mode available, cleanup after generation
5. **File Path Issues**: All paths relative to /app working directory

## Environment Variables Required

```bash
CF_R2_ACCOUNT_ID=your_account_id
CF_R2_ACCESS_KEY=your_access_key  
CF_R2_SECRET_KEY=your_secret_key
CF_R2_BUCKET=hunyuan3d
```

## Input/Output Contract

### Input (JSON)
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

### Output (JSON)
```json
{
  "download_url": "https://pub-xxx.r2.dev/hunyuan3d-21-xxx.glb",
  "textured": true,
  "seed": 1234,
  "uid": "generated-uuid"
}
```

### Error Response
```json
{
  "error": "Error message describing what went wrong"
}
```

## Performance Characteristics
- **Shape Generation**: ~30-60 seconds (depends on octree_resolution)
- **Texture Generation**: ~60-120 seconds (depends on resolution, views)  
- **Memory Usage**: ~6-8GB VRAM peak
- **Output Size**: 5-50MB GLB files (depends on complexity)

## Deployment Commands

```bash
# Build
docker build --platform linux/amd64 -t blobit2025/hunyuan-2.1:latest .

# Push  
docker push blobit2025/hunyuan-2.1:latest

# Deploy on Runpod with environment variables
```