"""
SAM Ultra — Main FastAPI Application
WebSocket + HTTP chat, health, status, CORS, lifespan.
"""
import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from core.config import settings
from core.logging import setup_logging, get_logger
from core.emotion import detect_emotion
from agents.router import route, get_agent
from memory.database import get_db
from models.schemas import (
    ChatRequest, ChatResponse, StreamEvent,
    AgentContext, EmotionEstimate, SystemStatus, Session
)

# ── Setup ──────────────────────────────────────────────────────────────────────

setup_logging()
logger = get_logger("main")

_start_time = time.time()
_active_sessions: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("sam_starting", version=settings.app_version)
    # Pre-warm DB connection
    try:
        db = get_db()
        logger.info("db_ready")
    except Exception as e:
        logger.warning("db_not_configured", error=str(e))

    yield

    logger.info("sam_shutdown")


app = FastAPI(
    title="SAM Ultra",
    version=settings.app_version,
    description="SAM — Personal AI Operating System",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cloudflare handles auth; we allow all origins
    allow_credentials=False,  # Must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID", "X-Accel-Buffering"],
)


# ── Health & Status ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"service": "SAM Ultra", "version": settings.app_version, "status": "online"}


@app.get("/health")
async def health():
    return {"status": "healthy", "uptime": time.time() - _start_time}


@app.get("/status", response_model=SystemStatus)
async def status():
    return SystemStatus(
        status="online",
        version=settings.app_version,
        ai_provider="groq",
        active_sessions=len(_active_sessions),
        uptime_seconds=time.time() - _start_time,
    )


# ── HTTP Chat (SSE Streaming) ──────────────────────────────────────────────────

@app.post("/chat")
async def chat_http(req: ChatRequest):
    """HTTP endpoint with Server-Sent Events streaming."""
    session_id = req.session_id or str(uuid.uuid4())
    _active_sessions.add(session_id)

    # Detect emotion
    emotion = EmotionEstimate(mood="neutral", confidence=0.0)
    if req.emotion_detection:
        emotion = detect_emotion(req.message)

    # Route to agent
    ctx = AgentContext(
        session_id=session_id,
        user_message=req.message,
        emotion=emotion,
        device=req.device,
    )

    agent_name = route(ctx)
    ctx.active_agent = agent_name

    if req.stream:
        async def event_stream():
            try:
                agent = await get_agent(agent_name)

                # Send session + agent info first
                yield f"data: {json.dumps({'type': 'session', 'data': {'session_id': session_id, 'agent': agent_name}})}\n\n"

                if emotion.mood != "neutral":
                    yield f"data: {json.dumps({'type': 'emotion', 'data': {'mood': emotion.mood, 'confidence': emotion.confidence}})}\n\n"

                async for event in agent.run(ctx):
                    yield f"data: {json.dumps({'type': event.type, 'data': event.data})}\n\n"

            except Exception as e:
                logger.error("chat_error", error=str(e), session=session_id)
                yield f"data: {json.dumps({'type': 'error', 'data': {'error': str(e)}})}\n\n"
            finally:
                _active_sessions.discard(session_id)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Session-ID": session_id,
            }
        )
    else:
        # Non-streaming
        agent = await get_agent(agent_name)
        full_text = ""
        tools_used = []

        async for event in agent.run(ctx):
            if event.type == "token":
                full_text += event.data
            elif event.type == "tool_end":
                tools_used.append(event.data.get("name", ""))

        _active_sessions.discard(session_id)
        return ChatResponse(
            reply=full_text,
            session_id=session_id,
            model=settings.model_smart,
            agent=agent_name,
            tools_used=tools_used,
            emotion=emotion if emotion.mood != "neutral" else None,
        )


# ── WebSocket Chat ─────────────────────────────────────────────────────────────

@app.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time bidirectional chat.
    Client sends: {"message": "...", "device": "...", "emotion_detection": true}
    Server sends: StreamEvent JSON objects
    """
    await websocket.accept()
    _active_sessions.add(session_id)
    logger.info("ws_connected", session=session_id)

    try:
        # Initialize session
        db = get_db()
        await db.create_session(session_id)

        while True:
            # Receive message
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=300)
                data = json.loads(raw)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue
            except Exception:
                break

            message = data.get("message", "")
            device = data.get("device", "web")
            emotion_detection = data.get("emotion_detection", True)

            if not message:
                continue

            # Detect emotion
            emotion = EmotionEstimate(mood="neutral", confidence=0.0)
            if emotion_detection:
                emotion = detect_emotion(message)
                if emotion.mood != "neutral":
                    await websocket.send_json({
                        "type": "emotion",
                        "data": {"mood": emotion.mood, "confidence": emotion.confidence}
                    })

            # Build context and route
            ctx = AgentContext(
                session_id=session_id,
                user_message=message,
                emotion=emotion,
                device=device,
            )
            agent_name = route(ctx)
            ctx.active_agent = agent_name

            # Notify agent switch
            await websocket.send_json({
                "type": "agent_switch",
                "data": {"agent": agent_name}
            })

            # Stream response
            agent = await get_agent(agent_name)
            async for event in agent.run(ctx):
                try:
                    await websocket.send_json({
                        "type": event.type,
                        "data": event.data,
                    })
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.info("ws_disconnected", session=session_id)
    except Exception as e:
        logger.error("ws_error", error=str(e), session=session_id)
        try:
            await websocket.send_json({"type": "error", "data": {"error": str(e)}})
        except Exception:
            pass
    finally:
        _active_sessions.discard(session_id)


# ── Memory API ─────────────────────────────────────────────────────────────────

@app.get("/memory")
async def get_memory(category: str = None):
    db = get_db()
    facts = await db.get_facts(category=category)
    return {"facts": [{"key": f.key, "value": f.value, "category": f.category} for f in facts]}


@app.delete("/memory/{key}")
async def delete_memory(key: str):
    db = get_db()
    ok = await db.delete_fact(key)
    return {"deleted": ok, "key": key}


# ── History API ────────────────────────────────────────────────────────────────

@app.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 20):
    db = get_db()
    history = await db.get_history(session_id, limit=limit)
    return {"session_id": session_id, "messages": history, "count": len(history)}


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
