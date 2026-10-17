"""Central LLM factory.

Every agent gets its model from here, so model name, temperature,
retries, and concurrency limits are controlled in one place.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def get_llm() -> ChatGoogleGenerativeAI:
    """Return a shared Gemini chat model configured from settings."""
    settings = get_settings()
    logger.debug("Creating LLM client for model %s", settings.gemini_model)
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key.get_secret_value(),
        temperature=settings.llm_temperature,
        max_retries=settings.llm_max_retries,
    )


@lru_cache
def _get_semaphore() -> threading.BoundedSemaphore:
    return threading.BoundedSemaphore(get_settings().llm_max_concurrency)


@contextmanager
def llm_slot() -> Iterator[None]:
    """Limit how many LLM calls run at the same time.

    Parallel graph branches run in threads, so a threading semaphore keeps
    us under the Gemini free-tier rate limits.

    Usage:
        with llm_slot():
            response = llm.invoke(prompt)
    """
    sem = _get_semaphore()
    sem.acquire()
    try:
        yield
    finally:
        sem.release()


def message_text(message: BaseMessage) -> str:
    """Extract plain text from a model response.

    Gemini can return `content` as a string or as a list of parts,
    so we normalise it here once instead of in every agent.
    """
    content = message.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict) and part.get("type") == "text":
            parts.append(part.get("text", ""))
    return "".join(parts)