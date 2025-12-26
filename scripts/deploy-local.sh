#!/bin/bash

# 로컬 Kubernetes 배포 스크립트
set -e

echo "🚀 Deploying to local Kubernetes (Docker Desktop)..."

# 컨텍스트 확인
CONTEXT=$(kubectl config current-context)
if [[ "$CONTEXT" != "docker-desktop" ]]; then
    echo "⚠️  현재 컨텍스트: $CONTEXT"
    echo "Docker Desktop 컨텍스트로 변경하시겠습니까? (y/n)"
    read -r answer
    if [[ "$answer" == "y" ]]; then
        kubectl config use-context docker-desktop
    else
        echo "취소됨"
        exit 1
    fi
fi

# Kustomize로 배포
echo ""
echo "📦 Applying Kustomize..."
kubectl apply -k k8s/local/

# 모든 서비스 대기
echo ""
echo "⏳ Waiting for all services to be ready..."
kubectl wait --for=condition=ready pod --all -n jiwon-tech --timeout=300s || true

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Pod status:"
kubectl get pods -n jiwon-tech

echo ""
echo "🌐 Service status:"
kubectl get svc -n jiwon-tech
