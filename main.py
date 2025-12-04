import os
from fastapi import FastAPI, HTTPException, status, Query, Path, Body, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from uuid import uuid4
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client

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
    "http://localhost:3000", # Next.js 기본 포트
    "http://localhost:5173", # Vite 기본 포트
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "https://clt-chatbot.vercel.app",
    "https://react-flow-three-ecru.vercel.app",
    "http://202.20.84.65:10000",
    "http://202.20.84.65:10001"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# 3. Client Scenarios (이 부분은 정적 데이터로 유지하거나 별도 테이블로 뺄 수 있음)
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
    nodes: List[Dict[str, Any]] = [] # JSONB 호환
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
# [API Endpoints]
# ==========================================

# 1. Existing Chat Endpoints (Supabase Integrated)
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    사용자 메시지를 저장하고 에코 응답을 생성하여 저장합니다.
    """
    response_msg = f"Echo: {request.content} (Supabase)"
    
    if request.conversation_id:
        # 1. 사용자 메시지 DB 저장
        try:
            supabase.table("messages").insert({
                "conversation_id": request.conversation_id,
                "role": "user",
                "content": request.content,
                "created_at": get_utc_now()
            }).execute()

            # 2. 봇 메시지 DB 저장
            supabase.table("messages").insert({
                "conversation_id": request.conversation_id,
                "role": "assistant",
                "content": response_msg,
                "created_at": get_utc_now()
            }).execute()
            
            # 3. 대화방 updated_at 갱신
            supabase.table("conversations").update({
                "updated_at": get_utc_now()
            }).eq("id", request.conversation_id).execute()
            
        except Exception as e:
            print(f"Error saving chat: {e}")
            # 실제 운영시엔 에러 처리 필요, 여기선 진행

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
    # 대화방 존재 확인
    conv_res = supabase.table("conversations").select("id").eq("id", conversation_id).execute()
    if not conv_res.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # 메시지 조회 (Paging)
    # Supabase range is 0-indexed inclusive
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
    # Cascade delete가 설정되어 있다면 메시지도 자동 삭제됨
    res = supabase.table("conversations").delete().eq("id", conversation_id).execute()
    if not res.data:
         raise HTTPException(status_code=404, detail="Conversation not found")
    return None

# Client Side Static Data (이 부분은 보통 하드코딩 유지하거나 별도 테이블 생성)
@app.get("/scenarios", response_model=List[ScenarioCategory])
async def get_client_scenarios():
    # 간단한 예시로 하드코딩 유지. 필요시 'scenario_categories' 테이블 연동
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


# 2. Admin/Management Endpoints (Supabase Integrated)
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
    return {"visibleNodeTypes": ["message", "form", "api", "branch", "condition"]} # Default

@admin_router.put("/settings/{tenant_id}/node_visibility", response_model=NodeVisibilitySettings)
async def update_node_visibility(tenant_id: str, settings: NodeVisibilitySettings):
    data = {"tenant_id": tenant_id, "node_visibility": settings.model_dump()}
    # Upsert (Insert or Update)
    res = supabase.table("settings").upsert(data).execute()
    return res.data[0]["node_visibility"]

app.include_router(admin_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)