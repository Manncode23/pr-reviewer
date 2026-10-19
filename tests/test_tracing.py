import os

from app.core.config import Settings
from app.core.tracing import configure_tracing
from app.services.review_service import _run_config

TRACE_VARS = ("LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT")


def _settings(**overrides) -> Settings:
    return Settings(
        google_api_key="g", github_token="t", database_url="postgresql://x", **overrides
    )


def _protect_env(monkeypatch) -> None:
    for name in TRACE_VARS:
        monkeypatch.setenv(name, "placeholder")  # registers the original value for restore


def test_tracing_is_exported_to_the_environment_when_enabled(monkeypatch):
    _protect_env(monkeypatch)

    enabled = configure_tracing(
        _settings(langsmith_tracing=True, langsmith_api_key="ls-key", langsmith_project="proj")
    )

    assert enabled is True
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "ls-key"
    assert os.environ["LANGSMITH_PROJECT"] == "proj"


def test_tracing_stays_off_when_disabled_or_without_a_key(monkeypatch):
    _protect_env(monkeypatch)

    assert configure_tracing(_settings(langsmith_tracing=False)) is False
    assert configure_tracing(_settings(langsmith_tracing=True, langsmith_api_key=None)) is False
    assert os.environ["LANGSMITH_TRACING"] == "placeholder"  # left untouched


def test_run_config_labels_the_trace():
    config = _run_config("o/r#7@abc123")

    assert config["configurable"] == {"thread_id": "o/r#7@abc123"}
    assert config["metadata"] == {"repo": "o/r", "pr_number": 7, "head_sha": "abc123"}
    assert config["run_name"] == "pr-review"


def test_run_config_tolerates_unusual_thread_ids():
    assert _run_config("weird")["configurable"]["thread_id"] == "weird"