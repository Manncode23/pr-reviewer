"""Forced re-runs and the degraded-review flag."""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agents import aggregator
from app.agents.registry import SPECIALISTS
from app.graph.builder import build_review_graph
from app.schemas.review import ReviewStatus
from app.services.review_service import ReviewService, ReviewStateError
from tests.api_helpers import STATUS_URL, wait_for_status
from tests.fakes import AGENTS, THREAD_ID, FakeClient, failing_specialist, make_finding

START = {"repo": "o/r", "pr_number": 1}


@pytest.fixture
def counting_service(monkeypatch):
    calls = {"count": 0}

    def make(name):
        def run(pr, file_diff, static):
            calls["count"] += 1
            return [make_finding(name)]
        return run

    for name in AGENTS:
        monkeypatch.setitem(SPECIALISTS, name, make(name))
    monkeypatch.setattr(aggregator, "find_duplicate_groups", lambda findings: [])

    client = FakeClient()
    service = ReviewService(build_review_graph(client, MemorySaver()), client)
    return service, calls


def test_reset_lets_the_same_commit_be_reviewed_again(counting_service):
    service, calls = counting_service

    service.start("o/r", 1)
    assert calls["count"] == 4

    service.reset(THREAD_ID)
    session = service.start("o/r", 1)

    assert calls["count"] == 8
    assert session.status is ReviewStatus.AWAITING_APPROVAL


def test_reset_is_refused_after_publishing(counting_service):
    service, _ = counting_service
    service.start("o/r", 1)
    service.approve(THREAD_ID, [0, 1, 2, 3])

    with pytest.raises(ReviewStateError):
        service.reset(THREAD_ID)


def test_api_force_reruns_an_existing_review(api_env):
    api_env.client.post("/reviews", json=START)
    wait_for_status(api_env.client, STATUS_URL, {"awaiting_approval"})
    assert api_env.calls["count"] == 4

    response = api_env.client.post("/reviews", json={**START, "force": True})

    assert response.status_code == 202
    assert response.json()["started"] is True
    wait_for_status(api_env.client, STATUS_URL, {"awaiting_approval"})
    assert api_env.calls["count"] == 8


def test_api_force_is_refused_after_publishing(api_env):
    api_env.client.post("/reviews", json=START)
    wait_for_status(api_env.client, STATUS_URL, {"awaiting_approval"})
    api_env.client.post(f"{STATUS_URL}/approve", json={"approve_all": True})

    response = api_env.client.post("/reviews", json={**START, "force": True})

    assert response.status_code == 409


def test_failed_reviewer_marks_the_review_degraded(api_env, monkeypatch):
    monkeypatch.setitem(SPECIALISTS, "style", failing_specialist)

    api_env.client.post("/reviews", json=START)
    body = wait_for_status(api_env.client, STATUS_URL, {"awaiting_approval"})

    result = body["result"]
    assert result["degraded"] is True
    assert len(result["errors"]) == 1
    assert "style" in result["errors"][0]