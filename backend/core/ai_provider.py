"""
SAM Ultra — AI Provider abstraction layer.
Supports Groq, OpenAI, Anthropic with unified streaming interface.
Routes to optimal model based on task type.
"""
import json
import time
import asyncio
from typing import AsyncGenerator, Optional, Any
from enum import Enum

import tiktoken
from groq import AsyncGroq
from openai import AsyncOpenAI
import anthropic

from core.config import settings
from core.logging import get_logger
from models.schemas import StreamEvent

logger = get_logger("ai_provider")


class TaskType(str, Enum):
    FAST = "fast"           # Greetings, simple acks
    SMART = "smart"         # General chat, tool use
    REASON = "reason"       # Code, math, planning
    VISION = "vision"       # Image understanding
    LONGCTX = "longctx"     # Long documents


class AIMessage:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

    def to_dict(self):
        return {"role": self.role, "content": self.content}


class AIProvider:
    """Unified AI provider with automatic failover and model routing."""

    def __init__(self):
        self.groq = AsyncGroq(api_key=settings.groq_api_key) if settings.groq_api_key else None
        self.openai = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.anthropic = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
        self._enc = None

    def _get_encoder(self):
        if not self._enc:
            try:
                self._enc = tiktoken.get_encoding("cl100k_base")
            except Exception:
                pass
        return self._enc

    def count_tokens(self, text: str) -> int:
        enc = self._get_encoder()
        if enc:
            return len(enc.encode(text))
        return len(text) // 4  # rough fallback

    def route_model(self, task_type: TaskType, message: str = "") -> tuple[str, str]:
        """Returns (provider, model_name) for the given task type."""
        token_count = self.count_tokens(message)

        # Long context routing
        if token_count > 6000:
            return ("groq", settings.model_longctx)

        routing = {
            TaskType.FAST: ("groq", settings.model_fast),
            TaskType.SMART: ("groq", settings.model_smart),
            TaskType.REASON: ("groq", settings.model_reason),
            TaskType.VISION: ("groq", settings.model_vision),
            TaskType.LONGCTX: ("groq", settings.model_longctx),
        }
        return routing.get(task_type, ("groq", settings.model_smart))

    def classify_task(self, message: str, has_tools: bool = False) -> TaskType:
        """Classify message to determine best model."""
        msg = message.lower()

        # Fast: simple greetings/acks
        fast_patterns = ["hi", "hello", "hey", "thanks", "ok", "okay", "sure", "yes", "no"]
        if any(msg == p or msg.startswith(p + " ") for p in fast_patterns) and len(message) < 30:
            return TaskType.FAST

        # Reasoning: code, math, planning
        reason_patterns = ["code", "debug", "fix", "write a function", "algorithm", "calculate",
                          "math", "plan", "architecture", "design", "analyze", "explain why"]
        if any(p in msg for p in reason_patterns):
            return TaskType.REASON

        # Long context
        if self.count_tokens(message) > 4000:
            return TaskType.LONGCTX

        return TaskType.SMART

    async def complete(
        self,
        messages: list[dict],
        system: str = "",
        task_type: Optional[TaskType] = None,
        tools: Optional[list[dict]] = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Unified completion with streaming.
        Yields StreamEvent objects.
        """
        user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

        if task_type is None:
            task_type = self.classify_task(user_message, has_tools=bool(tools))

        provider, model = self.route_model(task_type, user_message)

        logger.info("routing", provider=provider, model=model, task_type=task_type.value)

        yield StreamEvent(type="model", data={"provider": provider, "model": model})

        try:
            completed = False
            if provider == "groq" and self.groq:
                async for event in self._groq_complete(messages, system, model, tools, stream, temperature, max_tokens):
                    yield event
                completed = True
            elif provider == "openai" and self.openai:
                async for event in self._openai_complete(messages, system, model, tools, stream, temperature, max_tokens):
                    yield event
                completed = True
            elif provider == "anthropic" and self.anthropic:
                async for event in self._anthropic_complete(messages, system, model, stream, temperature, max_tokens):
                    yield event
                completed = True

            if not completed:
                yield StreamEvent(type="error", data={"error": "No AI providers configured. Add GROQ_API_KEY to your .env file."})

        except Exception as e:
            logger.error("provider_error", error=str(e), provider=provider, model=model)
            yield StreamEvent(type="error", data={"error": f"AI error: {str(e)}"})

    async def _groq_complete(
        self, messages, system, model, tools, stream, temperature, max_tokens
    ) -> AsyncGenerator[StreamEvent, None]:
        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        kwargs = {
            "model": model,
            "messages": all_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if stream:
            # groq 1.7.0: create(stream=True) returns AsyncStream[ChatCompletionChunk] directly
            s = await self.groq.chat.completions.create(
                model=model,
                messages=all_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **({"tools": tools, "tool_choice": "auto"} if tools else {}),
            )
            async for chunk in s:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield StreamEvent(type="token", data=delta.content)
                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.function and tc.function.name:
                            yield StreamEvent(type="tool_start", data={
                                "id": getattr(tc, 'id', ''),
                                "name": tc.function.name,
                                "arguments": tc.function.arguments or "",
                            })
        else:
            resp = await self.groq.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or ""
            yield StreamEvent(type="token", data=content)

            if resp.choices[0].message.tool_calls:
                for tc in resp.choices[0].message.tool_calls:
                    yield StreamEvent(type="tool_start", data={
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    })

        yield StreamEvent(type="done", data=None)

    async def _openai_complete(
        self, messages, system, model, tools, stream, temperature, max_tokens
    ) -> AsyncGenerator[StreamEvent, None]:
        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        kwargs = {
            "model": model,
            "messages": all_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if stream:
            async with await self.openai.chat.completions.create(**kwargs) as s:
                async for chunk in s:
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            yield StreamEvent(type="token", data=delta.content)
        else:
            resp = await self.openai.chat.completions.create(**kwargs)
            yield StreamEvent(type="token", data=resp.choices[0].message.content or "")

        yield StreamEvent(type="done", data=None)

    async def _anthropic_complete(
        self, messages, system, model, stream, temperature, max_tokens
    ) -> AsyncGenerator[StreamEvent, None]:
        kwargs = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        if stream:
            async with self.anthropic.messages.stream(**kwargs) as s:
                async for text in s.text_stream:
                    yield StreamEvent(type="token", data=text)
        else:
            resp = await self.anthropic.messages.create(**kwargs)
            yield StreamEvent(type="token", data=resp.content[0].text)

        yield StreamEvent(type="done", data=None)

    async def _fallback_complete(
        self, messages, system, tools, stream, temperature, max_tokens, exclude: str = ""
    ) -> AsyncGenerator[StreamEvent, None]:
        """Try providers in order, skipping excluded."""
        if exclude != "groq" and self.groq:
            async for e in self._groq_complete(messages, system, settings.model_smart, tools, stream, temperature, max_tokens):
                yield e
            return
        if exclude != "openai" and self.openai:
            async for e in self._openai_complete(messages, system, "gpt-4o-mini", tools, stream, temperature, max_tokens):
                yield e
            return
        if exclude != "anthropic" and self.anthropic:
            async for e in self._anthropic_complete(messages, system, "claude-haiku-3", stream, temperature, max_tokens):
                yield e
            return
        yield StreamEvent(type="error", data={"error": "No AI providers configured"})


# Singleton
_provider: Optional[AIProvider] = None


def get_provider() -> AIProvider:
    global _provider
    if _provider is None:
        _provider = AIProvider()
    return _provider
