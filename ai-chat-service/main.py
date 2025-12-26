import json
import os
import uuid
from typing import Optional, List, Dict
from datetime import datetime

import boto3
import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import init_db, get_db, Personality, SessionConfig, ConversationMessage

app = FastAPI()

# 앱 시작 이벤트에서 데이터베이스 초기화
@app.on_event("startup")
async def startup_event():
    """앱 시작 시 데이터베이스 초기화"""
    try:
        init_db()
    except Exception as e:
        print(f"⚠️ 데이터베이스 초기화 중 오류 (무시 가능): {e}")

# 대화 히스토리 저장소 (메모리 기반, 프로덕션에서는 Redis 등 사용 권장)
conversation_history: Dict[str, List[Dict]] = {}

# WebSocket 연결 관리 (세션 ID -> WebSocket 매핑)
active_connections: Dict[str, WebSocket] = {}

# Bedrock 클라이언트 초기화
bedrock_runtime = boto3.client(
    service_name="bedrock-runtime",
    region_name=os.getenv("AWS_REGION", "us-east-1"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)

# 기본 모델 ID
DEFAULT_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

# 임베딩 모델 ID (AWS Bedrock Titan Embeddings)
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v1"

# 로드맵 프롬프트 (로드맵 생성 시에만 사용)
ROADMAP_SYSTEM_PROMPT = """# Role
당신은 PC/랩탑 환경 기반의 학습자를 위한 [로드맵 생성 인터뷰어]입니다.

# Rules & Constraints
1. **인터뷰 원칙**: 
   - 한 번에 '하나의 질문'만 던집니다. 
   - 질문 시 인사, 요약, 부연 설명 없이 오직 질문만 출력합니다.
2. **범위 제한**: PC/랩탑 활용 활동으로만 제한하며, 오프라인 활동 감지 시 재질문을 던집니다.
3. **상태 체크리스트**: [A] 총목표, [B] 세부 목표, [C] 총 기간, [D] 일일 학습 시간

# Interaction Workflow (반드시 순서 준수)

### 1단계: 정보 수집 (Collection)
- [A]~[D] 중 누락된 정보를 순차적으로 하나씩 질문합니다.

### 2단계: 요약 및 확정 (Confirmation & Revision)
- [A]~[D] 정보가 모두 수집되면, 사용자에게 수집된 내용을 요약하여 보여줍니다.
- **중요**: 요약 후 반드시 "이대로 로드맵을 생성할까요? 수정하고 싶은 부분이 있다면 말씀해 주세요."라고 묻습니다.
- 사용자가 수정을 요청하면 해당 항목을 업데이트하고 다시 2단계(요약 및 확정)를 반복합니다.

### 3단계: 최종 출력 (Final Output)
- 사용자가 "됐어", "생성해줘", "확인" 등 승인 의사를 표시했을 때만 JSON 로드맵을 출력합니다.
- 출력 시 다른 텍스트 없이 오직 JSON 데이터만 출력하고 종료합니다.

# Output Format (JSON Only)
{
  "roadmap": [
    {
      "day": number,
      "content": "해당 일차에 수행할 PC 기반 학습 내용",
      "time": "사용자가 확정한 [D] 값"
    }
  ]
}

# Instruction to Start
가장 먼저 [A] 총목표를 묻는 질문부터 시작하세요."""


def get_session_config(session_id: str, db: Session) -> Optional[SessionConfig]:
    """세션 설정 가져오기"""
    return db.query(SessionConfig).filter(SessionConfig.session_id == session_id).first()


def generate_embedding(text: str) -> Optional[List[float]]:
    """텍스트를 벡터 임베딩으로 변환"""
    try:
        # AWS Bedrock Titan Embeddings 사용
        body = json.dumps({
            "inputText": text
        })
        
        response = bedrock_runtime.invoke_model(
            modelId=EMBEDDING_MODEL_ID,
            body=body,
        )
        
        response_body = json.loads(response.get("body").read())
        embedding = response_body.get("embedding", [])
        
        return embedding if embedding else None
    except Exception as e:
        print(f"⚠️ 임베딩 생성 실패: {e}")
        return None


def save_conversation_message(
    session_id: str,
    role: str,
    content: str,
    user_id: Optional[str] = None,
    db: Session = None
):
    """대화 메시지를 벡터와 함께 저장"""
    if db is None:
        from database import SessionLocal
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    
    try:
        # 임베딩 생성
        embedding = generate_embedding(content)
        
        # user_id를 UUID로 변환
        user_uuid = None
        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
            except ValueError:
                pass
        
        # 메시지 저장
        message = ConversationMessage(
            session_id=session_id,
            user_id=user_uuid,
            role=role,
            content=content,
            embedding=embedding
        )
        db.add(message)
        db.commit()
        
        return message
    except Exception as e:
        db.rollback()
        print(f"⚠️ 메시지 저장 실패: {e}")
        return None
    finally:
        if should_close:
            db.close()


def search_similar_messages(
    query: str,
    user_id: Optional[str] = None,
    limit: int = 5,
    db: Session = None
) -> List[Dict]:
    """유사한 대화 메시지 검색 (pgvector 사용)"""
    if db is None:
        from database import SessionLocal
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    
    try:
        # 쿼리 임베딩 생성
        query_embedding = generate_embedding(query)
        if not query_embedding:
            return []
        
        # pgvector의 코사인 거리 연산자 사용 (<->)
        from sqlalchemy import text, func
        
        # 벡터를 문자열로 변환
        embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        
        # SQL 쿼리 작성
        sql_query = text("""
            SELECT 
                id, session_id, user_id, role, content, created_at,
                1 - (embedding <=> :query_vec::vector) as similarity
            FROM conversation_messages
            WHERE embedding IS NOT NULL
        """)
        
        # user_id 필터 추가
        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
                sql_query = text("""
                    SELECT 
                        id, session_id, user_id, role, content, created_at,
                        1 - (embedding <=> :query_vec::vector) as similarity
                    FROM conversation_messages
                    WHERE embedding IS NOT NULL AND user_id = :user_id
                """)
                result = db.execute(sql_query, {"query_vec": embedding_str, "user_id": str(user_uuid)})
            except ValueError:
                result = db.execute(sql_query, {"query_vec": embedding_str})
        else:
            result = db.execute(sql_query, {"query_vec": embedding_str})
        
        # 결과를 딕셔너리로 변환
        rows = result.fetchall()
        results = []
        for row in sorted(rows, key=lambda x: x[6], reverse=True)[:limit]:
            results.append({
                "id": row[0],
                "session_id": row[1],
                "role": row[3],
                "content": row[4],
                "similarity": float(row[6]) if row[6] is not None else 0.0,
                "created_at": row[5].isoformat() if row[5] else None
            })
        
        return results
    except Exception as e:
        print(f"⚠️ 검색 실패: {e}")
        import traceback
        traceback.print_exc()
        # 폴백: 기존 방식으로 검색
        try:
            messages = db.query(ConversationMessage).filter(
                ConversationMessage.embedding.isnot(None)
            )
            
            if user_id:
                try:
                    user_uuid = uuid.UUID(user_id)
                    messages = messages.filter(ConversationMessage.user_id == user_uuid)
                except ValueError:
                    pass
            
            all_messages = messages.all()
            
            # 코사인 유사도 계산
            similarities = []
            query_vec = np.array(query_embedding)
            
            for msg in all_messages:
                if msg.embedding:
                    msg_vec = np.array(msg.embedding)
                    cosine_sim = np.dot(query_vec, msg_vec) / (
                        np.linalg.norm(query_vec) * np.linalg.norm(msg_vec)
                    )
                    similarities.append({
                        "message": msg,
                        "similarity": float(cosine_sim)
                    })
            
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            
            results = []
            for item in similarities[:limit]:
                msg = item["message"]
                results.append({
                    "id": msg.id,
                    "session_id": msg.session_id,
                    "role": msg.role,
                    "content": msg.content,
                    "similarity": item["similarity"],
                    "created_at": msg.created_at.isoformat() if msg.created_at else None
                })
            
            return results
        except Exception as e2:
            print(f"⚠️ 폴백 검색도 실패: {e2}")
            return []
    finally:
        if should_close:
            db.close()


def get_system_prompt(session_id: str, db: Session) -> str:
    """세션에 맞는 시스템 프롬프트 가져오기"""
    config = get_session_config(session_id, db)
    
    # 로드맵 모드인 경우
    if config and config.mode == "roadmap":
        return ROADMAP_SYSTEM_PROMPT
    
    # 성격이 선택된 경우
    if config and config.personality_id:
        personality = db.query(Personality).filter(Personality.id == config.personality_id).first()
        if personality:
            return personality.system_prompt
    
    # 기본값: 베타인 (첫 번째 성격)
    default_personality = db.query(Personality).filter(Personality.name == "베타인").first()
    if default_personality:
        return default_personality.system_prompt
    
    return "당신은 도움이 되는 AI 어시스턴트입니다."


# Pydantic 모델들
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None  # UUID 문자열
    model_id: Optional[str] = DEFAULT_MODEL_ID
    max_tokens: Optional[int] = 4096
    temperature: Optional[float] = 0.7
    conversation_history: Optional[List[Dict]] = None


class ChatResponse(BaseModel):
    response: str
    model_id: str
    session_id: str


class PersonalityResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None


class SelectPersonalityRequest(BaseModel):
    session_id: str
    personality_id: int
    user_id: Optional[str] = None  # UUID 문자열


class StartRoadmapRequest(BaseModel):
    session_id: str
    user_id: Optional[str] = None  # UUID 문자열


class SearchRequest(BaseModel):
    query: str
    user_id: Optional[str] = None  # UUID 문자열
    limit: Optional[int] = 5


# API 엔드포인트들
@app.get("/")
def read_root():
    return {"service": "ai-chat-service", "status": "running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/debug/personalities")
def debug_personalities():
    """디버깅용: 성격 목록 직접 조회"""
    try:
        from database import SessionLocal, Personality
        db = SessionLocal()
        try:
            personalities = db.query(Personality).all()
            return {
                "count": len(personalities),
                "personalities": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description
                    }
                    for p in personalities
                ]
            }
        finally:
            db.close()
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/sessions/user/{user_id}")
def get_user_sessions(user_id: str, db: Session = Depends(get_db)):
    """사용자별 세션 목록 조회"""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 user_id 형식입니다.")
    
    sessions = db.query(SessionConfig).filter(SessionConfig.user_id == user_uuid).all()
    
    return {
        "user_id": user_id,
        "sessions": [
            {
                "session_id": s.session_id,
                "personality_id": s.personality_id,
                "mode": s.mode,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None
            }
            for s in sessions
        ]
    }





