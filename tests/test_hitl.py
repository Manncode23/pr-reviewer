"""Human-in-the-loop and service tests (no network, no LLM)."""

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.agents import aggregator
from app.agents.registry import SPECIALISTS
from app.graph.builder import build_review_graph
from app.schemas.review import ReviewStatus
from app.services.review_service import ReviewService, ReviewStateError
from tests.fakes import (
    AGENTS,
    THREAD_ID,
    FakeClient,
    initial_state,
    make_finding,
    thread_config,
)


@pytest.fixture(autouse=True)
def no_llm_dedupe(monkeypatch):
    monkeypatch.setattr(aggregator, "find_duplicate_groups", lambda findings: [])


@pytest.fixture
def four_findings(monkeypatch):
    """Each fake agent reports one finding -> 4 findings reach the approval gate."""
    calls = {"count": 0}

    def make(name):
        def run(pr, file_diff, static):
            calls["count"] += 1
            return [make_finding(name)]
        return run

    for name in AGENTS:
        monkeypatch.setitem(SPECIALISTS, name, make(name))
    return calls


def _paused_graph():
    client = FakeClient()
    graph = build_review_graph(client=client, checkpointer=MemorySaver())
    config = thread_config()
    graph.invoke(initial_state(), config)
    return graph, client, config


def test_graph_pauses_before_posting(four_findings):
    graph, client, config = _paused_graph()

    assert graph.get_state(config).next == ("approval",)
    assert client.posted == []


def test_resume_posts_only_approved_findings(four_findings):
    graph, client, config = _paused_graph()

    graph.invoke(Command(resume={"approved": [0, 2]}), config)

    assert len(client.posted) == 1
    comments = client.posted[0]["comments"]
    assert len(comments) == 2
    assert all(c["side"] == "RIGHT" and c["path"] == "app/service.py" for c in comments)
    assert graph.get_state(config).next == ()
    assert graph.get_state(config).values["published"] is True


def test_rejecting_everything_posts_nothing(four_findings):
    graph, client, config = _paused_graph()

    graph.invoke(Command(resume={"approved": []}), config)

    assert client.posted == []
    assert graph.get_state(config).values["published"] is False


def test_invalid_indices_are_ignored(four_findings):
    graph, client, config = _paused_graph()

    graph.invoke(Command(resume={"approved": [0, 99, -1]}), config)

    assert len(client.posted[0]["comments"]) == 1


def test_no_findings_means_no_pause_and_no_post(monkeypatch):
    for name in AGENTS:
        monkeypatch.setitem(SPECIALISTS, name, lambda pr, fd, st: [])

    graph, client, config = _paused_graph()

    assert graph.get_state(config).next == ()
    assert client.posted == []


def test_service_start_is_idempotent_per_commit(four_findings):
    client = FakeClient()
    service = ReviewService(build_review_graph(client, MemorySaver()), client)

    first = service.start("o/r", 1)
    calls_after_first = four_findings["count"]
    second = service.start("o/r", 1)

    assert first.thread_id == second.thread_id == THREAD_ID
    assert second.status is ReviewStatus.AWAITING_APPROVAL
    assert four_findings["count"] == calls_after_first  # no second review ran


def test_service_approve_then_double_approve_is_rejected(four_findings):
    client = FakeClient()
    service = ReviewService(build_review_graph(client, MemorySaver()), client)
    session = service.start("o/r", 1)

    done = service.approve(session.thread_id, list(range(len(session.result.findings))))

    assert done.status is ReviewStatus.COMPLETED
    assert done.result.published is True
    with pytest.raises(ReviewStateError):
        service.approve(session.thread_id, [0])
        