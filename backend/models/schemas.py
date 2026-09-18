"""
JARVIS data models and schemas.
"""
from pydantic import BaseModel, Field
from typing import Optional, Any, Literal
from datetime import datetime
from enum import IntEnum
import uuid


# ── Permission Levels ─────────────────────────────────────────────────────────

class PermissionLevel(IntEnum):
    CONVERSATION = 0   # Normal chat
    READ = 1           # Read files, calendar, device state
    LOW_RISK = 2       # Open apps, control lights, play music
    SENSITIVE = 3      # Send messages, modify files, change settings
    DESTRUCTIVE = 4    # Delete files, privileged commands, financial


# ── Emotion State ─────────────────────────────────────────────────────────────

class EmotionEstimate(BaseModel):
    mood: str = "neutral"
    confidence: float = 0.0
    evidence: list[str] = []
    disabled: bool = False


# ── Messages ──────────────────────────────────────────────────────────────────

class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    device: str = "web"
    stream: bool = True
    emotion_detection: bool = True
    voice_input: bool = False


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    model: str
    agent: str = "conversation"
    tools_used: list[str] = []
    emotion: Optional[EmotionEstimate] = None
    permission_required: Optional[int] = None


# ── Streaming Events ──────────────────────────────────────────────────────────

class StreamEvent(BaseModel):
    type: Literal[
        "token", "tool_start", "tool_end", "agent_switch",
        "model", "emotion", "permission_request", "done", "error"
    ]
    data: Any = None


# ── Memory ────────────────────────────────────────────────────────────────────

class MemoryFact(BaseModel):
    id: Optional[str] = None
    key: str
    value: str
    category: str = "general"
    source: str = "user"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ConversationTurn(BaseModel):
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    device: str = "web"
    agent: str = "conversation"
    model: str = ""
    tools_used: list[str] = []
    created_at: Optional[datetime] = None


# ── Tools ─────────────────────────────────────────────────────────────────────

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    permission_level: PermissionLevel = PermissionLevel.LOW_RISK
    requires_confirmation: bool = False
    source: str = "builtin"   # builtin | mcp | custom
    mcp_server: Optional[str] = None
    enabled: bool = True
    timeout_seconds: int = 30
    risk_classification: str = "low"  # low | medium | high | critical


class ToolCall(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    arguments: dict[str, Any]
    permission_level: PermissionLevel
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ToolResult(BaseModel):
    tool_call_id: str
    tool_name: str
    success: bool
    result: Any
    error: Optional[str] = None
    duration_ms: int = 0


# ── MCP ───────────────────────────────────────────────────────────────────────

class MCPServerConfig(BaseModel):
    id: str
    name: str
    description: str
    transport: Literal["stdio", "sse", "http"] = "stdio"
    command: Optional[str] = None  # for stdio
    url: Optional[str] = None      # for sse/http
    args: list[str] = []
    env: dict[str, str] = {}
    enabled: bool = True
    auto_start: bool = True


# ── Agents ────────────────────────────────────────────────────────────────────

class AgentType(str):
    CONVERSATION = "conversation"
    RESEARCH = "research"
    COMPUTER = "computer"
    SMART_HOME = "smart_home"
    AUTOMATION = "automation"
    CALENDAR = "calendar"
    COMMUNICATION = "communication"
    MUSIC = "music"
    FILE = "file"
    CODING = "coding"
    MONITORING = "monitoring"
    MEMORY = "memory"
    SECURITY = "security"


class AgentContext(BaseModel):
    session_id: str
    user_message: str
    history: list[Message] = []
    memory_context: str = ""
    emotion: Optional[EmotionEstimate] = None
    device: str = "web"
    active_agent: str = "conversation"


# ── Sessions ──────────────────────────────────────────────────────────────────

class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device: str = "web"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    active_agent: str = "conversation"


# ── System Status ─────────────────────────────────────────────────────────────

class SystemStatus(BaseModel):
    status: str = "online"
    version: str = "1.0.0"
    ai_provider: str = "groq"
    active_sessions: int = 0
    mcp_servers: dict[str, str] = {}  # name -> status
    uptime_seconds: float = 0
