# SAM Ultra v2.0

Personal AI Operating System. Multi-agent, memory-enabled, streaming.

## Quick Start (Mac/Linux)

```bash
# 1. Clone / copy this folder to your machine
# 2. Set up environment
cp .env.example .env
# Edit .env — your Groq key is already there

# 3. Start everything
chmod +x scripts/start.sh
./scripts/start.sh
```

Then open: http://localhost:5173

## Architecture

```
SAM Ultra
├── backend/          FastAPI + Python
│   ├── main.py       HTTP + WebSocket entrypoint
│   ├── core/
│   │   ├── config.py         Settings (env vars)
│   │   ├── ai_provider.py    Groq/OpenAI/Anthropic unified layer
│   │   ├── emotion.py        Emotion detection from text
│   │   └── logging.py        Structured logging
│   ├── agents/
│   │   ├── base.py           Base agent (streaming, tools, memory)
│   │   ├── router.py         Intent → agent routing
│   │   ├── conversation.py   Primary chat agent
│   │   ├── research.py       Web search + synthesis
│   │   └── coding.py         Code generation (DeepSeek R1)
│   ├── memory/
│   │   └── database.py       Supabase persistence
│   └── models/
│       └── schemas.py        All Pydantic types
└── frontend/         React + TypeScript + Vite
    └── src/
        ├── App.tsx            Main UI
        ├── hooks/useChat.ts   SSE streaming
        └── stores/chat.ts     Zustand state
```

## Models Used

| Task | Model | Why |
|------|-------|-----|
| Greetings | llama-3.1-8b-instant | Fast, cheap |
| General chat | llama3-70b-8192 | Smart |
| Code/Math | deepseek-r1-distill-llama-70b | Reasoning |
| Vision | llama-3.2-11b-vision-preview | Images |
| Long docs | mixtral-8x7b-32768 | 32k context |

## Agents

| Agent | Triggers | Capability |
|-------|----------|-----------|
| conversation | Default | General chat, memory |
| research | "search", "find", "latest" | Web search + synthesis |
| coding | "code", "debug", "write function" | Code generation |
| smart_home | "lights", "thermostat", "turn on" | Home automation |
| calendar | "schedule", "meeting", "tomorrow" | Calendar management |
| communication | "send email/message" | Messages |
| music | "play", "song", "playlist" | Music control |
| file | "file", "folder", "document" | File operations |
| automation | "automate", "every day" | Workflow automation |

## API Endpoints

- `POST /chat` — HTTP with SSE streaming
- `WS /ws/{session_id}` — WebSocket bidirectional
- `GET /health` — Health check
- `GET /status` — System status
- `GET /memory` — List memory facts
- `DELETE /memory/{key}` — Delete a memory
- `GET /history/{session_id}` — Conversation history
- `GET /docs` — Swagger UI

## Docker

```bash
cd docker
docker-compose up --build
```

Frontend: http://localhost:3000  
Backend: http://localhost:8000
