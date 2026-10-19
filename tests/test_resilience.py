import pytest

from app.core.resilience import (
    CircuitBreaker,
    LLMQuotaExhaustedError,
    call_with_retries,
    classify_error,
    short_error,
)
from tests.llm_fakes import DAILY_429, PER_MINUTE_429, SERVER_503


class Recorder:
    """Stands in for time.sleep and records the delays requested."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def _flaky(*errors, result="ok"):
    """A function that raises each error in turn, then returns `result`."""
    queue = list(errors)
    state = {"calls": 0}

    def fn():
        state["calls"] += 1
        if queue:
            raise queue.pop(0)
        return result

    return fn, state


def test_daily_quota_is_classified_as_quota():
    info = classify_error(Exception(DAILY_429))
    assert info.kind == "quota"
    assert info.retry_after == pytest.approx(31774, abs=1)


def test_per_minute_rate_limit_is_classified_as_rate_limit():
    info = classify_error(Exception(PER_MINUTE_429))
    assert info.kind == "rate_limit"
    assert info.retry_after == pytest.approx(12, abs=1)


def test_server_errors_are_transient_and_unknown_errors_fatal():
    assert classify_error(Exception(SERVER_503)).kind == "transient"
    assert classify_error(TimeoutError("read timed out")).kind == "transient"
    assert classify_error(ValueError("bad schema")).kind == "fatal"


def test_short_error_is_concise_for_quota():
    text = short_error(Exception(DAILY_429))
    assert "gemini-3.8-flash" in text
    assert "8h49m" in text
    assert len(text) < 100


def test_transient_error_is_retried_then_succeeds():
    fn, state = _flaky(Exception(SERVER_503))
    sleeper = Recorder()

    result = call_with_retries(
        fn, max_attempts=3, sleep=sleeper, breaker=CircuitBreaker()
    )

    assert result == "ok"
    assert state["calls"] == 2
    assert len(sleeper.delays) == 1
    assert 1.5 <= sleeper.delays[0] <= 2.5  # 2s backoff with jitter


def test_rate_limit_waits_for_the_advised_delay():
    fn, _ = _flaky(Exception(PER_MINUTE_429))
    sleeper = Recorder()

    call_with_retries(fn, max_attempts=3, sleep=sleeper, breaker=CircuitBreaker())

    assert 12 <= sleeper.delays[0] <= 13


def test_daily_quota_fails_fast_and_opens_the_breaker():
    fn, state = _flaky(Exception(DAILY_429))
    sleeper = Recorder()
    breaker = CircuitBreaker()

    with pytest.raises(LLMQuotaExhaustedError) as excinfo:
        call_with_retries(fn, max_attempts=4, sleep=sleeper, breaker=breaker)

    assert state["calls"] == 1  # no retries
    assert sleeper.delays == []  # no waiting
    assert "quota exhausted" in str(excinfo.value)
    with pytest.raises(LLMQuotaExhaustedError):
        breaker.check()


def test_open_breaker_blocks_calls_until_it_expires():
    now = {"t": 0.0}
    breaker = CircuitBreaker(clock=lambda: now["t"])
    breaker.trip(100, "quota gone")
    fn, state = _flaky()

    with pytest.raises(LLMQuotaExhaustedError):
        call_with_retries(fn, max_attempts=2, breaker=breaker)
    assert state["calls"] == 0  # the LLM was never called

    now["t"] = 101.0
    assert call_with_retries(fn, max_attempts=2, breaker=breaker) == "ok"


def test_fatal_errors_are_not_retried():
    fn, state = _flaky(ValueError("bad schema"))

    with pytest.raises(ValueError):
        call_with_retries(fn, max_attempts=4, sleep=Recorder(), breaker=CircuitBreaker())

    assert state["calls"] == 1


def test_gives_up_after_max_attempts():
    fn, state = _flaky(*[Exception(SERVER_503) for _ in range(10)])
    sleeper = Recorder()

    with pytest.raises(Exception, match="UNAVAILABLE"):
        call_with_retries(fn, max_attempts=3, sleep=sleeper, breaker=CircuitBreaker())

    assert state["calls"] == 3
    assert len(sleeper.delays) == 2