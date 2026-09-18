"""
SAM Ultra — Conversation Agent
Primary agent for general chat, Q&A, and task delegation.
"""
from core.ai_provider import TaskType
from agents.base import BaseAgent
from models.schemas import AgentContext


SAM_IDENTITY = """You are SAM — a highly capable personal AI assistant. You are direct,
intelligent, and deeply useful. You have access to the user's files, calendar, messages,
smart home, computer, and memory. You learn and remember everything the user tells you.

Core traits:
- Concise but complete. Never verbose unless asked.
- Proactive. Anticipate what the user needs.
- Honest. Never pretend to know something you don't.
- Efficient. Solve problems fast.
- Personal. Remember context from previous conversations.

You can delegate to specialized agents for:
- Research tasks → research agent
- Computer control → computer agent
- Smart home → smart_home agent
- Code → coding agent
- Calendar/scheduling → calendar agent
- Messages/email → communication agent
- Music → music agent
- Files → file agent
- Automations → automation agent

When you cannot do something directly, clearly say what you'd need.
Never apologize excessively. Just be useful."""


class ConversationAgent(BaseAgent):
    name = "conversation"
    description = "Primary conversational agent for general tasks"
    task_type = TaskType.SMART

    def get_system_prompt(self, ctx: AgentContext) -> str:
        device_hint = ""
        if ctx.device == "mobile":
            device_hint = "\n\nUser is on mobile — keep responses concise and scannable."
        elif ctx.device == "voice":
            device_hint = "\n\nUser is using voice — respond naturally as if speaking. No markdown, no lists."

        return SAM_IDENTITY + device_hint

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "remember_fact",
                    "description": "Save an important fact about the user to long-term memory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "description": "Short unique key for this fact"},
                            "value": {"type": "string", "description": "The fact to remember"},
                            "category": {
                                "type": "string",
                                "enum": ["personal", "preference", "work", "health", "general"],
                                "description": "Category for this memory"
                            }
                        },
                        "required": ["key", "value"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "recall_memory",
                    "description": "Search long-term memory for facts about the user",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "What to search for in memory"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for current information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

    async def execute_tool(self, tool_name: str, arguments: dict, ctx: AgentContext):
        if tool_name == "remember_fact":
            from models.schemas import MemoryFact
            fact = MemoryFact(
                key=arguments["key"],
                value=arguments["value"],
                category=arguments.get("category", "general"),
                source="assistant",
            )
            saved = await self.db.save_fact(fact)
            return {"saved": True, "key": saved.key}

        elif tool_name == "recall_memory":
            facts = await self.db.search_facts(arguments["query"])
            return {"facts": [{"key": f.key, "value": f.value} for f in facts]}

        elif tool_name == "web_search":
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(arguments["query"], max_results=5))
                return {"results": [{"title": r["title"], "body": r["body"], "url": r["href"]} for r in results]}
            except Exception as e:
                return {"error": str(e)}

        return await super().execute_tool(tool_name, arguments, ctx)
