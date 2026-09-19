"""
SAM — Calendar Agent
Reads and creates Mac Calendar events via AppleScript.
Works with iCloud Calendar, Google Calendar (if synced to Mac Calendar), and local calendars.
"""
import asyncio
import json
from typing import Any
from datetime import datetime, timedelta

from agents.base import BaseAgent
from core.ai_provider import TaskType
from models.schemas import AgentContext

import logging
logger = logging.getLogger("agents.calendar")


class CalendarAgent(BaseAgent):
    name = "calendar"
    description = "Reads and manages Mac Calendar: events, reminders, scheduling"
    task_type = TaskType.SMART

    def get_system_prompt(self, ctx: AgentContext) -> str:
        now = datetime.now().strftime("%A, %B %d %Y — %I:%M %p")
        return f"""You are SAM's Calendar Module. Current time: {now}

You help the user manage their schedule via Mac Calendar.

Rules:
- Always confirm before creating or deleting events
- Parse natural language dates/times intelligently
- Show events in a clean, readable format
- Suggest free time slots when asked to schedule something
- Be concise — just the essentials (time, title, location if any)

When listing events, format them as:
• [Time] Event Name (Calendar)
  Location if applicable"""

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_events",
                    "description": "Get calendar events for a date range",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "Start date in YYYY-MM-DD format (default: today)"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date in YYYY-MM-DD format (default: same as start)"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_event",
                    "description": "Create a new calendar event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Event title"},
                            "start_datetime": {"type": "string", "description": "Start datetime: 'YYYY-MM-DD HH:MM'"},
                            "end_datetime": {"type": "string", "description": "End datetime: 'YYYY-MM-DD HH:MM'"},
                            "calendar": {"type": "string", "description": "Calendar name (default: first available)"},
                            "location": {"type": "string", "description": "Event location (optional)"},
                            "notes": {"type": "string", "description": "Event notes (optional)"}
                        },
                        "required": ["title", "start_datetime", "end_datetime"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_calendars",
                    "description": "List all available calendars",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_event",
                    "description": "Delete a calendar event by title and date",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Event title to delete"},
                            "date": {"type": "string", "description": "Date of the event YYYY-MM-DD"}
                        },
                        "required": ["title", "date"]
                    }
                }
            }
        ]

    async def _run_applescript(self, script: str, timeout: float = 15) -> dict:
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
            return {"success": False, "error": "AppleScript timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def execute_tool(self, tool_name: str, arguments: dict, ctx: AgentContext) -> Any:
        try:
            if tool_name == "list_calendars":
                script = '''
tell application "Calendar"
    set calList to {}
    repeat with c in calendars
        set end of calList to name of c
    end repeat
    return calList as string
end tell'''
                result = await self._run_applescript(script)
                if result["success"]:
                    cals = [c.strip() for c in result["output"].split(",") if c.strip()]
                    return {"calendars": cals}
                return result

            elif tool_name == "get_events":
                today = datetime.now().strftime("%Y-%m-%d")
                start_date = arguments.get("start_date", today)
                end_date = arguments.get("end_date", start_date)

                # Parse dates for AppleScript
                try:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59)
                except ValueError:
                    return {"error": f"Invalid date format. Use YYYY-MM-DD"}

                start_str = start_dt.strftime("%m/%d/%Y %H:%M:%S")
                end_str = end_dt.strftime("%m/%d/%Y %H:%M:%S")

                script = f'''
tell application "Calendar"
    set startDate to date "{start_str}"
    set endDate to date "{end_str}"
    set eventList to {{}}
    repeat with c in calendars
        set calName to name of c
        set evts to (every event of c whose start date >= startDate and start date <= endDate)
        repeat with e in evts
            set evtTitle to summary of e
            set evtStart to start date of e as string
            set evtEnd to end date of e as string
            try
                set evtLoc to location of e
            on error
                set evtLoc to ""
            end try
            set end of eventList to (evtTitle & "|" & evtStart & "|" & evtEnd & "|" & calName & "|" & evtLoc)
        end repeat
    end repeat
    return eventList as string
end tell'''
                result = await self._run_applescript(script)
                if result["success"]:
                    raw = result["output"]
                    if not raw:
                        return {"events": [], "date_range": f"{start_date} to {end_date}"}
                    events = []
                    for line in raw.split(","):
                        parts = line.strip().split("|")
                        if len(parts) >= 4:
                            events.append({
                                "title": parts[0].strip(),
                                "start": parts[1].strip(),
                                "end": parts[2].strip(),
                                "calendar": parts[3].strip(),
                                "location": parts[4].strip() if len(parts) > 4 else ""
                            })
                    return {"events": events, "date_range": f"{start_date} to {end_date}", "count": len(events)}
                return result

            elif tool_name == "create_event":
                title = arguments["title"]
                start = arguments["start_datetime"]
                end = arguments["end_datetime"]
                calendar = arguments.get("calendar", "")
                location = arguments.get("location", "")
                notes = arguments.get("notes", "")

                try:
                    start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
                    end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M")
                except ValueError:
                    return {"error": "Invalid datetime format. Use 'YYYY-MM-DD HH:MM'"}

                start_str = start_dt.strftime("%m/%d/%Y %H:%M:%S")
                end_str = end_dt.strftime("%m/%d/%Y %H:%M:%S")

                cal_selector = f'first calendar whose name is "{calendar}"' if calendar else "first calendar"

                loc_line = f'set location of newEvent to "{location}"' if location else ""
                notes_line = f'set description of newEvent to "{notes}"' if notes else ""

                script = f'''
tell application "Calendar"
    set targetCal to {cal_selector}
    set startDate to date "{start_str}"
    set endDate to date "{end_str}"
    set newEvent to make new event at end of events of targetCal with properties {{summary:"{title}", start date:startDate, end date:endDate}}
    {loc_line}
    {notes_line}
    return "created"
end tell'''
                result = await self._run_applescript(script)
                if result["success"]:
                    return {
                        "created": True,
                        "title": title,
                        "start": start,
                        "end": end,
                        "calendar": calendar or "default"
                    }
                return {"error": result.get("error", "Failed to create event")}

            elif tool_name == "delete_event":
                title = arguments["title"]
                date = arguments["date"]
                try:
                    dt = datetime.strptime(date, "%Y-%m-%d")
                    end_dt = dt.replace(hour=23, minute=59)
                except ValueError:
                    return {"error": "Invalid date format. Use YYYY-MM-DD"}

                start_str = dt.strftime("%m/%d/%Y %H:%M:%S")
                end_str = end_dt.strftime("%m/%d/%Y %H:%M:%S")

                script = f'''
tell application "Calendar"
    set startDate to date "{start_str}"
    set endDate to date "{end_str}"
    set deleted to 0
    repeat with c in calendars
        set evts to (every event of c whose summary is "{title}" and start date >= startDate and start date <= endDate)
        repeat with e in evts
            delete e
            set deleted to deleted + 1
        end repeat
    end repeat
    return deleted as string
end tell'''
                result = await self._run_applescript(script)
                if result["success"]:
                    count = int(result["output"]) if result["output"].isdigit() else 0
                    return {"deleted": count > 0, "count": count, "title": title}
                return {"error": result.get("error", "Failed to delete event")}

            return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.error(f"CalendarAgent tool error: {e}")
            return {"error": str(e)}
