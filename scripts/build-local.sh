#!/bin/bash

# 로컬 Docker 이미지 빌드 스크립트
set -e

echo "🔨 Building all services for local Kubernetes..."

SERVICES=("ai-chat-service" "ai-vision-service")

echo ""
echo "🐳 Building Docker images..."

for SERVICE in "${SERVICES[@]}"; do
    echo ""
    echo "📦 Building $SERVICE image..."
    
    # 서비스 디렉토리 확인
    SERVICE_DIR="./${SERVICE}"
    if [ ! -d "$SERVICE_DIR" ]; then
        echo "❌ 서비스 디렉토리를 찾을 수 없습니다: $SERVICE_DIR"
        exit 1
    fi
    
    # Dockerfile 확인
    if [ ! -f "$SERVICE_DIR/Dockerfile" ]; then
        echo "❌ Dockerfile을 찾을 수 없습니다: $SERVICE_DIR/Dockerfile"
        exit 1
    fi
    
    # Docker 이미지 빌드
    IMAGE_NAME="jiaa-${SERVICE}:local"
    docker build -t "$IMAGE_NAME" -f "$SERVICE_DIR/Dockerfile" "$SERVICE_DIR"
done

echo ""
echo "✅ All images built successfully!"
echo ""
echo "Built images:"
docker images | grep "jiaa-.*:local"
