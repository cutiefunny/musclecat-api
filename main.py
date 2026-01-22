import asyncio
import os
import json
from fastapi import FastAPI, BackgroundTasks, HTTPException, status, Query, Path, Body, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from uuid import uuid4
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client
from sse_starlette.sse import EventSourceResponse

# 환경 변수 로드
load_dotenv()

# Supabase 클라이언트 초기화
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Warning: SUPABASE_URL or SUPABASE_KEY is missing in .env file.")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Failed to initialize Supabase client: {e}")
    supabase = None

app = FastAPI(
    title="CLT Chatbot API (Supabase Integration)",
    description="API connected to Supabase for CLT Chatbot",
    version="1.3.0"
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

event_queue = asyncio.Queue()

# ==========================================
# [Models]
# ==========================================

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

# 3. Client Scenarios (Shortcuts) Models
class Action(BaseModel):
    type: str
    value: Optional[str] = ""

class ShortcutItem(BaseModel):
    title: str
    description: Optional[str] = None
    action: Optional[Action] = None
    id: Optional[str] = None 

class ShortcutSubCategory(BaseModel):
    title: str
    items: List[ShortcutItem] = []

class ShortcutCategory(BaseModel):
    name: str 
    subCategories: List[ShortcutSubCategory] = []
    items: List[ShortcutItem] = []

# 4. Admin & Scenario Editor Models
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

# [추가됨] 시나리오 세션 생성 요청 바디
class CreateSessionRequest(BaseModel):
    scenarioId: str
    slots: Optional[Dict[str, Any]] = None


# ==========================================
# [Helpers]
# ==========================================
def get_utc_now():
    return datetime.now(timezone.utc).isoformat()

# ==========================================
# [Background Tasks]
# ==========================================
async def perform_background_task(conversation_id: str):
    print(f"⏳ [Task] 비동기 작업 시작 (ID: {conversation_id})")
    await asyncio.sleep(5) 
    
    success_msg = "✅ 처리 완료 (5초 후 생성됨)"
    
    try:
        supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": success_msg,
            "created_at": get_utc_now()
        }).execute()
        
        supabase.table("conversations").update({
            "updated_at": get_utc_now()
        }).eq("id", conversation_id).execute()
        
        print(f"✅ [Task] 비동기 작업 완료 및 DB 저장 (ID: {conversation_id})")
        
        await event_queue.put({
            "conversation_id": conversation_id,
            "status": "done",
            "message": success_msg,
            "timestamp": get_utc_now()
        })
        
    except Exception as e:
        print(f"❌ [Task] Error in background task: {e}")

# ==========================================
# [API Endpoints]
# ==========================================

# 1. SSE Endpoint
@app.get("/events")
async def sse_endpoint(request: Request):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                data = await event_queue.get()
                yield {
                    "event": "message",
                    "data": json.dumps(data, ensure_ascii=False)
                }
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
    # 간이 챗봇 로직 (테스트용)
    if "딜레이" in request.content:
        response_msg = "⏳ 처리중입니다..."
        if request.conversation_id:
            background_tasks.add_task(perform_background_task, request.conversation_id)
    else:
        response_msg = f"Echo: {request.content} (Supabase)"

    if request.conversation_id:
        try:
            supabase.table("messages").insert({
                "conversation_id": request.conversation_id,
                "role": "user",
                "content": request.content,
                "created_at": get_utc_now()
            }).execute()

            supabase.table("messages").insert({
                "conversation_id": request.conversation_id,
                "role": "assistant",
                "content": response_msg,
                "created_at": get_utc_now()
            }).execute()
            
            supabase.table("conversations").update({
                "updated_at": get_utc_now()
            }).eq("id", request.conversation_id).execute()
            
        except Exception as e:
            print(f"Error saving chat: {e}")

    return {
        "type": "text",
        "message": response_msg,
        "slots": request.slots or {},
        "next_node": None
    }

# --- Conversations ---

@app.get("/conversations", response_model=List[ConversationSummary])
async def get_conversations():
    res = supabase.table("conversations").select("*").order("updated_at", desc=True).execute()
    return res.data

@app.post("/conversations", status_code=status.HTTP_201_CREATED, response_model=ConversationSummary)
async def create_conversation(request: CreateConversationRequest):
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

@app.post("/conversations/{conversation_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str):
    res = supabase.table("conversations").delete().eq("id", conversation_id).execute()
    if not res.data:
         raise HTTPException(status_code=404, detail="Conversation not found")
    return None

# --- [추가됨] Scenario Sessions ---

@app.post("/conversations/{conversation_id}/sessions", status_code=status.HTTP_201_CREATED)
async def create_scenario_session(conversation_id: str, request: CreateSessionRequest):
    """
    시나리오 세션을 생성합니다. (404 오류 해결용)
    """
    # 실제로는 'scenario_sessions' 테이블에 저장해야 하지만, 
    # 현재 단계에서는 세션 ID만 발급하여 프론트엔드 흐름을 유지합니다.
    session_id = str(uuid4())
    
    # (선택) 여기에 세션 생성 DB 로직 추가 가능
    
    return {
        "sessionId": session_id,
        "conversationId": conversation_id,
        "scenarioId": request.scenarioId,
        "status": "active"
    }

# 2. Scenarios / Shortcuts

@app.get("/scenarios", response_model=List[ShortcutCategory])
async def get_client_scenarios():
    """클라이언트용 숏컷(시나리오 카테고리) 목록 조회"""
    try:
        res = supabase.table("shortcuts").select("content").eq("id", 1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]["content"]
    except Exception as e:
        print(f"Error fetching shortcuts from DB: {e}")
    return []

@app.post("/scenarios", status_code=status.HTTP_201_CREATED)
async def save_client_scenarios(scenarios: List[ShortcutCategory]):
    """클라이언트용 숏컷 저장"""
    data = {
        "id": 1,
        "content": [s.model_dump() for s in scenarios],
        "updated_at": get_utc_now()
    }
    res = supabase.table("shortcuts").upsert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to save scenarios")
    return {"status": "success", "data": res.data}

@app.get("/scenarios/list")
async def get_real_scenario_list():
    """숏컷 에디터용: 실제 DB에 존재하는 시나리오 ID와 이름 목록 반환"""
    try:
        # admin_scenarios 테이블에서 id, name 조회
        res = supabase.table("admin_scenarios").select("id, name").execute()
        return res.data 
    except Exception as e:
        print(f"Error fetching scenario list: {e}")
        return []

# --- Admin/Management Endpoints ---

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

@admin_router.post("/scenarios/{tenant_id}/{stage_id}/{scenario_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
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

@admin_router.post("/templates/api/{tenant_id}/{template_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
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

@admin_router.post("/templates/form/{tenant_id}/{template_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
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