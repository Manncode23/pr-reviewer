"""Shared fixtures for the test suite."""

import os
import threading
from dataclasses import dataclass

# Dummy settings so tests never depend on a real .env (must be set before first use).
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ["LANGSMITH_TRACING"] = "false"  # tests must never send traces

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from app.agents import aggregator  # noqa: E402
from app.agents.registry import SPECIALISTS  # noqa: E402
from app.api.deps import get_webhook_secret  # noqa: E402
from app.api.main import create_app  # noqa: E402
from app.core.resilience import quota_breaker  # noqa: E402
from app.graph.builder import build_review_graph  # noqa: E402
from app.services.review_manager import ReviewManager  # noqa: E402
from app.services.review_service import ReviewService  # noqa: E402
from tests.api_helpers import WEBHOOK_SECRET  # noqa: E402
from tests.fakes import AGENTS, FakeClient, make_finding  # noqa: E402


@pytest.fixture(autouse=True)
def reset_llm_breaker():
    """The circuit breaker is process-wide state, so isolate every test."""
    quota_breaker.reset()
    yield
    quota_breaker.reset()


@dataclass
class ApiEnv:
    client: TestClient
    app: FastAPI
    github: FakeClient
    calls: dict  # how many fake specialist runs happened


@pytest.fixture
def api_env(monkeypatch):
    calls = {"count": 0}
    lock = threading.Lock()

    def make(name):
        def run(pr, file_diff, static):
            with lock:
                calls["count"] += 1
            return [make_finding(name)]
        return run

    for name in AGENTS:
        monkeypatch.setitem(SPECIALISTS, name, make(name))
    monkeypatch.setattr(aggregator, "find_duplicate_groups", lambda findings: [])

    github = FakeClient()
    graph = build_review_graph(github, MemorySaver())
    manager = ReviewManager(ReviewService(graph, github))

    app = create_app(use_lifespan=False)
    app.state.manager = manager
    app.dependency_overrides[get_webhook_secret] = lambda: WEBHOOK_SECRET

    with TestClient(app) as client:
        yield ApiEnv(client=client, app=app, github=github, calls=calls)
    manager.shutdown()