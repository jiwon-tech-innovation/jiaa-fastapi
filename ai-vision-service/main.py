import base64
import json
import os
from typing import Optional

import boto3
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel

app = FastAPI()

# Bedrock 클라이언트 초기화
# AWS 자격 증명은 환경 변수(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) 또는 
# Kubernetes Secret에서 설정된 값을 사용합니다
bedrock_runtime = boto3.client(
    service_name="bedrock-runtime",
    region_name=os.getenv("AWS_REGION", "us-east-1"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)

# 기본 모델 ID (Claude 3 Sonnet with Vision)
DEFAULT_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"


class VisionRequest(BaseModel):
    prompt: str
    model_id: Optional[str] = DEFAULT_MODEL_ID
    max_tokens: Optional[int] = 1024
    temperature: Optional[float] = 0.7


class VisionResponse(BaseModel):
    response: str
    model_id: str


@app.get("/")
def read_root():
    return {"service": "ai-vision-service", "status": "running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/analyze", response_model=VisionResponse)
async def analyze_image(
    file: UploadFile = File(...),
    prompt: str = "이 이미지를 자세히 분석해주세요.",
    model_id: str = DEFAULT_MODEL_ID,
    max_tokens: int = 1024,
    temperature: float = 0.7,
):
    """
    Bedrock을 사용한 이미지 분석 엔드포인트
    """
    try:
        # 이미지 파일 읽기
        image_data = await file.read()
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        # MIME 타입 확인
        mime_type = file.content_type or "image/jpeg"

        # Bedrock 요청 페이로드 구성
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": image_base64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            }
        )

        # Bedrock API 호출
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=body,
        )

        # 응답 파싱
        response_body = json.loads(response.get("body").read())
        assistant_message = response_body.get("content", [])[0].get("text", "")

        return VisionResponse(
            response=assistant_message,
            model_id=model_id,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bedrock API 오류: {str(e)}")