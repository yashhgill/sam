"""
SAM — Computer Control Agent
Controls the Mac using AppleScript, subprocess, and macOS APIs.
Can open apps, control windows, take screenshots, run commands.
"""
import asyncio
import subprocess
import json
import base64
import os
from typing import Any

from agents.base import BaseAgent
from core.ai_provider import TaskType
from models.schemas import AgentContext

import logging
logger = logging.getLogger("agents.computer")


class ComputerAgent(BaseAgent):
    name = "computer"
    description = "Controls the Mac: opens apps, types, clicks, takes screenshots, runs commands"
    task_type = TaskType.SMART

    def get_system_prompt(self, ctx: AgentContext) -> str:
        return """You are SAM's computer control module running on macOS.
You can control the user's Mac using tools: open apps, run commands, take screenshots, type text, and more.

IMPORTANT RULES:
- Always confirm before deleting files or running destructive commands
- For ambiguous requests, ask for clarification
- Report what you did after each action
- Be concise — just say what you did

When asked to open something: use open_app or run_applescript.
When asked to search/browse: use run_command with 'open "https://..."'.
When asked what's on screen: use take_screenshot.
When asked to type or click: describe that you'd need macOS-use for fine-grained control."""

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "open_app",
                    "description": "Open an application on the Mac by name",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "app_name": {
                                "type": "string",
                                "description": "Name of the app to open (e.g. 'Safari', 'Spotify', 'Terminal', 'Finder')"
                            }
                        },
                        "required": ["app_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Run a shell command on the Mac. Use for opening URLs, managing files, etc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Shell command to run"
                            },
                            "description": {
                                "type": "string",
                                "description": "What this command does (for the user)"
                            }
                        },
                        "required": ["command", "description"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_applescript",
                    "description": "Run AppleScript to control Mac apps (Finder, Mail, Calendar, Music, etc.)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "script": {
                                "type": "string",
                                "description": "AppleScript code to execute"
                            },
                            "description": {
                                "type": "string",
                                "description": "What this script does"
                            }
                        },
                        "required": ["script", "description"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "take_screenshot",
                    "description": "Take a screenshot of the current screen",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_running_apps",
                    "description": "Get list of currently running applications",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_volume",
                    "description": "Set the Mac system volume",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "level": {
                                "type": "integer",
                                "description": "Volume level 0-100"
                            }
                        },
                        "required": ["level"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "type_text",
                    "description": "Type text into the currently focused application",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "Text to type"
                            }
                        },
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Open a web search in the default browser",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            },
                            "browser": {
                                "type": "string",
                                "description": "Browser to use: safari, chrome, or default",
                                "enum": ["safari", "chrome", "default"]
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
        ]

    async def execute_tool(self, tool_name: str, arguments: dict, ctx: AgentContext) -> Any:
        try:
            if tool_name == "open_app":
                return await self._open_app(arguments["app_name"])

            elif tool_name == "run_command":
                cmd = arguments["command"]
                desc = arguments.get("description", "running command")
                # Safety: block dangerous commands
                blocked = ["rm -rf /", "format", "mkfs", "dd if=", ":(){ :|:& };:"]
                if any(b in cmd for b in blocked):
                    return {"error": "Command blocked for safety"}
                result = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=15)
                return {
                    "success": result.returncode == 0,
                    "output": stdout.decode()[:500] if stdout else "",
                    "error": stderr.decode()[:200] if stderr and result.returncode != 0 else "",
                    "action": desc,
                }

            elif tool_name == "run_applescript":
                script = arguments["script"]
                desc = arguments.get("description", "running AppleScript")
                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
                return {
                    "success": proc.returncode == 0,
                    "output": stdout.decode().strip()[:500] if stdout else "",
                    "error": stderr.decode().strip()[:200] if stderr and proc.returncode != 0 else "",
                    "action": desc,
                }

            elif tool_name == "take_screenshot":
                path = "/tmp/sam_screenshot.png"
                proc = await asyncio.create_subprocess_exec(
                    "screencapture", "-x", path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                if os.path.exists(path):
                    return {"success": True, "path": path, "message": "Screenshot saved"}
                return {"error": "Screenshot failed"}

            elif tool_name == "get_running_apps":
                script = 'tell application "System Events" to get name of every process whose background only is false'
                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                apps = stdout.decode().strip().replace(", ", "\n").split("\n")
                return {"running_apps": apps}

            elif tool_name == "set_volume":
                level = max(0, min(100, arguments["level"]))
                script = f"set volume output volume {level}"
                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                return {"success": True, "volume": level}

            elif tool_name == "type_text":
                text = arguments["text"].replace('"', '\\"')
                script = f'tell application "System Events" to keystroke "{text}"'
                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                return {"success": True, "typed": arguments["text"]}

            elif tool_name == "search_web":
                query = arguments["query"]
                browser = arguments.get("browser", "default")
                import urllib.parse
                url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                if browser == "safari":
                    cmd = f'open -a Safari "{url}"'
                elif browser == "chrome":
                    cmd = f'open -a "Google Chrome" "{url}"'
                else:
                    cmd = f'open "{url}"'
                proc = await asyncio.create_subprocess_shell(cmd)
                await proc.communicate()
                return {"success": True, "url": url, "query": query}

            return {"error": f"Unknown tool: {tool_name}"}

        except asyncio.TimeoutError:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    async def _open_app(self, app_name: str) -> dict:
        """Open a Mac application by name."""
        # Common app name mappings
        aliases = {
            "browser": "Safari",
            "chrome": "Google Chrome",
            "music": "Music",
            "spotify": "Spotify",
            "terminal": "Terminal",
            "finder": "Finder",
            "mail": "Mail",
            "calendar": "Calendar",
            "notes": "Notes",
            "messages": "Messages",
            "facetime": "FaceTime",
            "photos": "Photos",
            "vscode": "Visual Studio Code",
            "code": "Visual Studio Code",
            "slack": "Slack",
            "zoom": "Zoom",
            "word": "Microsoft Word",
            "excel": "Microsoft Excel",
            "powerpoint": "Microsoft PowerPoint",
        }
        resolved = aliases.get(app_name.lower(), app_name)
        proc = await asyncio.create_subprocess_exec(
            "open", "-a", resolved,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            return {"success": True, "app": resolved, "action": f"Opened {resolved}"}
        return {"error": f"Could not open {resolved}: {stderr.decode().strip()}"}
