"""
SAM Ultra — Memory & Database Layer
Supabase (PostgreSQL + pgvector) for persistent memory, conversations, facts.
"""
import json
from typing import Optional, Any
from datetime import datetime

from supabase import create_client, Client
from core.config import settings
from core.logging import get_logger
from models.schemas import MemoryFact, ConversationTurn, Message

logger = get_logger("memory.database")

# ── SQL Migrations ─────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Sessions
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    device      TEXT DEFAULT 'web',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW(),
    active_agent TEXT DEFAULT 'conversation',
    metadata    JSONB DEFAULT '{}'
);

-- Conversation turns
CREATE TABLE IF NOT EXISTS conversation_turns (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    device      TEXT DEFAULT 'web',
    agent       TEXT DEFAULT 'conversation',
    model       TEXT DEFAULT '',
    tools_used  TEXT[] DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON conversation_turns(session_id, created_at DESC);

-- Long-term memory facts
CREATE TABLE IF NOT EXISTS memory_facts (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    category    TEXT DEFAULT 'general',
    source      TEXT DEFAULT 'user',
    embedding   vector(1536),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_facts_key ON memory_facts(key);
CREATE INDEX IF NOT EXISTS idx_facts_category ON memory_facts(category);
CREATE INDEX IF NOT EXISTS idx_facts_embedding ON memory_facts USING ivfflat (embedding vector_cosine_ops);

-- Tool execution log
CREATE TABLE IF NOT EXISTS tool_logs (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT,
    tool_name   TEXT NOT NULL,
    arguments   JSONB,
    result      JSONB,
    success     BOOLEAN DEFAULT TRUE,
    duration_ms INT DEFAULT 0,
    permission_level INT DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tool_logs_session ON tool_logs(session_id, created_at DESC);

-- Automations
CREATE TABLE IF NOT EXISTS automations (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    name        TEXT NOT NULL,
    trigger     JSONB NOT NULL,
    actions     JSONB NOT NULL,
    enabled     BOOLEAN DEFAULT TRUE,
    last_run    TIMESTAMPTZ,
    run_count   INT DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
"""


class Database:
    """Supabase database wrapper with all SAM Ultra data operations.
    Falls back to in-memory storage when Supabase is not configured."""

    def __init__(self):
        self._client: Optional[Client] = None
        # In-memory fallback storage
        self._mem_history: dict[str, list[dict]] = {}
        self._mem_facts: dict[str, dict] = {}

    def _get_client(self) -> Optional[Client]:
        if not self._client:
            if not settings.supabase_url or not settings.supabase_service_key:
                return None
            try:
                self._client = create_client(settings.supabase_url, settings.supabase_service_key)
            except Exception as e:
                logger.warning("supabase_init_failed", error=str(e))
                return None
        return self._client

    @property
    def client(self) -> Optional[Client]:
        return self._get_client()

    @property
    def _has_db(self) -> bool:
        return self._get_client() is not None

    # ── Sessions ────────────────────────────────────────────────────────────────

    async def create_session(self, session_id: str, device: str = "web") -> dict:
        if not self._has_db:
            if session_id not in self._mem_history:
                self._mem_history[session_id] = []
            return {"id": session_id, "device": device}
        try:
            resp = self.client.table("sessions").upsert({
                "id": session_id,
                "device": device,
                "last_active": datetime.utcnow().isoformat(),
            }).execute()
            return resp.data[0] if resp.data else {}
        except Exception as e:
            logger.error("create_session_error", error=str(e))
            return {"id": session_id, "device": device}

    async def touch_session(self, session_id: str, active_agent: str = "conversation"):
        if not self._has_db:
            return
        try:
            self.client.table("sessions").update({
                "last_active": datetime.utcnow().isoformat(),
                "active_agent": active_agent,
            }).eq("id", session_id).execute()
        except Exception as e:
            logger.warning("touch_session_error", error=str(e))

    # ── Conversation History ────────────────────────────────────────────────────

    async def save_turn(self, turn: ConversationTurn):
        if not self._has_db:
            sid = turn.session_id
            if sid not in self._mem_history:
                self._mem_history[sid] = []
            self._mem_history[sid].append({"role": turn.role, "content": turn.content})
            # Keep last 50 turns in memory
            if len(self._mem_history[sid]) > 50:
                self._mem_history[sid] = self._mem_history[sid][-50:]
            return
        try:
            data = {
                "session_id": turn.session_id,
                "role": turn.role,
                "content": turn.content,
                "device": turn.device,
                "agent": turn.agent,
                "model": turn.model,
                "tools_used": turn.tools_used,
            }
            self.client.table("conversation_turns").insert(data).execute()
        except Exception as e:
            logger.error("save_turn_error", error=str(e))

    async def get_history(self, session_id: str, limit: int = 20) -> list[dict]:
        if not self._has_db:
            turns = self._mem_history.get(session_id, [])
            return turns[-limit:]
        try:
            resp = (
                self.client.table("conversation_turns")
                .select("role, content, agent, model, created_at")
                .eq("session_id", session_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            rows = resp.data or []
            rows.reverse()
            return rows
        except Exception as e:
            logger.error("get_history_error", error=str(e))
            return []

    async def get_messages(self, session_id: str, limit: int = 20) -> list[Message]:
        rows = await self.get_history(session_id, limit)
        return [Message(role=r["role"], content=r["content"]) for r in rows]

    # ── Memory Facts ────────────────────────────────────────────────────────────

    async def save_fact(self, fact: MemoryFact) -> MemoryFact:
        if not self._has_db:
            self._mem_facts[fact.key] = {"key": fact.key, "value": fact.value, "category": fact.category}
            return fact
        try:
            data = {
                "key": fact.key,
                "value": fact.value,
                "category": fact.category,
                "source": fact.source,
                "updated_at": datetime.utcnow().isoformat(),
            }
            # Upsert by key
            existing = self.client.table("memory_facts").select("id").eq("key", fact.key).execute()
            if existing.data:
                resp = self.client.table("memory_facts").update(data).eq("key", fact.key).execute()
                fact.id = existing.data[0]["id"]
            else:
                resp = self.client.table("memory_facts").insert(data).execute()
                if resp.data:
                    fact.id = resp.data[0]["id"]
            return fact
        except Exception as e:
            logger.error("save_fact_error", error=str(e))
            return fact

    async def get_facts(self, category: Optional[str] = None, limit: int = 100) -> list[MemoryFact]:
        if not self._has_db:
            facts = list(self._mem_facts.values())
            if category:
                facts = [f for f in facts if f.get("category") == category]
            return [MemoryFact(**f) for f in facts[:limit]]
        try:
            q = self.client.table("memory_facts").select("*")
            if category:
                q = q.eq("category", category)
            resp = q.order("updated_at", desc=True).limit(limit).execute()
            return [MemoryFact(**row) for row in (resp.data or [])]
        except Exception as e:
            logger.error("get_facts_error", error=str(e))
            return []

    async def search_facts(self, query: str, limit: int = 10) -> list[MemoryFact]:
        if not self._has_db:
            q = query.lower()
            facts = [f for f in self._mem_facts.values() if q in f["value"].lower() or q in f["key"].lower()]
            return [MemoryFact(**f) for f in facts[:limit]]
        try:
            resp = (
                self.client.table("memory_facts")
                .select("*")
                .ilike("value", f"%{query}%")
                .limit(limit)
                .execute()
            )
            return [MemoryFact(**row) for row in (resp.data or [])]
        except Exception as e:
            logger.error("search_facts_error", error=str(e))
            return []

    async def delete_fact(self, key: str) -> bool:
        if not self._has_db:
            self._mem_facts.pop(key, None)
            return True
        try:
            self.client.table("memory_facts").delete().eq("key", key).execute()
            return True
        except Exception as e:
            logger.error("delete_fact_error", error=str(e))
            return False

    async def build_memory_context(self, session_id: str, user_message: str) -> str:
        facts = await self.get_facts(limit=30)
        if not facts:
            return ""
        lines = ["[MEMORY]"]
        for f in facts:
            lines.append(f"- {f.key}: {f.value}")
        return "\n".join(lines)

    # ── Tool Logs ───────────────────────────────────────────────────────────────

    async def log_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict,
        result: Any,
        success: bool,
        duration_ms: int,
        permission_level: int,
    ):
        if not self._has_db:
            return
        try:
            self.client.table("tool_logs").insert({
                "session_id": session_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "result": result if isinstance(result, dict) else {"value": str(result)},
                "success": success,
                "duration_ms": duration_ms,
                "permission_level": permission_level,
            }).execute()
        except Exception as e:
            logger.warning("log_tool_error", error=str(e))

    # ── Automations ─────────────────────────────────────────────────────────────

    async def get_automations(self, enabled_only: bool = True) -> list[dict]:
        try:
            q = self.client.table("automations").select("*")
            if enabled_only:
                q = q.eq("enabled", True)
            resp = q.execute()
            return resp.data or []
        except Exception as e:
            logger.error("get_automations_error", error=str(e))
            return []

    async def save_automation(self, automation: dict) -> dict:
        try:
            resp = self.client.table("automations").upsert(automation).execute()
            return resp.data[0] if resp.data else automation
        except Exception as e:
            logger.error("save_automation_error", error=str(e))
            return automation


# Singleton
_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db
