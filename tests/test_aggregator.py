import pytest

from app.agents import aggregator
from app.agents.aggregator import (
    aggregate_findings,
    apply_groups,
    exact_duplicate_groups,
    rank_findings,
)
from app.schemas.findings import Category, Finding, Severity


def _f(agent="bugs", line=11, severity=Severity.MEDIUM, confidence=0.9,
       category=Category.BUG, title="Bare except", path="app.py") -> Finding:
    return Finding(
        file_path=path, line=line, severity=severity, category=category,
        title=title, explanation="x", suggestion="y",
        confidence=confidence, agent=agent,
    )


def test_apply_groups_merges_and_keeps_most_severe():
    findings = [
        _f(agent="style", severity=Severity.LOW, category=Category.STYLE),
        _f(agent="bugs", severity=Severity.MEDIUM, category=Category.BUG),
    ]
    result = apply_groups(findings, [[0, 1]])

    assert len(result) == 1
    assert result[0].agent == "bugs"
    assert result[0].severity is Severity.MEDIUM
    assert result[0].also_flagged_by == ["style"]


def test_apply_groups_ignores_cross_file_groups():
    findings = [_f(path="a.py"), _f(agent="style", path="b.py")]
    assert len(apply_groups(findings, [[0, 1]])) == 2


def test_apply_groups_ignores_lines_far_apart():
    findings = [_f(line=1), _f(agent="style", line=20)]
    assert len(apply_groups(findings, [[0, 1]])) == 2


def test_apply_groups_ignores_bad_indices_and_overlaps():
    three = [_f(line=5), _f(agent="style", line=5), _f(agent="tests", line=6)]

    assert len(apply_groups(three, [[0, 5]])) == 3            # index out of range
    assert len(apply_groups(three, [[0, 1], [1, 2]])) == 2    # second group overlaps


def test_exact_duplicate_groups():
    findings = [_f(), _f(agent="style"), _f(title="Different", line=3)]
    assert exact_duplicate_groups(findings) == [[0, 1]]


def test_rank_findings_orders_by_severity_then_confidence():
    low = _f(severity=Severity.LOW, confidence=0.9, title="low")
    high_unsure = _f(severity=Severity.HIGH, confidence=0.5, title="high-unsure")
    high_sure = _f(severity=Severity.HIGH, confidence=0.9, title="high-sure")

    ranked = rank_findings([low, high_unsure, high_sure])
    assert [f.title for f in ranked] == ["high-sure", "high-unsure", "low"]


def test_aggregate_falls_back_to_exact_dedupe_when_llm_fails(monkeypatch):
    def boom(findings):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(aggregator, "find_duplicate_groups", boom)
    result = aggregate_findings([_f(), _f(agent="style")])
    assert len(result) == 1


def test_aggregate_skips_llm_for_a_single_finding(monkeypatch):
    def must_not_run(findings):
        pytest.fail("LLM should not be called for fewer than 2 findings")

    monkeypatch.setattr(aggregator, "find_duplicate_groups", must_not_run)
    assert len(aggregate_findings([_f()])) == 1