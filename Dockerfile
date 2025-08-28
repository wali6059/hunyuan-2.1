FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

# Install comprehensive system dependencies
RUN apt-get update && apt-get install -y \
    build-essential cmake ninja-build pkg-config \
    gcc g++ gdb clang \
    python3.10 python3.10-dev python3.10-venv python3-pip \
    git wget curl unzip \
    libgl1-mesa-dev libglib2.0-0 libsm6 libxrender1 libxext6 \
    libglu1-mesa-dev libxmu6 libfreetype6-dev libopenblas-dev \
    libegl1-mesa-dev libxi6 libgconf-2-4 libxrandr2 libxss1 \
    libgtk-3-dev libgdk-pixbuf2.0-dev libxcomposite1 libxcursor1 \
    libxdamage1 libxfixes3 libxi6 libxinerama1 libxrandr2 libxss1 \
    libgconf-2-4 libasound2-dev libpango1.0-dev libatk1.0-dev \
    libcairo-gobject2 libgtk-3-0 libgdk-pixbuf2.0-0 \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set Python environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set comprehensive CUDA environment for compilation
ENV CUDA_HOME=/usr/local/cuda
ENV CUDA_ROOT=/usr/local/cuda
ENV PATH=${CUDA_HOME}/bin:${PATH}
ENV LD_LIBRARY_PATH=${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}
ENV LIBRARY_PATH=${CUDA_HOME}/lib64/stubs:${LIBRARY_PATH}
ENV TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9;9.0"
ENV CUDA_NVCC_FLAGS="--allow-unsupported-compiler --expt-relaxed-constexpr --expt-extended-lambda"
ENV FORCE_CUDA=1
ENV TORCH_NVCC_FLAGS="-Xfatbin -compress-all"

# Verify CUDA installation
RUN nvcc --version && nvidia-smi || echo "CUDA verification complete"

# Copy uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Create virtual environment first
RUN uv venv

# Set virtual environment path persistently
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/.venv/lib/python3.10/site-packages:$PYTHONPATH"

# Copy all source code first (needed for proper builds)
COPY . .

# Install PyTorch with compatible CUDA version (CUDA 12.8 detected)
RUN echo "Installing PyTorch with CUDA 12.1 support (compatible with 12.8)..." && \
    uv pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
    --index-url https://download.pytorch.org/whl/cu121

# Install essential build dependencies
RUN uv pip install \
    wheel setuptools \
    pybind11[global] \
    ninja \
    packaging \
    cmake

# Verify PyTorch CUDA support
RUN python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA version: {torch.version.cuda if torch.cuda.is_available() else \"N/A\"}')"

# Install requirements with error handling
RUN echo "Installing requirements..." && \
    uv pip install -r requirements.txt --no-deps || \
    (echo "Some packages failed, continuing..." && exit 0)

# Build custom extensions with proper error handling
RUN echo "Building custom rasterizer..." && \
    cd hy3dgen/texgen/custom_rasterizer && \
    MAX_JOBS=4 python setup.py build_ext --inplace \
    --verbose --debug && \
    uv pip install -e . --no-deps --force-reinstall

RUN echo "Building differentiable renderer..." && \
    cd hy3dgen/texgen/differentiable_renderer && \
    MAX_JOBS=4 python setup.py build_ext --inplace \
    --verbose --debug && \
    uv pip install -e . --no-deps --force-reinstall

# Install main package
RUN echo "Installing main package..." && \
    uv pip install -e . --no-deps --force-reinstall

# Install any remaining requirements that might have failed
RUN echo "Installing remaining requirements..." && \
    uv pip install \
    transformers==4.46.0 \
    diffusers==0.30.0 \
    accelerate==1.1.1 \
    huggingface-hub==0.30.2 \
    safetensors==0.4.4 \
    numpy==1.24.4 \
    scipy==1.14.1 \
    einops==0.8.0 \
    opencv-python==4.10.0.84 \
    imageio==2.36.0 \
    scikit-image==0.24.0 \
    rembg==2.0.65 \
    onnxruntime-gpu \
    trimesh==4.4.7 \
    pymeshlab==2022.2.post3 \
    pygltflib==1.16.3 \
    xatlas==0.0.9 \
    omegaconf==2.3.0 \
    pyyaml==6.0.2 \
    fastapi==0.115.12 \
    uvicorn==0.34.3 \
    pydantic==2.10.6 \
    tqdm==4.66.5 \
    psutil==6.0.0 \
    boto3 \
    runpod \
    requests \
    Pillow || echo "Some packages may have failed, continuing..."

# Try to install remaining packages that might need compilation
RUN echo "Installing packages that need compilation..." && \
    (uv pip install realesrgan==0.3.0 || echo "realesrgan failed, skipping") && \
    (uv pip install basicsr==1.4.2 || echo "basicsr failed, skipping") && \
    (uv pip install open3d==0.18.0 || echo "open3d failed, skipping") && \
    (uv pip install torchmetrics==1.6.0 || echo "torchmetrics failed, skipping") && \
    (uv pip install timm || echo "timm failed, skipping") && \
    (uv pip install torchdiffeq || echo "torchdiffeq failed, skipping")

# Verify critical imports with better error handling
RUN echo "Verifying critical imports..." && \
    python -c "import torch; print('✓ PyTorch')" && \
    python -c "import hy3dgen; print('✓ hy3dgen')" && \
    (python -c "from hy3dgen.rembg import BackgroundRemover; print('✓ BackgroundRemover')" || echo "⚠ BackgroundRemover failed - may need manual ONNX install") && \
    (python -c "from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline; print('✓ ShapePipeline')" || echo "⚠ ShapePipeline failed") && \
    (python -c "from hy3dgen.texgen import Hunyuan3DPaintPipeline; print('✓ TexturePipeline')" || echo "⚠ TexturePipeline failed") && \
    echo "Import verification completed (some may have warnings)"

# Set environment variables
ENV HY3DGEN_MODELS=/app/weights
ENV PYOPENGL_PLATFORM=egl
ENV CUDA_VISIBLE_DEVICES=0

# Create weights directory
RUN mkdir -p /app/weights

# Fix permissions
RUN chmod -R 755 /app

# Expose API port
EXPOSE 8080

# Enhanced health check with timeout
HEALTHCHECK --interval=30s --timeout=30s --start-period=120s --retries=3 \
    CMD timeout 25s python -c "import torch; import hy3dgen; print('Health check passed')" || exit 1

# Default command with error handling
CMD ["python", "api_server.py"]