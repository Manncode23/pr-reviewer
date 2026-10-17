"""Run ruff (fast Python linter) on a Python file."""

import json
import sys
from pathlib import Path

from app.core.logging import get_logger
from app.schemas.static import ToolIssue
from app.tools.process import ToolRunError, run_cli

logger = get_logger(__name__)

# E = pycodestyle errors, F = pyflakes, W = warnings, B = bugbear
RUFF_SELECT = "E,F,W,B"
RUFF_IGNORE = "E501"  # line length is too noisy for review comments


def run_ruff(source_path: Path) -> list[ToolIssue]:
    try:
        proc = run_cli(
            [
                sys.executable, "-m", "ruff", "check",
                "--isolated", "--no-cache", "--exit-zero",
                "--output-format", "json",
                "--select", RUFF_SELECT,
                "--ignore", RUFF_IGNORE,
                str(source_path),
            ]
        )
    except ToolRunError as exc:
        logger.warning("ruff failed: %s", exc)
        return []

    if not proc.stdout.strip():
        return []

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        logger.warning("ruff returned non-JSON output: %s", proc.stdout[:200])
        return []

    return [
        ToolIssue(
            tool="ruff",
            rule_id=item.get("code") or "syntax-error",
            line=item["location"]["row"],
            message=item["message"],
        )
        for item in data
    ]