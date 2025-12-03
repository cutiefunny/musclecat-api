from fastapi import FastAPI, HTTPException, status, Query, Path, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from uuid import uuid4
from datetime import datetime, timezone

app = FastAPI(
    title="CLT Chatbot API (Mock)",
    description="Mock API for CLT Chatbot Frontend Development",
    version="1.0.0"
)

# --- CORS 설정 (프론트엔드 연동을 위해 필수) ---
origins = [
    "http://localhost:3000", # Next.js 기본 포트
    "http://127.0.0.1:3000",
    "https://clt-chatbot.vercel.app",
    "http://202.20.84.65:10000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models (데이터 구조 정의) ---

# 1. Chat 관련 모델
class ChatRequest(BaseModel):
    conversation_id: Optional[str] = Field(None, description="기존 대화 ID")
    content: str = Field(..., description="사용자 메시지")
    language: Optional[str] = Field("ko", description="언어 설정")
    slots: Optional[Dict[str, Any]] = Field(None, description="시나리오 슬롯 상태")

class ChatResponse(BaseModel):
    type: str = Field(..., pattern="^(text|scenario)$")
    message: str
    slots: Optional[Dict[str, Any]] = None
    next_node: Optional[Dict[str, Any]] = None

# 2. Conversation 관련 모델
class ConversationSummary(BaseModel):
    id: str
    title: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime

class CreateConversationRequest(BaseModel):
    title: Optional[str] = None

class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    is_pinned: Optional[bool] = None

class Message(BaseModel):
    id: str
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str
    created_at: datetime

class ConversationDetail(BaseModel):
    id: str
    messages: List[Message]

# 3. Scenario 관련 모델
class ScenarioItem(BaseModel):
    id: str
    title: str
    description: str

class ScenarioCategory(BaseModel):
    category: str
    items: List[ScenarioItem]


# --- In-Memory Mock Data Store (DB 대용) ---

# 대화 목록 저장소
MOCK_CONVERSATIONS: List[Dict] = [
    {
        "id": "uuid-1",
        "title": "기본 인사 테스트",
        "is_pinned": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    },
    {
        "id": "uuid-2",
        "title": "비자 신청 문의",
        "is_pinned": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
]

# 메시지 기록 저장소 (Conversation ID를 Key로 사용)
MOCK_MESSAGES: Dict[str, List[Dict]] = {
    "uuid-1": [
        {"id": "msg-1", "role": "user", "content": "안녕?", "created_at": datetime.now(timezone.utc)},
        {"id": "msg-2", "role": "assistant", "content": "안녕하세요! 무엇을 도와드릴까요?", "created_at": datetime.now(timezone.utc)}
    ],
    "uuid-2": []
}

# 시나리오 데이터
MOCK_SCENARIOS = [
    {
        "category": "인사",
        "items": [
            {"id": "greeting", "title": "기본 인사", "description": "봇과 가볍게 인사를 나눕니다."},
            {"id": "intro", "title": "봇 소개", "description": "이 봇의 기능을 설명합니다."}
        ]
    },
    {
        "category": "민원",
        "items": [
            {"id": "visa", "title": "비자 문의", "description": "비자 발급 절차를 안내합니다."},
            {"id": "tax", "title": "세금 납부", "description": "지방세 납부 방법을 안내합니다."}
        ]
    }
]


# --- API Endpoints ---

# 1. Chat Endpoint
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    사용자 메시지를 받아 Mock 응답을 반환합니다.
    conversation_id가 있으면 해당 대화방에 메시지를 저장하는 척합니다.
    """
    # Mock Logic: 무조건 에코 응답 혹은 고정된 시나리오 응답 반환
    response_msg = f"Echo: {request.content} (Mock Response)"
    
    # 대화방 ID가 제공되었다면 메시지 저장 시늉 (실제 DB라면 여기서 Insert)
    if request.conversation_id and request.conversation_id in MOCK_MESSAGES:
        # 사용자 메시지 저장
        MOCK_MESSAGES[request.conversation_id].append({
            "id": str(uuid4()),
            "role": "user",
            "content": request.content,
            "created_at": datetime.now(timezone.utc)
        })
        # 봇 메시지 저장
        MOCK_MESSAGES[request.conversation_id].append({
            "id": str(uuid4()),
            "role": "assistant",
            "content": response_msg,
            "created_at": datetime.now(timezone.utc)
        })
    
    return {
        "type": "text",
        "message": response_msg,
        "slots": request.slots or {}, # 기존 슬롯 유지
        "next_node": None
    }

# 2. Conversations Endpoints
@app.get("/conversations", response_model=List[ConversationSummary])
async def get_conversations():
    """모든 대화방 목록을 최신순(Mock은 그냥 리스트 순)으로 반환"""
    return MOCK_CONVERSATIONS

@app.post("/conversations", status_code=status.HTTP_201_CREATED, response_model=ConversationSummary)
async def create_conversation(request: CreateConversationRequest):
    """새 대화방 생성"""
    new_id = str(uuid4())
    new_title = request.title if request.title else "New Chat"
    now = datetime.now(timezone.utc)
    
    new_conv = {
        "id": new_id,
        "title": new_title,
        "is_pinned": False,
        "created_at": now,
        "updated_at": now
    }
    
    MOCK_CONVERSATIONS.insert(0, new_conv) # 최신이 위로 오도록
    MOCK_MESSAGES[new_id] = [] # 메시지 저장소 초기화
    
    return new_conv

@app.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation_detail(
    conversation_id: str = Path(..., description="대화방 ID"),
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0)
):
    """특정 대화방의 상세 정보와 메시지 반환"""
    # 대화방 존재 확인
    if conversation_id not in MOCK_MESSAGES:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    all_messages = MOCK_MESSAGES[conversation_id]
    
    # 페이징 처리 (Mock)
    start = offset
    end = offset + limit
    sliced_messages = all_messages[start:end]
    
    return {
        "id": conversation_id,
        "messages": sliced_messages
    }

@app.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
async def update_conversation(
    conversation_id: str,
    request: UpdateConversationRequest
):
    """대화방 제목 또는 고정 상태 수정"""
    target_conv = next((c for c in MOCK_CONVERSATIONS if c["id"] == conversation_id), None)
    
    if not target_conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    if request.title is not None:
        target_conv["title"] = request.title
    if request.is_pinned is not None:
        target_conv["is_pinned"] = request.is_pinned
        
    target_conv["updated_at"] = datetime.now(timezone.utc)
    
    return target_conv

@app.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str):
    """대화방 삭제"""
    global MOCK_CONVERSATIONS
    
    # 리스트에서 해당 ID 제외하고 필터링
    initial_len = len(MOCK_CONVERSATIONS)
    MOCK_CONVERSATIONS = [c for c in MOCK_CONVERSATIONS if c["id"] != conversation_id]
    
    if len(MOCK_CONVERSATIONS) == initial_len:
         raise HTTPException(status_code=404, detail="Conversation not found")

    # 메시지 저장소에서도 삭제
    if conversation_id in MOCK_MESSAGES:
        del MOCK_MESSAGES[conversation_id]
        
    return None

# 3. Scenarios Endpoint
@app.get("/scenarios", response_model=List[ScenarioCategory])
async def get_scenarios():
    """사용 가능한 시나리오 목록 반환"""
    return MOCK_SCENARIOS

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)