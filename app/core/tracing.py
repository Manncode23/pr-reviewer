"""LangSmith tracing setup.

LangChain reads tracing settings from real environment variables, but our
config lives in .env (read by pydantic, not exported), so we export it here.
"""

import os

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def configure_tracing(settings: Settings | None = None) -> bool:
    """Turn on LangSmith tracing if it is enabled and a key is present."""
    settings = settings or get_settings()
    if not settings.langsmith_tracing:
        return False

    key = settings.langsmith_api_key.get_secret_value() if settings.langsmith_api_key else ""
    if not key:
        logger.warning("LANGSMITH_TRACING is on but LANGSMITH_API_KEY is empty; tracing disabled")
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    logger.info("LangSmith tracing enabled (project: %s)", settings.langsmith_project)
    return True