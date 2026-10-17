"""Run bandit (security linter) on a Python file."""

import json
import sys
from pathlib import Path

from app.core.logging import get_logger
from app.schemas.static import ToolIssue
from app.tools.process import ToolRunError, run_cli

logger = get_logger(__name__)


def run_bandit(source_path: Path) -> list[ToolIssue]:
    try:
        proc = run_cli(
            [sys.executable, "-m", "bandit", "-f", "json", "-q", str(source_path)]
        )
    except ToolRunError as exc:
        logger.warning("bandit failed: %s", exc)
        return []

    if not proc.stdout.strip():
        return []

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        logger.warning("bandit returned non-JSON output: %s", proc.stdout[:200])
        return []

    return [
        ToolIssue(
            tool="bandit",
            rule_id=result["test_id"],
            line=result["line_number"],
            message=result["issue_text"],
            severity=result.get("issue_severity"),
        )
        for result in data.get("results", [])
    ]