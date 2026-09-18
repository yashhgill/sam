"""
SAM Ultra — Coding Agent
Code generation, debugging, refactoring. Uses DeepSeek R1 for reasoning.
"""
from typing import Any
from agents.base import BaseAgent
from core.ai_provider import TaskType
from models.schemas import AgentContext


class CodingAgent(BaseAgent):
    name = "coding"
    description = "Advanced coding agent with reasoning model"
    task_type = TaskType.REASON

    def get_system_prompt(self, ctx: AgentContext) -> str:
        return """You are SAM's Coding Module — an expert software engineer.

Capabilities:
- Write clean, production-ready code in any language
- Debug and fix errors with precision
- Refactor and improve existing code
- Explain code clearly
- Design architecture and data models
- Write tests

Rules:
- Always include error handling
- Write type hints for Python, types for TypeScript
- Comment complex logic
- Suggest improvements beyond what was asked when you see obvious issues
- For multi-file changes, clearly label each file

Think step by step before writing code. Use reasoning for complex problems."""

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_code",
                    "description": "Execute Python code and return output",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "Python code to execute"},
                            "timeout": {"type": "integer", "default": 10}
                        },
                        "required": ["code"]
                    }
                }
            }
        ]

    async def execute_tool(self, tool_name: str, arguments: dict, ctx: AgentContext) -> Any:
        if tool_name == "run_code":
            import asyncio
            import subprocess
            import sys

            code = arguments.get("code", "")
            timeout = min(arguments.get("timeout", 10), 30)

            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-c", code,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                return {
                    "stdout": stdout.decode()[:2000],
                    "stderr": stderr.decode()[:500],
                    "returncode": proc.returncode,
                }
            except asyncio.TimeoutError:
                return {"error": "Code execution timed out"}
            except Exception as e:
                return {"error": str(e)}

        return await super().execute_tool(tool_name, arguments, ctx)
