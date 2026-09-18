"""
SAM Ultra — Base Agent
All agents inherit from this. Handles tool dispatch, permission checking,
streaming output, emotion detection, memory injection.
"""
import time
import json
from typing import AsyncGenerator, Optional, Any
from abc import ABC, abstractmethod

from core.config import settings
from core.ai_provider import get_provider, TaskType
from core.logging import get_logger
from memory.database import get_db
from models.schemas import (
    AgentContext, StreamEvent, PermissionLevel,
    ToolCall, ToolResult, EmotionEstimate, ConversationTurn
)

logger = get_logger("agents.base")


EMOTION_SYSTEM = """
Detect the user's emotional state from their message and respond accordingly:
- frustrated/angry: Be direct, skip filler, solve fast
- stressed: Calm, precise, efficient
- excited: Match energy, be enthusiastic but focused
- tired: Short answers, no fluff
- curious: Go deeper, explain well
- satisfied: Keep momentum
- neutral: Normal helpful tone
"""


class BaseAgent(ABC):
    """Base class for all SAM Ultra agents."""

    name: str = "base"
    description: str = "Base agent"
    task_type: TaskType = TaskType.SMART

    def __init__(self):
        self.provider = get_provider()
        self.db = get_db()
        self.logger = get_logger(f"agents.{self.name}")

    @abstractmethod
    def get_system_prompt(self, ctx: AgentContext) -> str:
        """Return the system prompt for this agent."""
        ...

    def get_tools(self) -> list[dict]:
        """Return OpenAI-format tool definitions. Override to add tools."""
        return []

    async def execute_tool(self, tool_name: str, arguments: dict, ctx: AgentContext) -> Any:
        """Execute a tool by name. Override to handle agent-specific tools."""
        return {"error": f"Unknown tool: {tool_name}"}

    def check_permission(self, required_level: PermissionLevel) -> bool:
        """Check if the required permission level is auto-approved."""
        return required_level < settings.require_confirmation_level

    async def run(self, ctx: AgentContext) -> AsyncGenerator[StreamEvent, None]:
        """
        Main agent execution loop.
        Handles: history retrieval, memory injection, streaming, tool calls, saving.
        """
        start = time.time()
        session_id = ctx.session_id

        # Touch session
        await self.db.touch_session(session_id, self.name)

        # Build message history
        history = await self.db.get_messages(session_id, limit=settings.max_conversation_turns)
        messages = [m.to_dict() if hasattr(m, "to_dict") else {"role": m.role, "content": m.content}
                    for m in history]
        messages.append({"role": "user", "content": ctx.user_message})

        # Build system prompt
        system = self.get_system_prompt(ctx)

        # Inject memory
        if ctx.memory_context:
            system = ctx.memory_context + "\n\n" + system
        else:
            memory_ctx = await self.db.build_memory_context(session_id, ctx.user_message)
            if memory_ctx:
                system = memory_ctx + "\n\n" + system

        # Inject emotion context
        if ctx.emotion and ctx.emotion.mood != "neutral":
            system += f"\n\n[USER MOOD: {ctx.emotion.mood}]\n" + EMOTION_SYSTEM

        # Get tools
        tools = self.get_tools()

        # Stream completion
        full_response = ""
        tools_called = []
        current_tool_calls: dict[str, dict] = {}

        self.logger.info("agent_run", session=session_id, agent=self.name, msg_len=len(ctx.user_message))

        async for event in self.provider.complete(
            messages=messages,
            system=system,
            task_type=self.task_type,
            tools=tools if tools else None,
            stream=True,
        ):
            if event.type == "token":
                full_response += event.data
                yield event

            elif event.type == "tool_start":
                tool_data = event.data
                tool_id = tool_data.get("id", "")
                current_tool_calls[tool_id] = {
                    "name": tool_data["name"],
                    "arguments": tool_data.get("arguments", ""),
                }
                yield StreamEvent(type="tool_start", data={"name": tool_data["name"]})

            elif event.type == "model":
                yield event

            elif event.type == "done":
                # Execute any pending tool calls
                for tool_id, tc in current_tool_calls.items():
                    tool_name = tc["name"]
                    try:
                        args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
                    except json.JSONDecodeError:
                        args = {}

                    t_start = time.time()
                    result = await self.execute_tool(tool_name, args, ctx)
                    duration_ms = int((time.time() - t_start) * 1000)

                    tools_called.append(tool_name)

                    # Log tool execution
                    await self.db.log_tool(
                        session_id=session_id,
                        tool_name=tool_name,
                        arguments=args,
                        result=result,
                        success=not (isinstance(result, dict) and "error" in result),
                        duration_ms=duration_ms,
                        permission_level=0,
                    )

                    yield StreamEvent(type="tool_end", data={
                        "name": tool_name,
                        "result": result,
                        "duration_ms": duration_ms,
                    })

                    # If tool had results, do a follow-up completion
                    if result and full_response == "":
                        messages_with_tool = messages + [
                            {"role": "assistant", "content": f"[Used tool: {tool_name}]"},
                            {"role": "tool", "content": json.dumps(result)},
                        ]
                        async for follow_event in self.provider.complete(
                            messages=messages_with_tool,
                            system=system,
                            task_type=self.task_type,
                            stream=True,
                        ):
                            if follow_event.type == "token":
                                full_response += follow_event.data
                                yield follow_event
                            elif follow_event.type == "done":
                                break

                break  # done event exits the loop

            elif event.type == "error":
                yield event
                break

        # Save conversation turns
        if ctx.user_message:
            await self.db.save_turn(ConversationTurn(
                session_id=session_id,
                role="user",
                content=ctx.user_message,
                device=ctx.device,
                agent=self.name,
            ))

        if full_response:
            await self.db.save_turn(ConversationTurn(
                session_id=session_id,
                role="assistant",
                content=full_response,
                device=ctx.device,
                agent=self.name,
                tools_used=tools_called,
            ))

        duration = int((time.time() - start) * 1000)
        self.logger.info("agent_done", session=session_id, duration_ms=duration, tools=tools_called)

        yield StreamEvent(type="done", data={
            "agent": self.name,
            "duration_ms": duration,
            "tools_used": tools_called,
        })
