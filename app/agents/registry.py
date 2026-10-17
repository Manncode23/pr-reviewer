"""Maps agent names to callables with one uniform signature.

The graph only knows agent names, so adding a new specialist means writing
the agent and registering it here. Nothing else changes.
"""

from collections.abc import Callable

from app.agents.bugs import review_bugs
from app.agents.security import review_security
from app.agents.style import review_style
from app.agents.testing import review_tests
from app.schemas.findings import Finding
from app.schemas.pr import FileDiff, PullRequestData
from app.schemas.static import StaticAnalysisResult

SpecialistFn = Callable[
    [PullRequestData, FileDiff, StaticAnalysisResult | None], list[Finding]
]


def _security(pr, file_diff, static):
    return review_security(pr, file_diff, static.bandit if static else None)


def _bugs(pr, file_diff, static):
    # Only pyflakes (F) and bugbear (B) rules are bug-related; E/W are style.
    hints = [i for i in (static.ruff if static else []) if i.rule_id.startswith(("F", "B"))]
    return review_bugs(pr, file_diff, hints)


def _style(pr, file_diff, static):
    return review_style(pr, file_diff, static.ruff if static else None)


def _tests(pr, file_diff, static):
    return review_tests(pr, file_diff)


SPECIALISTS: dict[str, SpecialistFn] = {
    "security": _security,
    "bugs": _bugs,
    "style": _style,
    "tests": _tests,
}