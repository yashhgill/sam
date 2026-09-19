"""
SAM — Music Agent
Controls Apple Music and Spotify via AppleScript.
"""
import asyncio
from typing import Any

from agents.base import BaseAgent
from core.ai_provider import TaskType
from models.schemas import AgentContext

import logging
logger = logging.getLogger("agents.music")


class MusicAgent(BaseAgent):
    name = "music"
    description = "Controls Apple Music and Spotify: play, pause, skip, search"
    task_type = TaskType.FAST

    def get_system_prompt(self, ctx: AgentContext) -> str:
        return """You are SAM's Music Module.
Control Apple Music or Spotify on the Mac using available tools.
Be brief — confirm what you did and what's now playing.
If a search returns no results, suggest alternatives."""

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "play_pause",
                    "description": "Play or pause music",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["play", "pause", "toggle"],
                                "description": "play, pause, or toggle"
                            },
                            "app": {
                                "type": "string",
                                "enum": ["Music", "Spotify"],
                                "description": "Which app to control (default: Music)"
                            }
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "skip_track",
                    "description": "Skip to next or previous track",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "direction": {
                                "type": "string",
                                "enum": ["next", "previous"],
                            },
                            "app": {"type": "string", "enum": ["Music", "Spotify"]}
                        },
                        "required": ["direction"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_now_playing",
                    "description": "Get currently playing track info",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "app": {"type": "string", "enum": ["Music", "Spotify"]}
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_and_play",
                    "description": "Search for a song or artist and play it",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Song name, artist, or album"},
                            "app": {"type": "string", "enum": ["Music", "Spotify"]}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_volume",
                    "description": "Set music volume",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "level": {"type": "integer", "description": "Volume 0-100"},
                            "app": {"type": "string", "enum": ["Music", "Spotify"]}
                        },
                        "required": ["level"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_shuffle",
                    "description": "Enable or disable shuffle",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "app": {"type": "string", "enum": ["Music", "Spotify"]}
                        },
                        "required": ["enabled"]
                    }
                }
            }
        ]

    async def _applescript(self, script: str, timeout: float = 10) -> dict:
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            if proc.returncode == 0:
                return {"success": True, "output": stdout.decode().strip()}
            return {"success": False, "error": stderr.decode().strip()}
        except asyncio.TimeoutError:
            return {"success": False, "error": "Timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def execute_tool(self, tool_name: str, arguments: dict, ctx: AgentContext) -> Any:
        try:
            app = arguments.get("app", "Music")

            if tool_name == "get_now_playing":
                # Try Music first, then Spotify
                apps_to_try = [app] if app in ["Music", "Spotify"] else ["Music", "Spotify"]
                for a in apps_to_try:
                    if a == "Music":
                        script = '''
tell application "Music"
    if player state is playing then
        set t to current track
        return (name of t) & " | " & (artist of t) & " | " & (album of t)
    else
        return "not playing"
    end if
end tell'''
                    else:
                        script = '''
tell application "Spotify"
    if player state is playing then
        return (current track's name) & " | " & (current track's artist) & " | " & (current track's album)
    else
        return "not playing"
    end if
end tell'''
                    result = await self._applescript(script)
                    if result["success"] and result["output"] != "not playing":
                        parts = result["output"].split(" | ")
                        return {
                            "playing": True,
                            "title": parts[0] if parts else "",
                            "artist": parts[1] if len(parts) > 1 else "",
                            "album": parts[2] if len(parts) > 2 else "",
                            "app": a
                        }
                return {"playing": False, "message": "Nothing is playing"}

            elif tool_name == "play_pause":
                action = arguments.get("action", "toggle")
                if app == "Spotify":
                    cmd_map = {"play": "play", "pause": "pause", "toggle": "playpause"}
                    script = f'tell application "Spotify" to {cmd_map.get(action, "playpause")}'
                else:
                    cmd_map = {"play": "play", "pause": "pause", "toggle": "playpause"}
                    script = f'tell application "Music" to {cmd_map.get(action, "playpause")}'

                result = await self._applescript(script)
                return {"success": result["success"], "action": action, "app": app,
                        "error": result.get("error", "")}

            elif tool_name == "skip_track":
                direction = arguments.get("direction", "next")
                if app == "Spotify":
                    cmd = "next track" if direction == "next" else "previous track"
                    script = f'tell application "Spotify" to {cmd}'
                else:
                    cmd = "next track" if direction == "next" else "back track"
                    script = f'tell application "Music" to {cmd}'

                result = await self._applescript(script)
                if result["success"]:
                    # Get new track info
                    info = await self.execute_tool("get_now_playing", {"app": app}, ctx)
                    return {"skipped": True, "direction": direction, "now_playing": info}
                return {"error": result.get("error", "Skip failed")}

            elif tool_name == "search_and_play":
                query = arguments["query"]
                if app == "Spotify":
                    # Spotify: open search URL
                    import urllib.parse
                    url = f"spotify:search:{urllib.parse.quote(query)}"
                    script = f'tell application "Spotify" to open location "{url}"'
                    result = await self._applescript(script)
                    if result["success"]:
                        return {"searching": True, "query": query, "app": "Spotify",
                                "note": "Opened Spotify search. Press play on a result."}
                    return {"error": result.get("error")}
                else:
                    # Apple Music: search library
                    script = f'''
tell application "Music"
    set results to search playlist "Library" for "{query}"
    if results is not {{}} then
        play item 1 of results
        set t to current track
        return (name of t) & " | " & (artist of t)
    else
        return "not found"
    end if
end tell'''
                    result = await self._applescript(script)
                    if result["success"]:
                        if result["output"] == "not found":
                            return {"found": False, "query": query,
                                    "message": f'No results for "{query}" in your library'}
                        parts = result["output"].split(" | ")
                        return {
                            "playing": True,
                            "title": parts[0] if parts else query,
                            "artist": parts[1] if len(parts) > 1 else "",
                            "app": "Music"
                        }
                    return {"error": result.get("error")}

            elif tool_name == "set_volume":
                level = max(0, min(100, arguments["level"]))
                if app == "Spotify":
                    script = f'tell application "Spotify" to set sound volume to {level}'
                else:
                    script = f'tell application "Music" to set sound volume to {level}'
                result = await self._applescript(script)
                return {"volume": level, "app": app, "success": result["success"]}

            elif tool_name == "set_shuffle":
                enabled = arguments["enabled"]
                if app == "Spotify":
                    script = f'tell application "Spotify" to set shuffling to {"true" if enabled else "false"}'
                else:
                    script = f'tell application "Music" to set shuffle enabled to {"true" if enabled else "false"}'
                result = await self._applescript(script)
                return {"shuffle": enabled, "app": app, "success": result["success"]}

            return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.error(f"MusicAgent error: {e}")
            return {"error": str(e)}
