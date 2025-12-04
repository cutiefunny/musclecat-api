from fastapi import FastAPI, HTTPException, status, Query, Path, Body, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from uuid import uuid4
from datetime import datetime, timezone

app = FastAPI(
    title="CLT Chatbot API (Mock)",
    description="Mock API for CLT Chatbot Frontend Development",
    version="1.1.0"
)

# --- CORS 설정 (프론트엔드 연동을 위해 필수) ---
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
# [Existing] Chat Client Models & Logic
# ==========================================

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

# 3. Client Side Scenario Models (기존)
class ScenarioItem(BaseModel):
    id: str
    title: str
    description: str

class ScenarioCategory(BaseModel):
    category: str
    items: List[ScenarioItem]


# ==========================================
# [New] Admin / Management API Models
# ==========================================

# --- Common Structures ---
class NodePosition(BaseModel):
    x: float
    y: float

class Node(BaseModel):
    id: str
    type: str  # e.g., "message", "form", "api"
    position: NodePosition
    data: Dict[str, Any] = {}
    width: Optional[float] = None
    height: Optional[float] = None

class Edge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = None

# --- Scenario Management Models ---
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
    nodes: List[Node] = []
    edges: List[Edge] = []
    start_node_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None

class CreateScenarioRequest(BaseModel):
    name: str
    job: Optional[str] = "Process"
    description: Optional[str] = ""
    category_id: Optional[str] = None
    nodes: List[Node] = []
    edges: List[Edge] = []
    start_node_id: Optional[str] = None
    clone_from_id: Optional[str] = None # 복제 시 사용

class UpdateScenarioRequest(BaseModel):
    # API 명세에 있는 ten_id, stg_id 등은 Path 파라미터로 받지만 Body에도 포함될 수 있음
    ten_id: Optional[str] = None
    stg_id: Optional[str] = None
    category_id: Optional[str] = None
    name: str
    job: str
    description: Optional[str] = None
    nodes: List[Node]
    edges: List[Edge]
    start_node_id: Optional[str] = None

class PatchScenarioRequest(BaseModel):
    name: Optional[str] = None
    job: Optional[str] = None
    description: Optional[str] = None
    last_used_at: Optional[datetime] = None

class ScenarioListResponse(BaseModel):
    scenarios: List[ScenarioListItem]

# --- Template Models ---
class ApiTemplateCreate(BaseModel):
    name: str
    method: str = "GET"
    url: str
    headers: Optional[Union[str, Dict]] = "{}"
    body: Optional[Union[str, Dict]] = "{}"
    responseMapping: List[Any] = []

class ApiTemplate(ApiTemplateCreate):
    id: str

class FormTemplateCreate(BaseModel):
    name: str
    title: str
    elements: List[Any] = []

class FormTemplate(FormTemplateCreate):
    id: str

# --- Settings Models ---
class NodeVisibilitySettings(BaseModel):
    visibleNodeTypes: List[str]


# ==========================================
# [In-Memory Mock Data Store]
# ==========================================

# 1. Existing Client Chat Data
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

MOCK_MESSAGES: Dict[str, List[Dict]] = {
    "uuid-1": [
        {"id": "msg-1", "role": "user", "content": "안녕?", "created_at": datetime.now(timezone.utc)},
        {"id": "msg-2", "role": "assistant", "content": "안녕하세요! 무엇을 도와드릴까요?", "created_at": datetime.now(timezone.utc)}
    ],
    "uuid-2": []
}

