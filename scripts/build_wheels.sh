#!/bin/bash
set -e

# Build script for Hunyuan3D 2.1 wheels
echo "Building Hunyuan3D 2.1 wheels..."

# Set CUDA environment
export TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9"
export CUDA_NVCC_FLAGS="-allow-unsupported-compiler"
export CCACHE_DIR=/tmp/ccache

# Create wheels directory
mkdir -p wheels

# Build wheels in parallel
echo "Building wheels in parallel..."
(
    echo "Building custom_rasterizer wheel..."
    cd hy3dgen/texgen/custom_rasterizer
    python3 -m pip wheel . -w ../../../wheels/ --no-deps
) &
PID1=$!

(
    echo "Building differentiable_renderer wheel..."
    cd hy3dgen/texgen/differentiable_renderer
    python3 -m pip wheel . -w ../../../wheels/ --no-deps
) &
PID2=$!

(
    echo "Building hunyuan3d_21 wheel..."
    python3 -m pip wheel . -w wheels/ --no-deps
) &
PID3=$!

# Wait for all builds to complete
echo "Waiting for builds to complete..."
wait $PID1 $PID2 $PID3

echo "Wheels built successfully!"
ls -la wheels/