@app.get("/personalities", response_model=List[PersonalityResponse])
def get_personalities(db: Session = Depends(get_db)):
    """사용 가능한 성격 캐릭터 목록 조회"""
    try:
        personalities = db.query(Personality).all()
        return [
            PersonalityResponse(
                id=p.id,
                name=p.name,
                description=p.description
            )
            for p in personalities
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"성격 목록 조회 중 오류 발생: {str(e)}")


@app.post("/personalities/select")
def select_personality(request: SelectPersonalityRequest, db: Session = Depends(get_db)):
    """세션에 성격 캐릭터 선택"""
    try:
        # 성격 존재 확인
        personality = db.query(Personality).filter(Personality.id == request.personality_id).first()
        if not personality:
            raise HTTPException(status_code=404, detail="성격을 찾을 수 없습니다.")
        
        # user_id를 UUID로 변환 (있는 경우)
        user_uuid = None
        if request.user_id:
            try:
                user_uuid = uuid.UUID(request.user_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="잘못된 user_id 형식입니다.")
        
        # 세션 설정 가져오기 또는 생성
        config = get_session_config(request.session_id, db)
        if not config:
            config = SessionConfig(
                session_id=request.session_id,
                user_id=user_uuid,
                personality_id=request.personality_id,
                mode="chat"
            )
            db.add(config)
        else:
            config.personality_id = request.personality_id
            config.mode = "chat"  # 일반 채팅 모드로 설정
            if user_uuid:
                config.user_id = user_uuid
            config.updated_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "message": f"{personality.name} 성격이 선택되었습니다.",
            "session_id": request.session_id,
            "personality": {
                "id": personality.id,
                "name": personality.name
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"성격 선택 중 오류 발생: {str(e)}")


