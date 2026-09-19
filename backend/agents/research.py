"""
SAM Ultra — Research Agent
Deep web research with synthesis. Uses DuckDuckGo + page fetching.
"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any

from agents.base import BaseAgent
from core.ai_provider import TaskType
from models.schemas import AgentContext


class ResearchAgent(BaseAgent):
    name = "research"
    description = "Deep research agent with web search and synthesis"
    task_type = TaskType.REASON

    def get_system_prompt(self, ctx: AgentContext) -> str:
        return """You are SAM's Research Module — a deep research engine.

Your job:
1. Search for comprehensive information on the topic
2. Synthesize multiple sources
3. Present findings clearly with key facts highlighted
4. Cite sources at the end

Be thorough but structured. Use the search and fetch tools to get real data."""

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "num_results": {"type": "integer", "default": 8}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_page",
                    "description": "Fetch and extract text from a webpage",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                        },
                        "required": ["url"]
                    }
                }
            }
        ]

    async def execute_tool(self, tool_name: str, arguments: dict, ctx: AgentContext) -> Any:
        if tool_name == "web_search":
            try:
                from ddgs import DDGS
                n = arguments.get("num_results", 8)
                with DDGS() as ddgs:
                    results = list(ddgs.text(arguments["query"], max_results=n))
                return {
                    "results": [
                        {"title": r["title"], "body": r["body"], "url": r["href"]}
                        for r in results
                    ]
                }
            except Exception as e:
                return {"error": str(e)}

        elif tool_name == "fetch_page":
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        arguments["url"],
                        timeout=aiohttp.ClientTimeout(total=10),
                        headers={"User-Agent": "Mozilla/5.0 SAM-Research/1.0"}
                    ) as resp:
                        html = await resp.text()

                soup = BeautifulSoup(html, "html.parser")
                # Remove scripts/styles
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                text = soup.get_text(separator="\n", strip=True)
                # Trim to reasonable length
                lines = [l for l in text.split("\n") if len(l.strip()) > 30]
                return {"text": "\n".join(lines[:100]), "url": arguments["url"]}
            except Exception as e:
                return {"error": str(e), "url": arguments["url"]}

        return await super().execute_tool(tool_name, arguments, ctx)
