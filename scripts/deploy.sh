#!/bin/bash
set -e

# Deployment script for Hunyuan3D 2.1 on Runpod

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Hunyuan3D 2.1 Deployment Script${NC}"
echo "=================================="

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

# Check for NVIDIA Docker runtime
if ! docker info | grep -q nvidia; then
    echo -e "${YELLOW}⚠️  NVIDIA Docker runtime not detected. Make sure nvidia-docker is installed.${NC}"
fi

# Set default values
REGISTRY=${REGISTRY:-"your-registry"}
IMAGE_NAME=${IMAGE_NAME:-"hunyuan3d-21"}
TAG=${TAG:-"latest"}
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"

echo -e "${GREEN}📦 Building Docker image...${NC}"
echo "Image: ${FULL_IMAGE}"

# Build the image
docker build -t "${IMAGE_NAME}:${TAG}" .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Build completed successfully!${NC}"
else
    echo -e "${RED}❌ Build failed!${NC}"
    exit 1
fi

# Tag for registry
if [ "$REGISTRY" != "your-registry" ]; then
    echo -e "${GREEN}🏷️  Tagging image for registry...${NC}"
    docker tag "${IMAGE_NAME}:${TAG}" "${FULL_IMAGE}"
    
    echo -e "${GREEN}📤 Pushing to registry...${NC}"
    docker push "${FULL_IMAGE}"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Push completed successfully!${NC}"
        echo -e "${GREEN}🎉 Image ready for Runpod deployment: ${FULL_IMAGE}${NC}"
    else
        echo -e "${RED}❌ Push failed!${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  Registry not specified. Skipping push.${NC}"
    echo -e "${GREEN}✅ Local image ready: ${IMAGE_NAME}:${TAG}${NC}"
fi

echo ""
echo -e "${GREEN}📋 Next steps:${NC}"
echo "1. Update your Runpod template with image: ${FULL_IMAGE}"
echo "2. Set environment variables (see .env.example)"
echo "3. Ensure GPU has 29GB+ VRAM (RTX 4090/A6000+)"
echo "4. Deploy as serverless endpoint"
echo ""
echo -e "${GREEN}🔧 Configuration:${NC}"
echo "- Memory requirement: 29GB VRAM"
echo "- Cold start time: ~2-3 minutes"
echo "- Inference time: ~30-60 seconds"
echo ""
echo -e "${GREEN}✨ Deployment complete!${NC}"