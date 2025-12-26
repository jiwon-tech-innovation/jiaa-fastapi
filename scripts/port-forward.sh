#!/bin/bash

# ai-chat-service 포트포워딩 (기본)
SERVICE=${1:-ai-chat-service}
LOCAL_PORT=${2:-8000}

if [ "$SERVICE" = "ai-chat-service" ]; then
    SERVICE_NAME="jiaa-ai-chat-service-svc"
    PORT=8000
elif [ "$SERVICE" = "ai-vision-service" ]; then
    SERVICE_NAME="jiaa-ai-vision-service-svc"
    PORT=8000
else
    echo "❌ 지원하지 않는 서비스입니다: $SERVICE"
    exit 1
fi

echo "🌐 Port forwarding $SERVICE to localhost:$LOCAL_PORT..."
echo ""
echo "Press Ctrl+C to stop"

kubectl port-forward svc/$SERVICE_NAME $LOCAL_PORT:$PORT -n jiwon-tech
