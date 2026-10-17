"""Run static analysis on a changed file and keep only issues on added lines."""

import tempfile
from pathlib import Path

from app.schemas.pr import FileDiff, LineKind
from app.schemas.static import StaticAnalysisResult, ToolIssue
from app.tools.bandit_runner import run_bandit
from app.tools.ruff_runner import run_ruff

PYTHON_SUFFIXES = {".py"}


def _added_line_numbers(file_diff: FileDiff) -> set[int]:
    return {
        line.new_line
        for hunk in file_diff.hunks
        for line in hunk.lines
        if line.kind is LineKind.ADDED and line.new_line is not None
    }


def _only_added(issues: list[ToolIssue], added: set[int]) -> list[ToolIssue]:
    return [issue for issue in issues if issue.line in added]


def analyze_python_file(file_diff: FileDiff, content: str) -> StaticAnalysisResult:
    """Lint the full file content, then keep issues on lines this PR added."""
    if Path(file_diff.path).suffix not in PYTHON_SUFFIXES:
        return StaticAnalysisResult()

    added = _added_line_numbers(file_diff)
    if not added:
        return StaticAnalysisResult()

    with tempfile.TemporaryDirectory() as tmp:
        source_path = Path(tmp) / Path(file_diff.path).name
        source_path.write_text(content, encoding="utf-8", newline="")
        bandit_issues = run_bandit(source_path)
        ruff_issues = run_ruff(source_path)

    return StaticAnalysisResult(
        bandit=_only_added(bandit_issues, added),
        ruff=_only_added(ruff_issues, added),
    )