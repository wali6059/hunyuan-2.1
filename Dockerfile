# =============================================================================
# WHEEL BUILDING STAGE - Pre-compile CUDA extensions into wheels
# =============================================================================
FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-devel AS wheel-builder

# Install build essentials for wheel compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build pkg-config gcc g++ \
    git wget curl ca-certificates \
    && apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/*

# Environment for CUDA compilation
ENV TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0" \
    FORCE_CUDA=1

# Install wheel building tools
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uv pip install --system wheel setuptools pybind11[global] ninja packaging cmake

# Copy only the CUDA extension source code
WORKDIR /app
COPY hy3dpaint/custom_rasterizer/ ./hy3dpaint/custom_rasterizer/
COPY hy3dpaint/DifferentiableRenderer/ ./hy3dpaint/DifferentiableRenderer/

# Build wheels for custom_rasterizer
RUN cd hy3dpaint/custom_rasterizer && \
    MAX_JOBS=4 python setup.py bdist_wheel && \
    mkdir -p /wheels && \
    cp dist/*.whl /wheels/

# Build wheel for DifferentiableRenderer (C++ pybind11 extension)
RUN cd hy3dpaint/DifferentiableRenderer && \
    bash compile_mesh_painter.sh && \
    python -c "
from setuptools import setup, Extension
import pybind11

ext = Extension(
    'mesh_inpaint_processor',
    ['mesh_inpaint_processor.cpp'],
    include_dirs=[pybind11.get_include()],
    language='c++',
    extra_compile_args=['-O3', '-std=c++11', '-fPIC'],
)

setup(
    name='differentiable_renderer',
    ext_modules=[ext],
    version='0.1.0',
    zip_safe=False,
)
" > setup.py && \
    python setup.py bdist_wheel && \
    cp dist/*.whl /wheels/ && \
    echo "Built wheels: $(ls /wheels/)"

# =============================================================================
# BUILD STAGE - Using pre-built PyTorch base for fast deployment
# =============================================================================
FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-devel AS builder

# Layer 1: Essential build tools (PyTorch already included in base)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build pkg-config gcc g++ \
    git wget curl unzip ca-certificates \
    libgl1-mesa-dev libglu1-mesa-dev libegl1-mesa-dev \
    libglib2.0-0 libsm6 libxrender1 libxext6 libfreetype6-dev \
    && apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/*

# Layer 2: Environment and UV installer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0" \
    FORCE_CUDA=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

# Layer 3: Create virtual environment
RUN uv venv
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/.venv/lib/python3.11/site-packages:/app"

# Layer 4: Core ML dependencies (stable layer)
RUN uv pip install \
    transformers==4.46.0 diffusers==0.30.0 accelerate==1.1.1 \
    huggingface-hub==0.30.2 safetensors==0.4.4 einops==0.8.0

# Layer 8: Build tools and computation libraries (stable)
RUN uv pip install \
    wheel setuptools pybind11[global] ninja packaging cmake \
    numpy==1.24.4 scipy==1.14.1

# Layer 9: Computer vision and mesh processing (stable)
RUN uv pip install \
    opencv-python==4.10.0.84 imageio==2.36.0 scikit-image==0.24.0 \
    trimesh==4.4.7 pygltflib==1.16.3

# Layer 10: Specialized ML packages (medium stability)
RUN uv pip install \
    rembg==2.0.65 onnxruntime-gpu xatlas==0.0.9

# Layer 11: Configuration and utility packages (stable)
RUN uv pip install \
    omegaconf==2.3.0 pyyaml==6.0.2 tqdm==4.66.5 psutil==6.0.0

# Layer 12: API and cloud packages (stable)
RUN uv pip install \
    fastapi==0.115.12 uvicorn==0.34.3 pydantic==2.10.6 \
    boto3 runpod requests Pillow

# Layer 13: Optional packages (separate layer for failure tolerance)
RUN uv pip install pymeshlab==2022.2.post3 realesrgan==0.3.0 \
    basicsr==1.4.2 open3d==0.18.0 torchmetrics==1.6.0 timm torchdiffeq \
    || echo "Some optional packages failed"

# Layer 14: Application source code (changes most frequently)
COPY hy3dshape/ ./hy3dshape/
COPY hy3dpaint/ ./hy3dpaint/
COPY api_server.py model_worker.py textureGenPipeline.py torchvision_fix.py ./
COPY api_models.py constants.py logger_utils.py ./

# Layer 15: Install pre-built wheels (fast installation)
COPY --from=wheel-builder /wheels /app/wheels
RUN uv pip install /app/wheels/*.whl --no-deps --force-reinstall && \
    echo "Installed wheels: $(ls /app/wheels/)"

# SKIP MODEL DOWNLOAD - Load at runtime for faster deployment (~22GB saved)
# Models will be downloaded on first run and cached in Runpod storage

# =============================================================================
# RUNTIME STAGE - Optimized for fast extraction on Runpod
# =============================================================================
FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime AS runtime

# Runtime Layer 1: Essential runtime libraries (PyTorch already included)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglu1-mesa libegl1 ca-certificates \
    libglib2.0-0 libsm6 libxrender1 libxext6 libfreetype6 \
    && apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/*

# Runtime Layer 2: Environment (tiny layer)  
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/opt/conda/lib/python3.11/site-packages:/app" \
    PYOPENGL_PLATFORM=egl \
    CUDA_VISIBLE_DEVICES=0

WORKDIR /app

# Runtime Layer 3: Python dependencies (using conda from base)
COPY --from=builder /app/.venv/lib/python3.11/site-packages /opt/conda/lib/python3.11/site-packages

# Runtime Layer 3.5: Copy wheels to host for extraction
COPY --from=wheel-builder /wheels /wheels

# Create script to extract wheels to host
RUN echo '#!/bin/bash\n\
echo "Extracting wheels to host..."\n\
mkdir -p /host/wheels 2>/dev/null || true\n\
cp -v /wheels/*.whl /host/wheels/ 2>/dev/null || echo "Note: Mount /host to extract wheels"\n\
echo "Wheels available at: $(ls /wheels/)"\n\
' > /extract_wheels.sh && chmod +x /extract_wheels.sh

# Runtime Layer 4: Core modules (medium size, stable)
COPY --from=builder /app/hy3dshape /app/hy3dshape
COPY --from=builder /app/hy3dpaint /app/hy3dpaint

# Runtime Layer 5: Application files (small, changes most frequently)
COPY --from=builder /app/api_server.py /app/model_worker.py /app/textureGenPipeline.py /app/
COPY --from=builder /app/torchvision_fix.py /app/api_models.py /app/constants.py /app/logger_utils.py /app/

# Runtime Layer 6: Runtime setup (tiny layer)
RUN mkdir -p /tmp /app/weights && chmod 777 /tmp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=2 \
    CMD python -c "import torch; assert torch.cuda.is_available()" || exit 1

EXPOSE 8080
CMD ["python", "api_server.py"]

# =============================================================================
# WHEELS EXTRACTION STAGE - For saving wheels to host during build
# =============================================================================
FROM scratch AS wheels-export
COPY --from=wheel-builder /wheels /wheels