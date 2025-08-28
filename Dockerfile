FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential cmake ninja-build \
    python3.10 python3.10-dev python3-pip \
    git wget curl \
    && rm -rf /var/lib/apt/lists/*

# Set Python environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set CUDA environment for compilation
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=${CUDA_HOME}/bin:${PATH}
ENV LD_LIBRARY_PATH=${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}
ENV TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9"
ENV CUDA_NVCC_FLAGS="-allow-unsupported-compiler"

# Download uv binary for fast package management in builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install PyTorch for build using uv
RUN uv pip install --system torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124

# Install build tools using uv
RUN uv pip install --system wheel setuptools pybind11 ninja

WORKDIR /build
COPY . .

# Build wheels with caching
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/tmp/ccache \
    bash scripts/build_wheels.sh

# Runtime stage
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS base

# Install Python and system dependencies for 3D processing
RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    libglu1-mesa libxmu6 libfreetype6 libopenblas-dev \
    libegl1-mesa-dev libxi6 libgconf-2-4 \
    python3.10 python3.10-venv python3-pip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download uv binary for fast package management
FROM ghcr.io/astral-sh/uv:latest AS uvstage

FROM base
COPY --from=uvstage /uv /uvx /bin/
WORKDIR /app

# Copy built wheels and source code
COPY --from=builder /build/wheels ./wheels/
COPY api_server.py download_script.py constants.py logger_utils.py api_models.py model_worker.py ./
COPY hy3dgen ./hy3dgen/

# Create virtual environment and install wheels
RUN uv venv 
RUN ls -la wheels/ && \
    uv pip install wheels/*.whl

# Set environment variables
ENV HY3DGEN_MODELS=/app/weights
ENV PYOPENGL_PLATFORM=egl

# Expose API port
EXPOSE 8080

# Default command
CMD [".venv/bin/python", "api_server.py"]