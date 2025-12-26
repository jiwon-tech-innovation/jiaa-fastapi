# 벡터 검색 기능 가이드

이 서비스는 PostgreSQL을 사용하여 대화 메시지를 벡터로 저장하고 검색할 수 있는 기능을 제공합니다.

## 기능

1. **자동 벡터 저장**: 모든 채팅 메시지(사용자 및 AI 응답)가 자동으로 벡터 임베딩과 함께 데이터베이스에 저장됩니다.
2. **벡터 검색**: 저장된 대화 내용을 벡터 유사도 검색으로 찾을 수 있습니다.
3. **pgvector 지원**: pgvector 확장이 있으면 최적화된 벡터 검색을 사용하고, 없으면 ARRAY 타입으로 저장하여 코사인 유사도로 검색합니다.

## 데이터베이스 구조

### ConversationMessage 테이블

- `id`: 메시지 ID
- `session_id`: 세션 ID
- `user_id`: 사용자 ID (UUID)
- `role`: 메시지 역할 ("user" 또는 "assistant")
- `content`: 메시지 내용
- `embedding`: 벡터 임베딩 (ARRAY 또는 vector 타입)
- `created_at`: 생성 시간

## API 엔드포인트

### 1. 벡터 검색

**POST** `/chat/search`

대화 메시지를 벡터 유사도로 검색합니다.

**Request Body:**
```json
{
  "query": "검색할 질문이나 키워드",
  "user_id": "사용자 UUID (선택사항)",
  "limit": 5
}
```

**Response:**
```json
{
  "query": "검색할 질문이나 키워드",
  "results": [
    {
      "id": 1,
      "session_id": "session-uuid",
      "role": "user",
      "content": "저장된 메시지 내용",
      "similarity": 0.95,
      "created_at": "2024-01-01T00:00:00"
    }
  ],
  "count": 1
}
```

**예시:**
```bash
curl -X POST "http://localhost:8000/chat/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Python 학습",
    "limit": 5
  }'
```

## pgvector 설치 (선택사항)

pgvector를 설치하면 더 빠른 벡터 검색이 가능합니다.

### Docker를 사용하는 경우

PostgreSQL 이미지에 pgvector를 포함한 이미지를 사용하거나, 수동으로 설치할 수 있습니다:

```bash
# pgvector가 포함된 PostgreSQL 이미지 사용
docker run -d \
  --name postgres-vector \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=jiwon \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 수동 설치

PostgreSQL 서버에 직접 접속하여 설치:

```sql
-- pgvector 확장 설치
CREATE EXTENSION IF NOT EXISTS vector;
```

## 사용 방법

### 1. 일반 채팅 (자동 벡터 저장)

일반 채팅을 하면 자동으로 벡터가 생성되어 저장됩니다:

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Python으로 웹 개발을 배우고 싶어요",
    "session_id": "my-session",
    "user_id": "user-uuid"
  }'
```

### 2. 벡터 검색

저장된 대화 내용을 검색:

```bash
curl -X POST "http://localhost:8000/chat/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Python 웹 개발",
    "user_id": "user-uuid",
    "limit": 10
  }'
```

## 임베딩 모델

현재 AWS Bedrock의 `amazon.titan-embed-text-v1` 모델을 사용합니다.

임베딩 모델을 변경하려면 `main.py`의 `EMBEDDING_MODEL_ID` 변수를 수정하세요.

## 주의사항

1. **pgvector 없이도 작동**: pgvector가 없어도 ARRAY 타입으로 저장하고 코사인 유사도로 검색합니다. 다만 대량의 데이터에서는 성능 차이가 있을 수 있습니다.

2. **임베딩 생성 비용**: AWS Bedrock API를 호출하므로 비용이 발생할 수 있습니다.

3. **비동기 처리**: 임베딩 생성은 동기적으로 처리되므로, 응답 시간이 약간 늘어날 수 있습니다.

## 문제 해결

### pgvector 확장 오류

pgvector가 설치되지 않은 경우 다음 경고가 나타납니다:
```
⚠️ pgvector 확장 없음 (ARRAY로 대체): ...
```

이는 정상이며, ARRAY 타입으로 작동합니다. pgvector를 설치하면 자동으로 사용됩니다.

### 임베딩 생성 실패

임베딩 생성이 실패하면 메시지는 저장되지만 벡터는 저장되지 않습니다. AWS Bedrock 설정을 확인하세요.

