import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents import base
from app.schemas.findings import Category, Finding, ReviewOutput, Severity
from app.tools.diff_parser import commentable_lines
from eval.dataset import CASES, resolve_line
from eval.llm_cache import CachingLLM, EvalBudgetExhausted
from eval.runner import build_pr, evaluate
from eval.scoring import CaseScore, score_case, summarize
from tests.llm_fakes import FakeLLM, FakeStructuredLLM, review_output

SQLI = next(c for c in CASES if c.id == "sqli_fstring")
SQLI_ISSUE = SQLI.expected[0]
SQLI_FILE = SQLI_ISSUE.file
SQLI_LINE = resolve_line(SQLI, SQLI_ISSUE)
CLEAN = next(c for c in CASES if c.is_clean)
CLEAN_FILE = next(iter(CLEAN.files))


def _finding(path: str, line: int, severity=Severity.HIGH, title="T") -> Finding:
    return Finding(
        file_path=path, line=line, severity=severity, category=Category.BUG,
        title=title, explanation="E", suggestion="S", confidence=0.9, agent="bugs",
    )


def test_dataset_is_well_formed():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids))
    assert any(c.is_clean for c in CASES) and any(not c.is_clean for c in CASES)
    for case in CASES:
        for issue in case.expected:
            assert resolve_line(case, issue) >= 1  # raises if the anchor is missing
            assert issue.category in {"security", "bug"}


def test_finding_near_the_labeled_line_counts_as_a_match():
    score = score_case(SQLI, [_finding(SQLI_FILE, SQLI_LINE + 1)])

    assert score.matched_expected == 1 and score.missed == []
    assert score.matched_findings == 1 and score.false_positives == []


def test_distant_finding_is_a_false_positive_and_the_issue_is_missed():
    score = score_case(SQLI, [_finding(SQLI_FILE, SQLI_LINE + 10)])

    assert score.missed == [SQLI_ISSUE.label]
    assert score.matched_findings == 0
    assert len(score.false_positives) == 1


def test_every_finding_on_a_clean_case_is_a_false_positive():
    findings = [
        _finding(CLEAN_FILE, 1, severity=Severity.HIGH),
        _finding(CLEAN_FILE, 2, severity=Severity.LOW),
    ]
    score = score_case(CLEAN, findings)

    assert score.expected == 0 and score.matched_findings == 0
    assert score.false_alarms == 1  # only the HIGH one is "medium or worse"


def test_summary_computes_precision_recall_and_f1():
    scores = [
        CaseScore("a", False, expected=2, findings=2, matched_expected=1, matched_findings=1),
        CaseScore("b", False, expected=2, findings=3, matched_expected=2, matched_findings=2),
    ]
    summary = summarize(scores)

    assert summary["recall"] == pytest.approx(3 / 4)
    assert summary["precision"] == pytest.approx(3 / 5)
    assert summary["f1"] == pytest.approx(2 * 0.6 * 0.75 / (0.6 + 0.75))


def test_build_pr_marks_every_line_added_and_hides_the_label():
    pr = build_pr(SQLI)
    line_count = len(SQLI.files[SQLI_FILE].splitlines())

    assert commentable_lines(pr.files[0]) == set(range(1, line_count + 1))
    assert SQLI.id not in pr.title and pr.body == ""


def test_cache_serves_repeat_calls_without_the_llm(tmp_path):
    inner = FakeStructuredLLM([review_output()])
    caching = CachingLLM(FakeLLM(inner), tmp_path, "m", max_live_calls=5)
    structured = caching.with_structured_output(ReviewOutput)
    messages = [SystemMessage(content="s"), HumanMessage(content="h")]

    first = structured.invoke(messages)
    second = structured.invoke(messages)

    assert inner.calls == 1
    assert second == first
    assert caching.live_calls == 1 and caching.cache_hits == 1


def test_cache_enforces_the_live_call_budget(tmp_path):
    inner = FakeStructuredLLM([review_output(), review_output()])
    caching = CachingLLM(FakeLLM(inner), tmp_path, "m", max_live_calls=1)
    structured = caching.with_structured_output(ReviewOutput)
    first, second = [HumanMessage(content="a")], [HumanMessage(content="b")]

    structured.invoke(first)
    with pytest.raises(EvalBudgetExhausted):
        structured.invoke(second)
    structured.invoke(first)  # already cached, so still served

    assert inner.calls == 1


def test_evaluate_scores_a_case_end_to_end(tmp_path, monkeypatch):
    inner = FakeStructuredLLM([review_output(line=SQLI_LINE), ReviewOutput(findings=[])])
    caching = CachingLLM(FakeLLM(inner), tmp_path, "m", max_live_calls=10)
    monkeypatch.setattr(base, "get_llm", lambda: caching)

    report = evaluate([SQLI], agents=("security", "bugs"))

    assert report.pending == [] and report.errored == {}
    assert report.scores[0].matched_expected == 1
    assert report.scores[0].missed == []


def test_evaluate_marks_a_case_pending_when_the_budget_runs_out(tmp_path, monkeypatch):
    inner = FakeStructuredLLM([review_output()])
    caching = CachingLLM(FakeLLM(inner), tmp_path, "m", max_live_calls=0)
    monkeypatch.setattr(base, "get_llm", lambda: caching)

    report = evaluate([SQLI], agents=("security", "bugs"))

    assert report.pending == [SQLI.id]
    assert report.scores == []
    assert inner.calls == 0