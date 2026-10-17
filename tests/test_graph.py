"""Graph tests using a fake GitHub client and fake specialists (no network/LLM)."""

import pytest

from app.agents import aggregator
from app.agents.registry import SPECIALISTS
from app.graph.builder import build_review_graph
from app.schemas.findings import Category, Finding, Severity
from app.schemas.pr import FileDiff, PullRequestData
from app.tools.diff_parser import parse_patch

PATCH = "@@ -0,0 +1,2 @@\n+def f():\n+    return 1"
AGENTS = {"security", "bugs", "style", "tests"}


@pytest.fixture(autouse=True)
def no_llm_dedupe(monkeypatch):
    """Keep graph tests offline: pretend the LLM found no duplicates."""
    monkeypatch.setattr(aggregator, "find_duplicate_groups", lambda findings: [])


class FakeClient:
    def get_pull_request(self, repo, number):
        return PullRequestData(
            repo=repo, number=number, title="t", author="a",
            base_branch="main", head_branch="x", head_sha="abc123",
            files=[
                FileDiff(
                    path="app/service.py", status="added", additions=2,
                    patch=PATCH, hunks=parse_patch(PATCH),
                )
            ],
        )

    def get_file_content(self, repo, path, ref):
        return None  # skips static analysis


def _finding(name, line=1, severity=Severity.LOW, title=None) -> Finding:
    return Finding(
        file_path="app/service.py", line=line, severity=severity,
        category=Category.BUG, title=title or name, explanation="x",
        suggestion="y", confidence=0.9, agent=name,
    )


def _fake_specialist(name: str):
    def run(pr, file_diff, static):
        return [_finding(name)]
    return run


def _failing_specialist(pr, file_diff, static):
    raise RuntimeError("boom")


def _invoke():
    graph = build_review_graph(client=FakeClient())
    return graph.invoke({"repo": "o/r", "pr_number": 1, "findings": [], "errors": []})


def test_graph_has_expected_nodes():
    graph = build_review_graph(client=FakeClient())
    nodes = set(graph.get_graph().nodes)
    assert {
        "fetch_pr", "preprocess", "supervisor", "specialist", "validator", "aggregator"
    } <= nodes


def test_graph_fans_out_and_merges_findings(monkeypatch):
    for name in AGENTS:
        monkeypatch.setitem(SPECIALISTS, name, _fake_specialist(name))

    state = _invoke()

    assert {f.agent for f in state["findings"]} == AGENTS
    assert state["errors"] == []


def test_one_failing_specialist_does_not_sink_the_review(monkeypatch):
    for name in AGENTS:
        monkeypatch.setitem(SPECIALISTS, name, _fake_specialist(name))
    monkeypatch.setitem(SPECIALISTS, "style", _failing_specialist)

    state = _invoke()

    assert {f.agent for f in state["findings"]} == AGENTS - {"style"}
    assert len(state["errors"]) == 1
    assert "style" in state["errors"][0]


def test_validator_drops_bad_findings_and_final_list_is_ranked(monkeypatch):
    for name in AGENTS:
        monkeypatch.setitem(SPECIALISTS, name, _fake_specialist(name))

    def bugs(pr, file_diff, static):
        return [
            _finding("bugs", line=99, title="hallucinated line"),
            _finding("bugs", line=1, severity=Severity.HIGH, title="real bug"),
        ]

    monkeypatch.setitem(SPECIALISTS, "bugs", bugs)

    state = _invoke()
    final = state["final_findings"]

    assert len(state["dropped"]) == 1
    assert all(f.line != 99 for f in final)
    assert final[0].title == "real bug"  # highest severity first