@app.post("/chat/roadmap/start")
def start_roadmap(request: StartRoadmapRequest, db: Session = Depends(get_db)):
    """로드맵 생성 모드 시작"""
    try:
        # user_id를 UUID로 변환 (있는 경우)
        user_uuid = None
        if request.user_id:
            try:
                user_uuid = uuid.UUID(request.user_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="잘못된 user_id 형식입니다.")
        
        # 세션 설정 가져오기 또는 생성
        config = get_session_config(request.session_id, db)
        if not config:
            config = SessionConfig(
                session_id=request.session_id,
                user_id=user_uuid,
                mode="roadmap"
            )
            db.add(config)
        else:
            config.mode = "roadmap"
            if user_uuid:
                config.user_id = user_uuid
            config.updated_at = datetime.utcnow()
        
        db.commit()
        
        # 로드맵 모드 시작 시 대화 히스토리 초기화
        if request.session_id in conversation_history:
            del conversation_history[request.session_id]
        
        return {
            "message": "로드맵 생성 모드가 시작되었습니다.",
            "session_id": request.session_id,
            "mode": "roadmap"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"로드맵 모드 시작 중 오류 발생: {str(e)}")


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    """Bedrock을 사용한 채팅 엔드포인트"""
    try:
        # 세션 ID 처리
        session_id = request.session_id
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # user_id가 있으면 세션 설정에 저장
        if request.user_id:
            try:
                user_uuid = uuid.UUID(request.user_id)
                config = get_session_config(session_id, db)
                if not config:
                    config = SessionConfig(
                        session_id=session_id,
                        user_id=user_uuid,
                        mode="chat"
                    )
                    db.add(config)
                    db.commit()
                elif not config.user_id:
                    config.user_id = user_uuid
                    db.commit()
            except ValueError:
                # 잘못된 UUID 형식은 무시
                pass
        
        # 시스템 프롬프트 가져오기
        system_prompt = get_system_prompt(session_id, db)
        
        # 대화 히스토리 가져오기
        messages = []
        if request.conversation_history:
            for msg in request.conversation_history:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
        elif session_id in conversation_history:
            stored_messages = conversation_history[session_id]
            for msg in stored_messages:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
        
        # 현재 사용자 메시지 추가
        messages.append({
            "role": "user",
            "content": request.message,
        })
        
        # 사용자 메시지를 벡터와 함께 저장
        save_conversation_message(
            session_id=session_id,
            role="user",
            content=request.message,
            user_id=request.user_id,
            db=db
        )
        
        # Bedrock 요청 페이로드 구성
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "system": system_prompt,
                "messages": messages,
            }
        )

        # Bedrock API 호출
        response = bedrock_runtime.invoke_model(
            modelId=request.model_id,
            body=body,
        )

        # 응답 파싱
        response_body = json.loads(response.get("body").read())
        assistant_message = response_body.get("content", [])[0].get("text", "")
        
        # AI 응답을 벡터와 함께 저장
        save_conversation_message(
            session_id=session_id,
            role="assistant",
            content=assistant_message,
            user_id=request.user_id,
            db=db
        )
        
        # AI 응답을 히스토리에 추가
        messages.append({
            "role": "assistant",
            "content": assistant_message,
        })
        
        # 히스토리 저장 (최대 50개 메시지 유지)
        if len(messages) > 50:
            messages = messages[-50:]
        conversation_history[session_id] = messages

        return ChatResponse(
            response=assistant_message,
            model_id=request.model_id,
            session_id=session_id,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bedrock API 오류: {str(e)}")


@app.post("/chat/clear")
async def clear_history(session_id: str):
    """특정 세션의 대화 히스토리 삭제"""
    if session_id in conversation_history:
        del conversation_history[session_id]
        return {"message": "대화 히스토리가 삭제되었습니다.", "session_id": session_id}
    return {"message": "해당 세션을 찾을 수 없습니다.", "session_id": session_id}


@app.post("/chat/search")
def search_conversations(request: SearchRequest, db: Session = Depends(get_db)):
    """벡터 검색을 사용한 대화 메시지 검색"""
    try:
        results = search_similar_messages(
            query=request.query,
            user_id=request.user_id,
            limit=request.limit,
            db=db
        )
        
        return {
            "query": request.query,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 중 오류 발생: {str(e)}")


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket 기반 채팅 엔드포인트"""
    await websocket.accept()
    session_id = None
    
    # 데이터베이스 세션 생성
    from database import SessionLocal
    db = SessionLocal()
    
    try:
        while True:
            # 클라이언트로부터 메시지 수신
            data = await websocket.receive_text()
            
            try:
                # JSON 파싱
                request_data = json.loads(data)
                message = request_data.get("message", "")
                
                if not message:
                    await websocket.send_json({
                        "type": "error",
                        "error": "메시지가 비어있습니다."
                    })
                    continue
                
                # 세션 ID 처리
                session_id = request_data.get("session_id")
                if not session_id:
                    session_id = str(uuid.uuid4())
                    await websocket.send_json({
                        "type": "session",
                        "session_id": session_id
                    })
                
                # WebSocket 연결을 세션에 매핑
                active_connections[session_id] = websocket
                
                # 모델 설정 가져오기
                model_id = request_data.get("model_id", DEFAULT_MODEL_ID)
                max_tokens = request_data.get("max_tokens", 4096)
                temperature = request_data.get("temperature", 0.7)
                
                # 시스템 프롬프트 가져오기
                system_prompt = get_system_prompt(session_id, db)
                
                # 대화 히스토리 가져오기
                messages = []
                if request_data.get("conversation_history"):
                    for msg in request_data["conversation_history"]:
                        if isinstance(msg, dict) and "role" in msg and "content" in msg:
                            messages.append({
                                "role": msg["role"],
                                "content": msg["content"]
                            })
                elif session_id in conversation_history:
                    stored_messages = conversation_history[session_id]
                    for msg in stored_messages:
                        if isinstance(msg, dict) and "role" in msg and "content" in msg:
                            messages.append({
                                "role": msg["role"],
                                "content": msg["content"]
                            })
                
                # 현재 사용자 메시지 추가
                messages.append({
                    "role": "user",
                    "content": message,
                })
                
                # 사용자 메시지를 벡터와 함께 저장
                user_id = request_data.get("user_id")
                save_conversation_message(
                    session_id=session_id,
                    role="user",
                    content=message,
                    user_id=user_id,
                    db=db
                )
                
                # Bedrock 요청 페이로드 구성
                body = json.dumps(
                    {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "system": system_prompt,
                        "messages": messages,
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
                
                # AI 응답을 벡터와 함께 저장
                save_conversation_message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_message,
                    user_id=user_id,
                    db=db
                )
                
                # AI 응답을 히스토리에 추가
                messages.append({
                    "role": "assistant",
                    "content": assistant_message,
                })
                
                # 히스토리 저장 (최대 50개 메시지 유지)
                if len(messages) > 50:
                    messages = messages[-50:]
                conversation_history[session_id] = messages
                
                # 클라이언트에 응답 전송
                await websocket.send_json({
                    "type": "message",
                    "response": assistant_message,
                    "model_id": model_id,
                    "session_id": session_id,
                })
                
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "error": "잘못된 JSON 형식입니다."
                })
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "error": f"처리 중 오류가 발생했습니다: {str(e)}"
                })
                
    except WebSocketDisconnect:
        if session_id and session_id in active_connections:
            del active_connections[session_id]
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "error": f"연결 오류: {str(e)}"
            })
        except:
            pass
        if session_id and session_id in active_connections:
            del active_connections[session_id]
    finally:
        db.close()
