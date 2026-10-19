"""Shared fixtures for API tests."""

import threading
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from app.agents import aggregator
from app.agents.registry import SPECIALISTS
from app.api.deps import get_webhook_secret
from app.api.main import create_app
from app.graph.builder import build_review_graph
from app.services.review_manager import ReviewManager
from app.services.review_service import ReviewService
from tests.api_helpers import WEBHOOK_SECRET
from tests.fakes import AGENTS, FakeClient, make_finding


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