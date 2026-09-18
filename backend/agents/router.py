"""
SAM Ultra — Agent Router
Classifies user intent and routes to the right specialist agent.
Uses lightweight model for fast routing decisions.
"""
import re
from typing import Optional

from core.logging import get_logger
from models.schemas import AgentContext, AgentType

logger = get_logger("agents.router")


# Intent → Agent mapping with keyword patterns
ROUTING_RULES = [
    # Research & Web
    (AgentType.RESEARCH, [
        r"search\b", r"look up", r"find information", r"research\b",
        r"what is\b", r"who is\b", r"when did\b", r"news\b",
        r"latest\b", r"current\b", r"wikipedia",
    ]),

    # Computer control
    (AgentType.COMPUTER, [
        r"open\s+\w+", r"close\s+\w+", r"screenshot\b", r"click\b",
        r"type\s+", r"scroll\b", r"window\b", r"screen\b",
        r"take a screenshot", r"my desktop", r"on my (mac|computer|laptop)",
    ]),

    # Smart home
    (AgentType.SMART_HOME, [
        r"lights?\b", r"lamp\b", r"thermostat\b", r"temperature\b",
        r"lock\b", r"unlock\b", r"door\b", r"fan\b", r"ac\b",
        r"air conditioner", r"blinds?\b", r"curtains?\b",
        r"turn (on|off)\b", r"dim\b", r"bright",
    ]),

    # Calendar
    (AgentType.CALENDAR, [
        r"schedul", r"calendar\b", r"meeting\b", r"appointment\b",
        r"remind\b", r"event\b", r"tomorrow\b", r"next week",
        r"what('s| is) (on |happening )?today", r"my day\b",
        r"free time", r"available\b",
    ]),

    # Communication
    (AgentType.COMMUNICATION, [
        r"send\b.*(message|email|text|slack|whatsapp)",
        r"(message|email|text)\b.*send",
        r"reply\b", r"respond\b.*email", r"draft\b.*email",
        r"message\b.*(to|for)\b", r"email\b",
    ]),

    # Music
    (AgentType.MUSIC, [
        r"play\b", r"music\b", r"song\b", r"playlist\b",
        r"pause\b", r"skip\b", r"volume\b", r"spotify\b",
        r"shuffle\b", r"next (song|track)",
    ]),

    # Files
    (AgentType.FILE, [
        r"file\b", r"folder\b", r"document\b", r"download\b",
        r"open\b.*(doc|pdf|file)", r"save\b", r"move\b.*file",
        r"rename\b", r"delete\b.*file", r"find\b.*file",
    ]),

    # Coding
    (AgentType.CODING, [
        r"code\b", r"debug\b", r"function\b", r"class\b",
        r"error\b", r"bug\b", r"fix\b.*code", r"refactor\b",
        r"write\b.*(function|class|script)", r"terminal\b", r"git\b",
        r"python\b", r"javascript\b", r"typescript\b", r"sql\b",
    ]),

    # Automation
    (AgentType.AUTOMATION, [
        r"automat\w+", r"every (day|morning|hour|week)",
        r"when (i|my)\b", r"trigger\b", r"workflow\b",
        r"routine\b", r"schedule\s+task",
    ]),

    # Memory
    (AgentType.MEMORY, [
        r"remember\b", r"forgot\b", r"what did i (say|tell)",
        r"history\b", r"recall\b", r"my preference",
        r"do you know\b", r"have i (ever|told)",
    ]),
]


def route(ctx: AgentContext) -> str:
    """
    Route a user message to the appropriate agent.
    Returns agent name string.
    """
    message = ctx.user_message.lower()

    # Check each routing rule
    scores: dict[str, int] = {}
    for agent_type, patterns in ROUTING_RULES:
        score = sum(1 for p in patterns if re.search(p, message))
        if score > 0:
            scores[agent_type] = score

    if scores:
        best = max(scores, key=lambda k: scores[k])
        logger.info("routed", agent=best, score=scores[best], scores=scores)
        return best

    # Default to conversation
    return AgentType.CONVERSATION


async def get_agent(agent_name: str):
    """Lazy-load and return an agent instance by name."""
    from agents.conversation import ConversationAgent

    # Lazy import each agent to avoid circular imports
    agent_map = {
        AgentType.CONVERSATION: ConversationAgent,
    }

    # Try to import specialized agents (they may not all be built yet)
    try:
        from agents.research import ResearchAgent
        agent_map[AgentType.RESEARCH] = ResearchAgent
    except ImportError:
        pass

    try:
        from agents.coding import CodingAgent
        agent_map[AgentType.CODING] = CodingAgent
    except ImportError:
        pass

    cls = agent_map.get(agent_name, ConversationAgent)
    return cls()
