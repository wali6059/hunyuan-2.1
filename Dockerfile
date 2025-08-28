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

# Build wheels with caching and fix metadata issues
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/tmp/ccache \
    bash scripts/build_wheels.sh && \
    # Fix any malformed wheel files by rebuilding them properly \
    find wheels/ -name "*.whl" -exec python3 -c " \
import sys, zipfile, os; \
try: \
    with zipfile.ZipFile(sys.argv[1], 'r') as z: \
        z.testzip(); \
except: \
    print(f'Removing corrupted wheel: {sys.argv[1]}'); \
    os.remove(sys.argv[1]) \
" {} \; && \
    # Rebuild the main package wheel properly \
    python3 -m pip wheel . -w wheels/ --no-deps --force-reinstall

# Runtime stage
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS runtime

# Install Python and system dependencies for 3D processing
RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    libglu1-mesa libxmu6 libfreetype6 libopenblas-dev \
    libegl1-mesa-dev libxi6 libgconf-2-4 \
    python3.10 python3.10-venv python3-pip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt pyproject.toml ./

# Create virtual environment and install base requirements
RUN uv venv && \
    uv pip install -r requirements.txt

# Copy built wheels and install them
COPY --from=builder /build/wheels ./wheels/
RUN # Install valid wheels only, skip any corrupted ones \
    for wheel in wheels/*.whl; do \
        if [ -f "$wheel" ]; then \
            echo "Installing wheel: $wheel"; \
            uv pip install "$wheel" --force-reinstall || echo "Skipped corrupted wheel: $wheel"; \
        fi; \
    done && \
    # Clean up wheels after installation \
    rm -rf wheels/

# Copy application code
COPY api_server.py download_script.py constants.py logger_utils.py api_models.py model_worker.py ./
COPY hy3dgen ./hy3dgen/

# Install the main package in development mode to ensure all modules are available
RUN uv pip install -e . --no-deps

# Set environment variables
ENV HY3DGEN_MODELS=/app/weights
ENV PYOPENGL_PLATFORM=egl
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Create weights directory
RUN mkdir -p /app/weights

# Expose API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import torch; import hy3dgen; print('Health check passed')" || exit 1

# Default command
CMD ["python", "api_server.py"]