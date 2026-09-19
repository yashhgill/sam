"""
SAM — File Agent
Browse, search, read, move, and manage files on the Mac.
"""
import asyncio
import os
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from core.ai_provider import TaskType
from models.schemas import AgentContext

import logging
logger = logging.getLogger("agents.file")


class FileAgent(BaseAgent):
    name = "file"
    description = "Manages files and folders on the Mac"
    task_type = TaskType.SMART

    def get_system_prompt(self, ctx: AgentContext) -> str:
        home = os.path.expanduser("~")
        return f"""You are SAM's File Module. The user's home directory is {home}.

You can list, search, read, move, rename, and open files on the Mac.

Rules:
- Always confirm before deleting or overwriting files
- Expand ~ to the actual home path
- Present file lists cleanly
- For large files, summarize rather than dumping full content
- Never access system directories outside the user's home unless asked"""

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files and folders in a directory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Directory path (default: ~/Desktop)"},
                            "show_hidden": {"type": "boolean", "description": "Show hidden files (default: false)"}
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_files",
                    "description": "Search for files by name or content",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search term (filename or content)"},
                            "path": {"type": "string", "description": "Directory to search in (default: ~)"},
                            "type": {"type": "string", "description": "Filter by type: 'file', 'folder', or 'any'"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read the contents of a text file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path to read"},
                            "lines": {"type": "integer", "description": "Max lines to read (default: 100)"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "open_file",
                    "description": "Open a file in its default app",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path to open"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "move_file",
                    "description": "Move or rename a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string", "description": "Source file path"},
                            "destination": {"type": "string", "description": "Destination path"}
                        },
                        "required": ["source", "destination"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_file_info",
                    "description": "Get info about a file (size, dates, type)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"}
                        },
                        "required": ["path"]
                    }
                }
            }
        ]

    def _expand(self, path: str) -> str:
        return os.path.expanduser(path)

    async def _run(self, cmd: list[str], timeout: float = 10) -> dict:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "success": proc.returncode == 0,
                "output": stdout.decode().strip(),
                "error": stderr.decode().strip() if proc.returncode != 0 else ""
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": "Command timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def execute_tool(self, tool_name: str, arguments: dict, ctx: AgentContext) -> Any:
        try:
            if tool_name == "list_files":
                path = self._expand(arguments.get("path", "~/Desktop"))
                show_hidden = arguments.get("show_hidden", False)

                if not os.path.exists(path):
                    return {"error": f"Directory not found: {path}"}

                try:
                    entries = os.scandir(path)
                    files = []
                    for e in sorted(entries, key=lambda x: (not x.is_dir(), x.name.lower())):
                        if not show_hidden and e.name.startswith("."):
                            continue
                        stat = e.stat()
                        size = stat.st_size
                        size_str = (
                            f"{size/1_000_000:.1f} MB" if size > 1_000_000
                            else f"{size/1_000:.1f} KB" if size > 1_000
                            else f"{size} B"
                        )
                        files.append({
                            "name": e.name,
                            "type": "folder" if e.is_dir() else "file",
                            "size": size_str if not e.is_dir() else "",
                        })
                    return {"path": path, "items": files, "count": len(files)}
                except PermissionError:
                    return {"error": f"Permission denied: {path}"}

            elif tool_name == "search_files":
                query = arguments["query"]
                path = self._expand(arguments.get("path", "~"))
                file_type = arguments.get("type", "any")

                cmd = ["find", path, "-maxdepth", "5", "-iname", f"*{query}*"]
                if file_type == "file":
                    cmd += ["-type", "f"]
                elif file_type == "folder":
                    cmd += ["-type", "d"]

                # Exclude noisy dirs
                cmd += ["!", "-path", "*/node_modules/*", "!", "-path", "*/.git/*",
                        "!", "-path", "*/Library/Caches/*"]

                result = await self._run(cmd, timeout=15)
                if result["success"]:
                    lines = [l for l in result["output"].split("\n") if l.strip()][:50]
                    return {"results": lines, "count": len(lines), "query": query}
                return {"error": result.get("error", "Search failed"), "results": []}

            elif tool_name == "read_file":
                path = self._expand(arguments["path"])
                max_lines = arguments.get("lines", 100)

                if not os.path.exists(path):
                    return {"error": f"File not found: {path}"}
                if os.path.isdir(path):
                    return {"error": f"{path} is a directory, not a file"}

                try:
                    size = os.path.getsize(path)
                    if size > 5_000_000:
                        return {"error": f"File too large ({size/1_000_000:.1f} MB). Use search or specify a smaller file."}

                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()

                    total = len(lines)
                    content = "".join(lines[:max_lines])
                    truncated = total > max_lines

                    return {
                        "path": path,
                        "content": content,
                        "lines": total,
                        "truncated": truncated,
                        "message": f"Showing first {max_lines} of {total} lines" if truncated else ""
                    }
                except PermissionError:
                    return {"error": f"Permission denied: {path}"}
                except UnicodeDecodeError:
                    return {"error": "Binary file — cannot read as text"}

            elif tool_name == "open_file":
                path = self._expand(arguments["path"])
                result = await self._run(["open", path])
                if result["success"]:
                    return {"opened": True, "path": path}
                return {"error": result.get("error", "Failed to open file")}

            elif tool_name == "move_file":
                src = self._expand(arguments["source"])
                dst = self._expand(arguments["destination"])

                if not os.path.exists(src):
                    return {"error": f"Source not found: {src}"}

                # Safety check
                dangerous = ["/System", "/Library", "/usr", "/bin", "/sbin", "/etc"]
                for d in dangerous:
                    if src.startswith(d) or dst.startswith(d):
                        return {"error": f"Cannot move system files"}

                result = await self._run(["mv", src, dst])
                if result["success"]:
                    return {"moved": True, "from": src, "to": dst}
                return {"error": result.get("error", "Move failed")}

            elif tool_name == "get_file_info":
                path = self._expand(arguments["path"])
                if not os.path.exists(path):
                    return {"error": f"Not found: {path}"}

                stat = os.stat(path)
                from datetime import datetime
                return {
                    "path": path,
                    "type": "folder" if os.path.isdir(path) else "file",
                    "size_bytes": stat.st_size,
                    "size": (
                        f"{stat.st_size/1_000_000:.2f} MB" if stat.st_size > 1_000_000
                        else f"{stat.st_size/1_000:.1f} KB"
                    ),
                    "created": datetime.fromtimestamp(stat.st_birthtime).isoformat() if hasattr(stat, "st_birthtime") else "",
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "extension": Path(path).suffix,
                }

            return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.error(f"FileAgent error: {e}")
            return {"error": str(e)}