MOCK_SCENARIOS_CLIENT = [
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

# 2. New Admin/Management Data
# 관리자용 시나리오 DB
MOCK_ADMIN_SCENARIOS: List[Dict] = [
    {
        "id": "scen-1",
        "name": "예약 시나리오",
        "job": "Process",
        "description": "사용자 예약을 처리하는 메인 흐름",
        "nodes": [
            {
                "id": "node-1", "type": "message", 
                "position": {"x": 100, "y": 100}, 
                "data": {"content": "안녕하세요, 예약을 도와드릴까요?"},
                "width": 200, "height": 100
            },
            {
                "id": "node-2", "type": "form",
                "position": {"x": 400, "y": 100},
                "data": {"schema": {}},
                "width": 300, "height": 200
            }
        ],
        "edges": [
            {"id": "edge-1", "source": "node-1", "target": "node-2"}
        ],
        "start_node_id": "node-1",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "last_used_at": datetime.now(timezone.utc)
    }
]

# 템플릿 DB
MOCK_API_TEMPLATES: List[Dict] = []
MOCK_FORM_TEMPLATES: List[Dict] = []

# 설정 DB (Tenant ID를 키로 사용)
MOCK_SETTINGS: Dict[str, Dict] = {
    "default": {
        "visibleNodeTypes": ["message", "form", "api", "branch", "condition"]
    }
}


# ==========================================
# [API Endpoints]
# ==========================================

# 1. Existing Chat Endpoints
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    response_msg = f"Echo: {request.content} (Mock Response)"
    if request.conversation_id and request.conversation_id in MOCK_MESSAGES:
        MOCK_MESSAGES[request.conversation_id].append({
            "id": str(uuid4()), "role": "user", "content": request.content, "created_at": datetime.now(timezone.utc)
        })
        MOCK_MESSAGES[request.conversation_id].append({
            "id": str(uuid4()), "role": "assistant", "content": response_msg, "created_at": datetime.now(timezone.utc)
        })
    
    return {"type": "text", "message": response_msg, "slots": request.slots or {}, "next_node": None}

@app.get("/conversations", response_model=List[ConversationSummary])
async def get_conversations():
    return MOCK_CONVERSATIONS

@app.post("/conversations", status_code=status.HTTP_201_CREATED, response_model=ConversationSummary)
async def create_conversation(request: CreateConversationRequest):
    new_id = str(uuid4())
    new_title = request.title if request.title else "New Chat"
    now = datetime.now(timezone.utc)
    new_conv = {"id": new_id, "title": new_title, "is_pinned": False, "created_at": now, "updated_at": now}
    MOCK_CONVERSATIONS.insert(0, new_conv)
    MOCK_MESSAGES[new_id] = []
    return new_conv

@app.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation_detail(conversation_id: str = Path(...), limit: int = Query(50), offset: int = Query(0)):
    if conversation_id not in MOCK_MESSAGES:
        raise HTTPException(status_code=404, detail="Conversation not found")
    sliced = MOCK_MESSAGES[conversation_id][offset:offset+limit]
    return {"id": conversation_id, "messages": sliced}

@app.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
async def update_conversation(conversation_id: str, request: UpdateConversationRequest):
    target_conv = next((c for c in MOCK_CONVERSATIONS if c["id"] == conversation_id), None)
    if not target_conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if request.title is not None: target_conv["title"] = request.title
    if request.is_pinned is not None: target_conv["is_pinned"] = request.is_pinned
    target_conv["updated_at"] = datetime.now(timezone.utc)
    return target_conv

@app.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str):
    global MOCK_CONVERSATIONS
    initial_len = len(MOCK_CONVERSATIONS)
    MOCK_CONVERSATIONS = [c for c in MOCK_CONVERSATIONS if c["id"] != conversation_id]
    if len(MOCK_CONVERSATIONS) == initial_len:
         raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation_id in MOCK_MESSAGES: del MOCK_MESSAGES[conversation_id]
    return None

@app.get("/scenarios", response_model=List[ScenarioCategory])
async def get_client_scenarios():
    return MOCK_SCENARIOS_CLIENT


# 2. NEW Admin/Management Endpoints
# 문서의 Base URL: /api/v1/chat
admin_router = APIRouter(prefix="/api/v1/chat")

# --- Scenarios ---
@admin_router.get("/scenarios/{tenant_id}/{stage_id}", response_model=ScenarioListResponse)
async def list_admin_scenarios(tenant_id: str, stage_id: str):
    """전체 시나리오 목록 조회"""
    # Mock: tenant_id, stage_id 구분 없이 모든 Mock 데이터 반환
    return {"scenarios": MOCK_ADMIN_SCENARIOS}

