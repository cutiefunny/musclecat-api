import asyncio
import os
import json  # JSON 변환을 위해 추가
from fastapi import FastAPI, BackgroundTasks, HTTPException, status, Query, Path, Body, APIRouter, Request # Request 추가
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from uuid import uuid4
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client
from sse_starlette.sse import EventSourceResponse # [설치 필요] pip install sse-starlette

# 환경 변수 로드
load_dotenv()

# Supabase 클라이언트 초기화
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Warning: SUPABASE_URL or SUPABASE_KEY is missing in .env file.")

# Client 생성 (전역)
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Failed to initialize Supabase client: {e}")
    supabase = None

app = FastAPI(
    title="CLT Chatbot API (Supabase Integration)",
    description="API connected to Supabase for CLT Chatbot",
    version="1.2.0"
)

# --- CORS 설정 ---
origins = [
    "http://localhost:3000",
    "http://localhost:3000/",
    "http://localhost:5173",
    "http://localhost:5173/",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3000/",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5173/",
    "https://clt-chatbot.vercel.app",
    "https://clt-chatbot.vercel.app/",
    "https://react-flow-three-ecru.vercel.app",
    "https://react-flow-three-ecru.vercel.app/",
    "http://202.20.84.65:10000",
    "http://202.20.84.65:10000/",
    "http://202.20.84.65:10001",
    "http://202.20.84.65:10001/",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# [전역 변수: 이벤트 큐]
# ==========================================
# 백그라운드 태스크와 SSE 엔드포인트 간의 통신을 위한 메모리 큐입니다.
# 실제 상용 서비스(다중 서버)에서는 Redis Pub/Sub 등을 사용하는 것이 좋습니다.
event_queue = asyncio.Queue()


# ==========================================
# [Models]
# ==========================================
# (이전과 동일한 모델 정의)

# 1. Chat Models
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

# 2. Conversation Models
class ConversationSummary(BaseModel):
    id: str
    title: Optional[str] = None
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
    role: str
    content: str
    created_at: datetime

class ConversationDetail(BaseModel):
    id: str
    messages: List[Message]

# 3. Client Scenarios
class ScenarioItem(BaseModel):
    id: str
    title: str
    description: str

class ScenarioCategory(BaseModel):
    category: str
    items: List[ScenarioItem]

# 4. Admin Models
class NodePosition(BaseModel):
    x: float
    y: float

class Node(BaseModel):
    id: str
    type: str
    position: NodePosition
    data: Dict[str, Any] = {}
    width: Optional[float] = None
    height: Optional[float] = None

class Edge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = None

class ScenarioListItem(BaseModel):
    id: str
    name: str
    job: Optional[str] = None
    description: Optional[str] = None
    updated_at: datetime
    last_used_at: Optional[datetime] = None

class ScenarioDetail(BaseModel):
    id: str
    name: str
    job: Optional[str] = None
    description: Optional[str] = None
    nodes: List[Dict[str, Any]] = [] 
    edges: List[Dict[str, Any]] = []
    start_node_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None

class CreateScenarioRequest(BaseModel):
    name: str
    job: Optional[str] = "Process"
    description: Optional[str] = ""
    category_id: Optional[str] = None
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    start_node_id: Optional[str] = None
    clone_from_id: Optional[str] = None

class UpdateScenarioRequest(BaseModel):
    name: str
    job: str
    description: Optional[str] = None
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    start_node_id: Optional[str] = None

class PatchScenarioRequest(BaseModel):
    name: Optional[str] = None
    job: Optional[str] = None
    description: Optional[str] = None
    last_used_at: Optional[datetime] = None

class ScenarioListResponse(BaseModel):
    scenarios: List[ScenarioListItem]

class ApiTemplateCreate(BaseModel):
    name: str
    method: str = "GET"
    url: str
    headers: Optional[Union[str, Dict]] = "{}"
    body: Optional[Union[str, Dict]] = "{}"
    responseMapping: List[Any] = []

class FormTemplateCreate(BaseModel):
    name: str
    title: str
    elements: List[Any] = []

class NodeVisibilitySettings(BaseModel):
    visibleNodeTypes: List[str]


# ==========================================
# [Helpers]
# ==========================================
def get_utc_now():
    return datetime.now(timezone.utc).isoformat()

# ==========================================
# [Background Tasks]
# ==========================================
async def perform_background_task(conversation_id: str):
    # 1. 무거운 작업을 시뮬레이션 (5초 대기)
    print(f"⏳ [Task] 비동기 작업 시작 (ID: {conversation_id})")
    await asyncio.sleep(5) 
    
    success_msg = "✅ 처리 완료 (5초 후 생성됨)"
    
    # 2. 작업 완료 후 DB에 결과 저장
    try:
        supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": success_msg,
            "created_at": get_utc_now()
        }).execute()
        
        # (선택) 대화방 updated_at 갱신
        supabase.table("conversations").update({
            "updated_at": get_utc_now()
        }).eq("id", conversation_id).execute()
        
        print(f"✅ [Task] 비동기 작업 완료 및 DB 저장 (ID: {conversation_id})")
        
        # 3. [추가됨] SSE 큐에 완료 이벤트 전송
        # 프론트엔드가 /events에 연결되어 있다면 이 메시지를 받게 됩니다.
        await event_queue.put({
            "conversation_id": conversation_id,
            "status": "done",
            "message": success_msg,
            "timestamp": get_utc_now()
        })
        print(f"📡 [Task] SSE 알림 큐 전송 완료")
        
    except Exception as e:
        print(f"❌ [Task] Error in background task: {e}")

