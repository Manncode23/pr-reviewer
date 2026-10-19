"""Graph tests: fake client, fake specialists, in-memory checkpointer."""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agents import aggregator
from app.agents.registry import SPECIALISTS
from app.graph.builder import build_review_graph
from app.schemas.findings import Severity
from tests.fakes import (
    AGENTS,
    FakeClient,
    failing_specialist,
    fake_specialist,
    initial_state,
    make_finding,
    thread_config,
)


@pytest.fixture(autouse=True)
def no_llm_dedupe(monkeypatch):
    """Keep graph tests offline: pretend the LLM found no duplicates."""
    monkeypatch.setattr(aggregator, "find_duplicate_groups", lambda findings: [])


def _run() -> dict:
    graph = build_review_graph(client=FakeClient(), checkpointer=MemorySaver())
    config = thread_config()
    graph.invoke(initial_state(), config)  # pauses at the approval step
    return graph.get_state(config).values


def test_graph_has_expected_nodes():
    graph = build_review_graph(client=FakeClient(), checkpointer=MemorySaver())
    nodes = set(graph.get_graph().nodes)
    assert {
        "fetch_pr", "preprocess", "supervisor", "specialist",
        "validator", "aggregator", "approval", "publisher",
    } <= nodes


def test_graph_fans_out_and_merges_findings(monkeypatch):
    for name in AGENTS:
        monkeypatch.setitem(SPECIALISTS, name, fake_specialist(name))

    values = _run()

    assert {f.agent for f in values["findings"]} == AGENTS
    assert values["errors"] == []


def test_one_failing_specialist_does_not_sink_the_review(monkeypatch):
    for name in AGENTS:
        monkeypatch.setitem(SPECIALISTS, name, fake_specialist(name))
    monkeypatch.setitem(SPECIALISTS, "style", failing_specialist)

    values = _run()

    assert {f.agent for f in values["findings"]} == AGENTS - {"style"}
    assert len(values["errors"]) == 1
    assert "style" in values["errors"][0]


def test_validator_drops_bad_findings_and_final_list_is_ranked(monkeypatch):
    for name in AGENTS:
        monkeypatch.setitem(SPECIALISTS, name, fake_specialist(name))

    def bugs(pr, file_diff, static):
        return [
            make_finding("bugs", line=99, title="hallucinated line"),
            make_finding("bugs", line=1, severity=Severity.HIGH, title="real bug"),
        ]

    monkeypatch.setitem(SPECIALISTS, "bugs", bugs)

    values = _run()
    final = values["final_findings"]

    assert len(values["dropped"]) == 1
    assert all(f.line != 99 for f in final)
    assert final[0].title == "real bug"  # highest severity first