"""Tests for run_review: conversion, chunking, retries, and fast-fail (fake LLM)."""

import pytest

from app.agents import base
from app.core.resilience import LLMQuotaExhaustedError
from app.schemas.findings import Category, RawFinding, ReviewOutput, Severity
from app.schemas.pr import FileDiff, PullRequestData
from app.tools import diff_chunker
from app.tools.diff_parser import parse_patch
from tests.llm_fakes import DAILY_429, SERVER_503, FakeLLM, FakeStructuredLLM, review_output


def _pr() -> PullRequestData:
    return PullRequestData(
        repo="o/r", number=1, title="t", author="a",
        base_branch="main", head_branch="x", head_sha="abc",
    )


def _file(num_lines: int, line_len: int = 5) -> FileDiff:
    body = "\n".join("+" + "x" * line_len for _ in range(num_lines))
    patch = f"@@ -0,0 +1,{num_lines} @@\n{body}"
    return FileDiff(
        path="app.py", status="added", additions=num_lines,
        patch=patch, hunks=parse_patch(patch),
    )


def _run(file_diff: FileDiff):
    return base.run_review(
        agent_name="bugs", category=Category.BUG, system_prompt="p",
        pr=_pr(), file_diff=file_diff,
    )


def _install(monkeypatch, outputs: list) -> FakeStructuredLLM:
    structured = FakeStructuredLLM(outputs)
    monkeypatch.setattr(base, "get_llm", lambda: FakeLLM(structured))
    return structured


def test_raw_findings_are_converted_and_clamped(monkeypatch):
    output = ReviewOutput(
        findings=[
            RawFinding(line=2, severity=Severity.HIGH, title=" T ", explanation="E",
                       suggestion="S", confidence=0.9),
            RawFinding(line=0, severity=Severity.LOW, title="U", explanation="E",
                       suggestion="S", confidence=1.7),
        ]
    )
    _install(monkeypatch, [output])

    findings = _run(_file(2))

    assert findings[0].file_path == "app.py"
    assert findings[0].title == "T"
    assert findings[0].agent == "bugs" and findings[0].category is Category.BUG
    assert findings[1].line == 1  # clamped up from 0
    assert findings[1].confidence == 1.0  # clamped down from 1.7


def test_large_file_is_reviewed_in_chunks_and_merged(monkeypatch):
    monkeypatch.setattr(diff_chunker, "MAX_CHUNK_CHARS", 1500)
    structured = _install(monkeypatch, [review_output(), review_output(), review_output()])

    findings = _run(_file(num_lines=60, line_len=60))

    assert structured.calls == 3
    assert len(findings) == 3


def test_transient_error_is_retried_inside_run_review(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)  # don't actually wait
    structured = _install(monkeypatch, [Exception(SERVER_503), review_output()])

    findings = _run(_file(2))

    assert structured.calls == 2
    assert len(findings) == 1


def test_quota_error_fails_fast_and_blocks_later_calls(monkeypatch):
    structured = _install(monkeypatch, [Exception(DAILY_429), review_output()])

    with pytest.raises(LLMQuotaExhaustedError):
        _run(_file(2))
    with pytest.raises(LLMQuotaExhaustedError):
        _run(_file(2))  # breaker is open: the LLM is not called again

    assert structured.calls == 1