# ==========================================
# [API Endpoints]
# ==========================================

# 1. SSE Endpoint
@app.get("/events")
async def sse_endpoint(request: Request):
    """
    Server-Sent Events 엔드포인트
    클라이언트는 이 주소에 연결하여 백그라운드 작업 완료 알림을 실시간으로 수신합니다.
    """
    async def event_generator():
        while True:
            # 클라이언트 연결 끊김 확인
            if await request.is_disconnected():
                break

            # 큐에서 메시지가 올 때까지 대기 (비동기)
            try:
                # 큐에서 데이터를 가져옴
                data = await event_queue.get()
                
                # SSE 포맷으로 데이터 전송
                # 한글 깨짐 방지를 위해 ensure_ascii=False 사용
                yield {
                    "event": "message",
                    "data": json.dumps(data, ensure_ascii=False)
                }
                
                # 큐 작업 완료 처리
                event_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"SSE Error: {e}")
                break
                
    return EventSourceResponse(event_generator())

# 2. Existing Chat Endpoints
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    사용자 메시지를 저장하고 응답을 반환합니다.
    '딜레이'가 포함되면 즉시 응답 후 백그라운드 작업을 실행합니다.
    """
    
    # 1. 응답 메시지 결정 & 백그라운드 태스크 등록
    if "딜레이" in request.content:
        response_msg = "⏳ 처리중입니다... (결과는 잠시 후 도착합니다)"
        
        # ✨ [핵심] 응답 리턴 후 실행할 작업을 큐에 등록
        if request.conversation_id:
            background_tasks.add_task(perform_background_task, request.conversation_id)
    else:
        response_msg = f"Echo: {request.content} (Supabase)"

    # 2. DB 저장 로직 (사용자 메시지 + 1차 응답 메시지)
    if request.conversation_id:
        try:
            # (1) 사용자 메시지 저장
            supabase.table("messages").insert({
                "conversation_id": request.conversation_id,
                "role": "user",
                "content": request.content,
                "created_at": get_utc_now()
            }).execute()

            # (2) 봇의 1차 응답(Echo 또는 처리중) 저장
            supabase.table("messages").insert({
                "conversation_id": request.conversation_id,
                "role": "assistant",
                "content": response_msg,
                "created_at": get_utc_now()
            }).execute()
            
            # (3) 대화방 갱신
            supabase.table("conversations").update({
                "updated_at": get_utc_now()
            }).eq("id", request.conversation_id).execute()
            
        except Exception as e:
            print(f"Error saving chat: {e}")

    # 3. 클라이언트에게는 즉시 응답 반환
    return {
        "type": "text",
        "message": response_msg,
        "slots": request.slots or {},
        "next_node": None
    }

@app.get("/conversations", response_model=List[ConversationSummary])
async def get_conversations():
    """모든 대화방 목록 조회 (최신순)"""
    res = supabase.table("conversations").select("*").order("updated_at", desc=True).execute()
    return res.data

@app.post("/conversations", status_code=status.HTTP_201_CREATED, response_model=ConversationSummary)
async def create_conversation(request: CreateConversationRequest):
    """새 대화방 생성"""
    new_title = request.title if request.title else "New Chat"
    
    data = {
        "title": new_title,
        "is_pinned": False,
        "created_at": get_utc_now(),
        "updated_at": get_utc_now()
    }
    
    res = supabase.table("conversations").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create conversation")
    
    return res.data[0]

@app.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation_detail(
    conversation_id: str = Path(...),
    limit: int = Query(50),
    offset: int = Query(0)
):
    """대화방 상세 및 메시지 페이징"""
    conv_res = supabase.table("conversations").select("id").eq("id", conversation_id).execute()
    if not conv_res.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    msg_res = supabase.table("messages")\
        .select("*")\
        .eq("conversation_id", conversation_id)\
        .order("created_at", desc=False)\
        .range(offset, offset + limit - 1)\
        .execute()
        
    return {
        "id": conversation_id,
        "messages": msg_res.data
    }

@app.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
async def update_conversation(conversation_id: str, request: UpdateConversationRequest):
    update_data = {"updated_at": get_utc_now()}
    if request.title is not None:
        update_data["title"] = request.title
    if request.is_pinned is not None:
        update_data["is_pinned"] = request.is_pinned
        
    res = supabase.table("conversations").update(update_data).eq("id", conversation_id).execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return res.data[0]

@app.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str):
    res = supabase.table("conversations").delete().eq("id", conversation_id).execute()
    if not res.data:
         raise HTTPException(status_code=404, detail="Conversation not found")
    return None

# Client Side Static Data
@app.get("/scenarios", response_model=List[ScenarioCategory])
async def get_client_scenarios():
    return [
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


# 2. Admin/Management Endpoints
admin_router = APIRouter(prefix="/api/v1/chat")

@admin_router.get("/scenarios/{tenant_id}/{stage_id}", response_model=ScenarioListResponse)
async def list_admin_scenarios(tenant_id: str, stage_id: str):
    res = supabase.table("admin_scenarios")\
        .select("id, name, job, description, updated_at, last_used_at")\
        .eq("tenant_id", tenant_id)\
        .eq("stage_id", stage_id)\
        .order("updated_at", desc=True)\
        .execute()
    return {"scenarios": res.data}

@admin_router.get("/scenarios/{tenant_id}/{stage_id}/{scenario_id}", response_model=ScenarioDetail)
async def get_admin_scenario_detail(tenant_id: str, stage_id: str, scenario_id: str):
    res = supabase.table("admin_scenarios").select("*").eq("id", scenario_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return res.data[0]

@admin_router.post("/scenarios/{tenant_id}/{stage_id}", status_code=status.HTTP_201_CREATED, response_model=ScenarioDetail)
async def create_admin_scenario(tenant_id: str, stage_id: str, request: CreateScenarioRequest):
    new_data = {
        "tenant_id": tenant_id,
        "stage_id": stage_id,
        "name": request.name,
        "job": request.job,
        "description": request.description,
        "nodes": request.nodes,
        "edges": request.edges,
        "start_node_id": request.start_node_id,
        "category_id": request.category_id,
        "created_at": get_utc_now(),
        "updated_at": get_utc_now(),
        "last_used_at": get_utc_now()
    }
    
    # 복제 로직
    if request.clone_from_id:
        original = supabase.table("admin_scenarios").select("*").eq("id", request.clone_from_id).execute()
        if original.data:
            org = original.data[0]
            new_data["nodes"] = org["nodes"]
            new_data["edges"] = org["edges"]
            new_data["start_node_id"] = org["start_node_id"]
    
    res = supabase.table("admin_scenarios").insert(new_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create scenario")
    return res.data[0]

@admin_router.put("/scenarios/{tenant_id}/{stage_id}/{scenario_id}", response_model=ScenarioDetail)
async def update_admin_scenario(tenant_id: str, stage_id: str, scenario_id: str, request: UpdateScenarioRequest):
    update_data = {
        "name": request.name,
        "job": request.job,
        "description": request.description,
        "nodes": request.nodes,
        "edges": request.edges,
        "start_node_id": request.start_node_id,
        "updated_at": get_utc_now()
    }
    
    res = supabase.table("admin_scenarios").update(update_data).eq("id", scenario_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return res.data[0]

@admin_router.patch("/scenarios/{tenant_id}/{stage_id}/{scenario_id}", response_model=ScenarioListItem)
async def patch_admin_scenario(tenant_id: str, stage_id: str, scenario_id: str, request: PatchScenarioRequest):
    update_data = {"updated_at": get_utc_now()}
    if request.name is not None: update_data["name"] = request.name
    if request.job is not None: update_data["job"] = request.job
    if request.description is not None: update_data["description"] = request.description
    if request.last_used_at is not None: update_data["last_used_at"] = request.last_used_at
    
    res = supabase.table("admin_scenarios").update(update_data).eq("id", scenario_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return res.data[0]

@admin_router.delete("/scenarios/{tenant_id}/{stage_id}/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_scenario(tenant_id: str, stage_id: str, scenario_id: str):
    res = supabase.table("admin_scenarios").delete().eq("id", scenario_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return None

# --- Templates ---
@admin_router.get("/templates/api/{tenant_id}", response_model=List[Dict])
async def list_api_templates(tenant_id: str):
    res = supabase.table("api_templates").select("*").eq("tenant_id", tenant_id).execute()
    return res.data

@admin_router.post("/templates/api/{tenant_id}", status_code=status.HTTP_201_CREATED)
async def create_api_template(tenant_id: str, request: ApiTemplateCreate):
    data = request.model_dump()
    data["tenant_id"] = tenant_id
    res = supabase.table("api_templates").insert(data).execute()
    return res.data[0]

@admin_router.delete("/templates/api/{tenant_id}/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_template(tenant_id: str, template_id: str):
    supabase.table("api_templates").delete().eq("id", template_id).execute()
    return None

@admin_router.get("/templates/form/{tenant_id}", response_model=List[Dict])
async def list_form_templates(tenant_id: str):
    res = supabase.table("form_templates").select("*").eq("tenant_id", tenant_id).execute()
    return res.data

@admin_router.post("/templates/form/{tenant_id}", status_code=status.HTTP_201_CREATED)
async def create_form_template(tenant_id: str, request: FormTemplateCreate):
    data = request.model_dump()
    data["tenant_id"] = tenant_id
    res = supabase.table("form_templates").insert(data).execute()
    return res.data[0]

@admin_router.delete("/templates/form/{tenant_id}/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_form_template(tenant_id: str, template_id: str):
    supabase.table("form_templates").delete().eq("id", template_id).execute()
    return None

# --- Settings ---
@admin_router.get("/settings/{tenant_id}/node_visibility", response_model=NodeVisibilitySettings)
async def get_node_visibility(tenant_id: str):
    res = supabase.table("settings").select("node_visibility").eq("tenant_id", tenant_id).execute()
    if res.data:
        return res.data[0]["node_visibility"]
    return {"visibleNodeTypes": ["message", "form", "api", "branch", "condition"]}

@admin_router.put("/settings/{tenant_id}/node_visibility", response_model=NodeVisibilitySettings)
async def update_node_visibility(tenant_id: str, settings: NodeVisibilitySettings):
    data = {"tenant_id": tenant_id, "node_visibility": settings.model_dump()}
    res = supabase.table("settings").upsert(data).execute()
    return res.data[0]["node_visibility"]

app.include_router(admin_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)