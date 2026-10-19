"""Retry, backoff, and circuit-breaking for LLM calls.

Errors are classified from their text, because Gemini failures surface as
different exception classes depending on library versions.
"""

import random
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

from app.core.config import get_settings
from app.core.logging import get_logger

T = TypeVar("T")
logger = get_logger(__name__)

MAX_BACKOFF_SECONDS = 60.0  # never sleep longer than this inside one call
DEFAULT_BREAKER_SECONDS = 3600.0
MAX_BREAKER_SECONDS = 24 * 3600.0

ErrorKind = Literal["quota", "rate_limit", "transient", "fatal"]

_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s")
_RETRY_IN_RE = re.compile(r"retry in ([0-9hms.]+)", re.IGNORECASE)
_DURATION_PART_RE = re.compile(r"(\d+(?:\.\d+)?)([hms])")
_STATUS_429_RE = re.compile(r"\b429\b")
_SERVER_ERROR_RE = re.compile(r"\b(500|502|503|504)\b")
_MODEL_RE = re.compile(r"model:\s*([\w.\-]+)")


class LLMQuotaExhaustedError(Exception):
    """The LLM quota is used up, so retrying now is pointless."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class ErrorInfo:
    kind: ErrorKind
    retry_after: float | None = None  # seconds, when the API told us


def format_duration(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _parse_retry_after(text: str) -> float | None:
    match = _RETRY_DELAY_RE.search(text)
    if match:
        return float(match.group(1))
    match = _RETRY_IN_RE.search(text)
    if match:
        units = {"h": 3600, "m": 60, "s": 1}
        total = sum(
            float(value) * units[unit]
            for value, unit in _DURATION_PART_RE.findall(match.group(1))
        )
        return total or None
    return None


def classify_error(exc: BaseException) -> ErrorInfo:
    text = str(exc)
    upper = text.upper()

    if _STATUS_429_RE.search(text) or "RESOURCE_EXHAUSTED" in upper:
        retry_after = _parse_retry_after(text)
        per_day = "PERDAY" in upper.replace("_", "")
        if per_day or (retry_after is not None and retry_after > MAX_BACKOFF_SECONDS):
            return ErrorInfo("quota", retry_after)
        return ErrorInfo("rate_limit", retry_after)

    if (
        _SERVER_ERROR_RE.search(text)
        or "UNAVAILABLE" in upper
        or "DEADLINE_EXCEEDED" in upper
        or "TIMED OUT" in upper
        or "TIMEOUT" in upper
        or isinstance(exc, (TimeoutError, ConnectionError))
    ):
        return ErrorInfo("transient")

    return ErrorInfo("fatal")


def short_error(exc: BaseException) -> str:
    """One readable line instead of a wall of JSON."""
    if isinstance(exc, LLMQuotaExhaustedError):
        return str(exc)

    info = classify_error(exc)
    text = str(exc)
    if info.kind == "quota":
        model = _MODEL_RE.search(text)
        target = f" for {model.group(1)}" if model else ""
        wait = f", resets in ~{format_duration(info.retry_after)}" if info.retry_after else ""
        return f"LLM quota exhausted{target}{wait}"
    if info.kind == "rate_limit":
        return "LLM rate limit hit"
    if info.kind == "transient":
        return "LLM service temporarily unavailable"

    first_line = text.strip().splitlines()[0] if text.strip() else type(exc).__name__
    return first_line[:200]


class CircuitBreaker:
    """Once the quota is gone, stop calling the LLM until it should be back."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._open_until = 0.0
        self._reason = ""

    def check(self) -> None:
        with self._lock:
            remaining = self._open_until - self._clock()
            reason = self._reason
        if remaining > 0:
            raise LLMQuotaExhaustedError(
                f"{reason} (blocking LLM calls for another {format_duration(remaining)})",
                retry_after=remaining,
            )

    def trip(self, seconds: float, reason: str) -> None:
        with self._lock:
            self._open_until = self._clock() + seconds
            self._reason = reason
        logger.error("Circuit breaker open for %s: %s", format_duration(seconds), reason)

    def reset(self) -> None:
        with self._lock:
            self._open_until = 0.0
            self._reason = ""


quota_breaker = CircuitBreaker()


def _backoff_delay(info: ErrorInfo, attempt: int) -> float:
    if info.retry_after is not None:
        return min(info.retry_after, MAX_BACKOFF_SECONDS) + random.uniform(0.0, 1.0)
    return min(2.0**attempt, MAX_BACKOFF_SECONDS) * random.uniform(0.75, 1.25)


def call_with_retries(
    fn: Callable[[], T],
    *,
    label: str = "llm",
    max_attempts: int | None = None,
    sleep: Callable[[float], None] | None = None,
    breaker: CircuitBreaker | None = None,
) -> T:
    """Call fn, retrying only the failures that retrying can fix."""
    breaker = breaker or quota_breaker
    attempts = (
        max_attempts if max_attempts is not None else get_settings().llm_max_retries + 1
    )
    attempt = 0

    while True:
        attempt += 1
        breaker.check()
        try:
            return fn()
        except LLMQuotaExhaustedError:
            raise
        except Exception as exc:  # noqa: BLE001 - we classify everything here
            info = classify_error(exc)

            if info.kind == "quota":
                seconds = min(info.retry_after or DEFAULT_BREAKER_SECONDS, MAX_BREAKER_SECONDS)
                reason = short_error(exc)
                breaker.trip(seconds, reason)
                raise LLMQuotaExhaustedError(reason, retry_after=seconds) from exc

            if info.kind == "fatal" or attempt >= attempts:
                raise

            delay = _backoff_delay(info, attempt)
            logger.warning(
                "[%s] %s error (attempt %d/%d); retrying in %.1fs",
                label, info.kind, attempt, attempts, delay,
            )
            (sleep or time.sleep)(delay)