#!/bin/bash

# 로컬 Kubernetes 리소스 정리
echo "🧹 Cleaning up local Kubernetes resources..."

kubectl delete -k k8s/local/ --ignore-not-found

echo ""
echo "✅ Cleanup complete!"
