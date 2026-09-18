"""
JARVIS Configuration
Central settings loaded from environment variables.
"""
from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    # Identity
    app_name: str = "JARVIS"
    app_version: str = "1.0.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Auth
    secret_key: str = "change-me-in-production-use-32-char-minimum"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_anon_key: str = ""

    # AI Providers
    groq_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Default models per task type
    model_fast: str = "llama-3.1-8b-instant"              # greetings, ack
    model_smart: str = "llama-3.3-70b-versatile"          # general chat, tools
    model_reason: str = "deepseek-r1-distill-llama-70b"   # code, math, planning
    model_vision: str = "llama-3.2-11b-vision-preview"    # image understanding
    model_longctx: str = "llama-3.3-70b-versatile"        # long docs (versatile has 128k ctx)

    # Redis (optional, for caching/pub-sub)
    redis_url: str = "redis://localhost:6379"
    use_redis: bool = False

    # Voice
    whisper_model: str = "whisper-large-v3-turbo"
    tts_provider: str = "browser"  # browser | elevenlabs | openai

    # Memory
    max_conversation_turns: int = 50
    max_working_memory_tokens: int = 4000

    # Permissions
    require_confirmation_level: int = 3  # Level 3+ requires confirmation

    class Config:
        env_file = (".env", "../.env")   # check current dir then parent
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
