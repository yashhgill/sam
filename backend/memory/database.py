"""
SAM Ultra — Memory & Database Layer

Priority:
1. Supabase (PostgreSQL) if configured and reachable
2. SQLite on disk (persistent across restarts, no external deps)
3. In-memory (last resort, resets on restart)
"""
import json
import sqlite3
import os
from typing import Optional, Any
from datetime import datetime
from pathlib import Path

from core.config import settings
from core.logging import get_logger
from models.schemas import MemoryFact, ConversationTurn, Message

logger = get_logger("memory.database")

# SQLite DB — use /data when running in Docker, otherwise next to backend/
_docker_data = Path("/data")
SQLITE_PATH = (_docker_data / "sam_memory.db") if _docker_data.exists() else (Path(__file__).parent.parent / "sam_memory.db")


# ── SQL Migrations (Supabase/PostgreSQL) ───────────────────────────────────────

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    device      TEXT DEFAULT 'web',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW(),
    active_agent TEXT DEFAULT 'conversation',
    metadata    JSONB DEFAULT '{}'
);

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

CREATE TABLE IF NOT EXISTS memory_facts (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    category    TEXT DEFAULT 'general',
    source      TEXT DEFAULT 'user',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_facts_key ON memory_facts(key);
CREATE INDEX IF NOT EXISTS idx_facts_category ON memory_facts(category);

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
"""

# ── SQLite Schema ──────────────────────────────────────────────────────────────

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    device      TEXT DEFAULT 'web',
    created_at  TEXT DEFAULT (datetime('now')),
    last_active TEXT DEFAULT (datetime('now')),
    active_agent TEXT DEFAULT 'conversation'
);

CREATE TABLE IF NOT EXISTS conversation_turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    device      TEXT DEFAULT 'web',
    agent       TEXT DEFAULT 'conversation',
    model       TEXT DEFAULT '',
    tools_used  TEXT DEFAULT '[]',
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON conversation_turns(session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS memory_facts (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    key         TEXT NOT NULL UNIQUE,
    value       TEXT NOT NULL,
    category    TEXT DEFAULT 'general',
    source      TEXT DEFAULT 'user',
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
"""


class SQLiteStore:
    """SQLite-backed persistent storage. No external deps, works offline."""

    def __init__(self, path: Path):
        self.path = path
        self._conn: Optional[sqlite3.Connection] = None
        self._init()

    def _init(self):
        try:
            self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(SQLITE_SCHEMA)
            self._conn.commit()
            logger.info("sqlite_ready", path=str(self.path))
        except Exception as e:
            logger.error("sqlite_init_failed", error=str(e))
            self._conn = None

    def execute(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Cursor]:
        if not self._conn:
            return None
        try:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur
        except Exception as e:
            logger.error("sqlite_execute_error", error=str(e), sql=sql[:80])
            return None

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        if not self._conn:
            return []
        try:
            cur = self._conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error("sqlite_fetch_error", error=str(e))
            return []

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[dict]:
        rows = self.fetchall(sql, params)
        return rows[0] if rows else None


class Database:
    """
    SAM memory layer. Uses Supabase if available, SQLite otherwise.
    In-memory dict is last resort (only if SQLite also fails).
    """

    def __init__(self):
        self._supa: Optional[Any] = None
        self._sqlite: Optional[SQLiteStore] = None
        self._mem_history: dict[str, list[dict]] = {}
        self._mem_facts: dict[str, dict] = {}

        # Init SQLite (always, as primary local store)
        try:
            self._sqlite = SQLiteStore(SQLITE_PATH)
        except Exception as e:
            logger.warning("sqlite_unavailable", error=str(e))

        # Try Supabase
        if settings.supabase_url and settings.supabase_service_key:
            try:
                from supabase import create_client
                self._supa = create_client(settings.supabase_url, settings.supabase_service_key)
                logger.info("supabase_connected")
            except Exception as e:
                logger.warning("supabase_init_failed", error=str(e))

    @property
    def _has_supa(self) -> bool:
        return self._supa is not None

    @property
    def _has_sqlite(self) -> bool:
        return self._sqlite is not None and self._sqlite._conn is not None

    # ── Sessions ────────────────────────────────────────────────────────────────

    async def create_session(self, session_id: str, device: str = "web") -> dict:
        if self._has_supa:
            try:
                self._supa.table("sessions").upsert({
                    "id": session_id, "device": device,
                    "last_active": datetime.utcnow().isoformat()
                }).execute()
                return {"id": session_id}
            except Exception as e:
                logger.warning("supa_session_error", error=str(e))

        if self._has_sqlite:
            self._sqlite.execute(
                "INSERT OR IGNORE INTO sessions (id, device) VALUES (?, ?)",
                (session_id, device)
            )

        if session_id not in self._mem_history:
            self._mem_history[session_id] = []
        return {"id": session_id}

    async def touch_session(self, session_id: str, active_agent: str = "conversation"):
        if self._has_supa:
            try:
                self._supa.table("sessions").update({
                    "last_active": datetime.utcnow().isoformat(),
                    "active_agent": active_agent,
                }).eq("id", session_id).execute()
                return
            except Exception:
                pass
        if self._has_sqlite:
            self._sqlite.execute(
                "UPDATE sessions SET last_active=datetime('now'), active_agent=? WHERE id=?",
                (active_agent, session_id)
            )

    # ── Conversation History ────────────────────────────────────────────────────

    async def save_turn(self, turn: ConversationTurn):
        if self._has_supa:
            try:
                self._supa.table("conversation_turns").insert({
                    "session_id": turn.session_id,
                    "role": turn.role,
                    "content": turn.content,
                    "device": turn.device,
                    "agent": turn.agent,
                    "model": turn.model,
                    "tools_used": turn.tools_used,
                }).execute()
                return
            except Exception as e:
                logger.warning("supa_save_turn_error", error=str(e))

        if self._has_sqlite:
            self._sqlite.execute(
                "INSERT INTO conversation_turns (session_id, role, content, device, agent, model, tools_used) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (turn.session_id, turn.role, turn.content, turn.device,
                 turn.agent, turn.model, json.dumps(turn.tools_used))
            )
            return

        # Fallback in-memory
        sid = turn.session_id
        if sid not in self._mem_history:
            self._mem_history[sid] = []
        self._mem_history[sid].append({"role": turn.role, "content": turn.content})
        if len(self._mem_history[sid]) > 100:
            self._mem_history[sid] = self._mem_history[sid][-100:]

    async def get_history(self, session_id: str, limit: int = 20) -> list[dict]:
        if self._has_supa:
            try:
                resp = (
                    self._supa.table("conversation_turns")
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
                logger.warning("supa_get_history_error", error=str(e))

        if self._has_sqlite:
            rows = self._sqlite.fetchall(
                "SELECT role, content, agent, model, created_at FROM conversation_turns WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit)
            )
            rows.reverse()
            return rows

        turns = self._mem_history.get(session_id, [])
        return turns[-limit:]

    async def get_messages(self, session_id: str, limit: int = 20) -> list[Message]:
        rows = await self.get_history(session_id, limit)
        return [Message(role=r["role"], content=r["content"]) for r in rows]

    # ── Memory Facts ────────────────────────────────────────────────────────────

    async def save_fact(self, fact: MemoryFact) -> MemoryFact:
        if self._has_supa:
            try:
                data = {
                    "key": fact.key, "value": fact.value,
                    "category": fact.category, "source": fact.source,
                    "updated_at": datetime.utcnow().isoformat(),
                }
                existing = self._supa.table("memory_facts").select("id").eq("key", fact.key).execute()
                if existing.data:
                    self._supa.table("memory_facts").update(data).eq("key", fact.key).execute()
                else:
                    resp = self._supa.table("memory_facts").insert(data).execute()
                    if resp.data:
                        fact.id = resp.data[0]["id"]
                return fact
            except Exception as e:
                logger.warning("supa_save_fact_error", error=str(e))

        if self._has_sqlite:
            self._sqlite.execute(
                "INSERT INTO memory_facts (key, value, category, source) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, category=excluded.category, updated_at=datetime('now')",
                (fact.key, fact.value, fact.category, fact.source)
            )
            return fact

        self._mem_facts[fact.key] = {"key": fact.key, "value": fact.value, "category": fact.category}
        return fact

    async def get_facts(self, category: Optional[str] = None, limit: int = 100) -> list[MemoryFact]:
        if self._has_supa:
            try:
                q = self._supa.table("memory_facts").select("*")
                if category:
                    q = q.eq("category", category)
                resp = q.order("updated_at", desc=True).limit(limit).execute()
                return [MemoryFact(**row) for row in (resp.data or [])]
            except Exception as e:
                logger.warning("supa_get_facts_error", error=str(e))

        if self._has_sqlite:
            if category:
                rows = self._sqlite.fetchall(
                    "SELECT * FROM memory_facts WHERE category=? ORDER BY updated_at DESC LIMIT ?",
                    (category, limit)
                )
            else:
                rows = self._sqlite.fetchall(
                    "SELECT * FROM memory_facts ORDER BY updated_at DESC LIMIT ?", (limit,)
                )
            return [MemoryFact(**r) for r in rows]

        facts = list(self._mem_facts.values())
        if category:
            facts = [f for f in facts if f.get("category") == category]
        return [MemoryFact(**f) for f in facts[:limit]]

    async def search_facts(self, query: str, limit: int = 10) -> list[MemoryFact]:
        if self._has_supa:
            try:
                resp = (
                    self._supa.table("memory_facts")
                    .select("*")
                    .ilike("value", f"%{query}%")
                    .limit(limit)
                    .execute()
                )
                return [MemoryFact(**row) for row in (resp.data or [])]
            except Exception as e:
                logger.warning("supa_search_error", error=str(e))

        if self._has_sqlite:
            rows = self._sqlite.fetchall(
                "SELECT * FROM memory_facts WHERE value LIKE ? OR key LIKE ? LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)
            )
            return [MemoryFact(**r) for r in rows]

        q = query.lower()
        facts = [f for f in self._mem_facts.values()
                 if q in f["value"].lower() or q in f["key"].lower()]
        return [MemoryFact(**f) for f in facts[:limit]]

    async def delete_fact(self, key: str) -> bool:
        if self._has_supa:
            try:
                self._supa.table("memory_facts").delete().eq("key", key).execute()
                return True
            except Exception:
                pass
        if self._has_sqlite:
            self._sqlite.execute("DELETE FROM memory_facts WHERE key=?", (key,))
            return True
        self._mem_facts.pop(key, None)
        return True

    async def build_memory_context(self, session_id: str, user_message: str) -> str:
        facts = await self.get_facts(limit=30)
        if not facts:
            return ""
        lines = ["[SAM MEMORY — things you know about the user]"]
        for f in facts:
            lines.append(f"- {f.key}: {f.value}")
        return "\n".join(lines)

    # ── Tool Logs ───────────────────────────────────────────────────────────────

    async def log_tool(self, session_id: str, tool_name: str, arguments: dict,
                       result: Any, success: bool, duration_ms: int, permission_level: int):
        if self._has_supa:
            try:
                self._supa.table("tool_logs").insert({
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "result": result if isinstance(result, dict) else {"value": str(result)},
                    "success": success,
                    "duration_ms": duration_ms,
                    "permission_level": permission_level,
                }).execute()
            except Exception:
                pass

    # ── Automations ─────────────────────────────────────────────────────────────

    async def get_automations(self, enabled_only: bool = True) -> list[dict]:
        return []

    async def save_automation(self, automation: dict) -> dict:
        return automation


# Singleton
_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db
