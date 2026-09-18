"""
Structured logging for JARVIS.
Every tool call, agent action, and error is logged with context.
"""
import structlog
import logging
import sys
from core.config import settings


def setup_logging():
    log_level = logging.DEBUG if settings.debug else logging.INFO

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if settings.debug
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
    )


def get_logger(name: str):
    return structlog.get_logger(name)