@admin_router.get("/scenarios/{tenant_id}/{stage_id}/{scenario_id}", response_model=ScenarioDetail)
async def get_admin_scenario_detail(tenant_id: str, stage_id: str, scenario_id: str):
    """특정 시나리오 상세 조회"""
    scenario = next((s for s in MOCK_ADMIN_SCENARIOS if s["id"] == scenario_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario

@admin_router.post("/scenarios/{tenant_id}/{stage_id}", status_code=status.HTTP_201_CREATED, response_model=ScenarioDetail)
async def create_admin_scenario(tenant_id: str, stage_id: str, request: CreateScenarioRequest):
    """시나리오 생성 및 복제"""
    new_id = str(uuid4())
    now = datetime.now(timezone.utc)
    
    new_scenario = {
        "id": new_id,
        "name": request.name,
        "job": request.job,
        "description": request.description,
        "nodes": [],
        "edges": [],
        "start_node_id": None,
        "created_at": now,
        "updated_at": now,
        "last_used_at": now
    }
    
    # 복제 로직
    if request.clone_from_id:
        original = next((s for s in MOCK_ADMIN_SCENARIOS if s["id"] == request.clone_from_id), None)
        if original:
            new_scenario["nodes"] = original["nodes"]
            new_scenario["edges"] = original["edges"]
            new_scenario["start_node_id"] = original["start_node_id"]
    else:
        new_scenario["nodes"] = request.nodes
        new_scenario["edges"] = request.edges
        new_scenario["start_node_id"] = request.start_node_id
        
    MOCK_ADMIN_SCENARIOS.append(new_scenario)
    return new_scenario

@admin_router.put("/scenarios/{tenant_id}/{stage_id}/{scenario_id}", response_model=ScenarioDetail)
async def update_admin_scenario(tenant_id: str, stage_id: str, scenario_id: str, request: UpdateScenarioRequest):
    """시나리오 전체 수정 (저장)"""
    scenario = next((s for s in MOCK_ADMIN_SCENARIOS if s["id"] == scenario_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    scenario.update({
        "name": request.name,
        "job": request.job,
        "description": request.description,
        "nodes": [n.model_dump() for n in request.nodes],
        "edges": [e.model_dump() for e in request.edges],
        "start_node_id": request.start_node_id,
        "updated_at": datetime.now(timezone.utc)
    })
    return scenario

@admin_router.patch("/scenarios/{tenant_id}/{stage_id}/{scenario_id}", response_model=ScenarioListItem)
async def patch_admin_scenario(tenant_id: str, stage_id: str, scenario_id: str, request: PatchScenarioRequest):
    """시나리오 부분 수정 (이름/설명 또는 최근 사용시간)"""
    scenario = next((s for s in MOCK_ADMIN_SCENARIOS if s["id"] == scenario_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
        
    if request.name is not None: scenario["name"] = request.name
    if request.job is not None: scenario["job"] = request.job
    if request.description is not None: scenario["description"] = request.description
    if request.last_used_at is not None: scenario["last_used_at"] = request.last_used_at
    
    scenario["updated_at"] = datetime.now(timezone.utc)
    return scenario

@admin_router.delete("/scenarios/{tenant_id}/{stage_id}/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_scenario(tenant_id: str, stage_id: str, scenario_id: str):
    """시나리오 삭제"""
    global MOCK_ADMIN_SCENARIOS
    initial_len = len(MOCK_ADMIN_SCENARIOS)
    MOCK_ADMIN_SCENARIOS = [s for s in MOCK_ADMIN_SCENARIOS if s["id"] != scenario_id]
    if len(MOCK_ADMIN_SCENARIOS) == initial_len:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return None

# --- Templates (API) ---
@admin_router.get("/templates/api/{tenant_id}", response_model=List[ApiTemplate])
async def list_api_templates(tenant_id: str):
    return MOCK_API_TEMPLATES

@admin_router.post("/templates/api/{tenant_id}", status_code=status.HTTP_201_CREATED, response_model=ApiTemplate)
async def create_api_template(tenant_id: str, request: ApiTemplateCreate):
    new_tmpl = request.model_dump()
    new_tmpl["id"] = str(uuid4())
    MOCK_API_TEMPLATES.append(new_tmpl)
    return new_tmpl

@admin_router.delete("/templates/api/{tenant_id}/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_template(tenant_id: str, template_id: str):
    global MOCK_API_TEMPLATES
    MOCK_API_TEMPLATES = [t for t in MOCK_API_TEMPLATES if t["id"] != template_id]
    return None

# --- Templates (Form) ---
@admin_router.get("/templates/form/{tenant_id}", response_model=List[FormTemplate])
async def list_form_templates(tenant_id: str):
    return MOCK_FORM_TEMPLATES

@admin_router.post("/templates/form/{tenant_id}", status_code=status.HTTP_201_CREATED, response_model=FormTemplate)
async def create_form_template(tenant_id: str, request: FormTemplateCreate):
    new_tmpl = request.model_dump()
    new_tmpl["id"] = str(uuid4())
    MOCK_FORM_TEMPLATES.append(new_tmpl)
    return new_tmpl

@admin_router.delete("/templates/form/{tenant_id}/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_form_template(tenant_id: str, template_id: str):
    global MOCK_FORM_TEMPLATES
    MOCK_FORM_TEMPLATES = [t for t in MOCK_FORM_TEMPLATES if t["id"] != template_id]
    return None

# --- Settings ---
@admin_router.get("/settings/{tenant_id}/node_visibility", response_model=NodeVisibilitySettings)
async def get_node_visibility(tenant_id: str):
    # Tenant별 설정이 없으면 default 반환
    return MOCK_SETTINGS.get(tenant_id, MOCK_SETTINGS["default"])

@admin_router.put("/settings/{tenant_id}/node_visibility", response_model=NodeVisibilitySettings)
async def update_node_visibility(tenant_id: str, settings: NodeVisibilitySettings):
    MOCK_SETTINGS[tenant_id] = settings.model_dump()
    return MOCK_SETTINGS[tenant_id]

# 라우터 등록
app.include_router(admin_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)