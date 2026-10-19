"""Runs the real specialist agents over eval cases (no GitHub; LLM or cache)."""

from dataclasses import dataclass, field

from app.agents.aggregator import apply_groups, exact_duplicate_groups, rank_findings
from app.agents.registry import SPECIALISTS
from app.agents.validator import validate_findings
from app.core.resilience import LLMQuotaExhaustedError, short_error
from app.schemas.findings import Finding
from app.schemas.pr import FileDiff, PullRequestData
from app.tools.diff_parser import parse_patch
from app.tools.static_analysis import analyze_python_file
from eval.dataset import EvalCase
from eval.llm_cache import EvalBudgetExhausted
from eval.scoring import DEFAULT_TOLERANCE, CaseScore, score_case


def build_pr(case: EvalCase) -> PullRequestData:
    """Turn a case into a PR where every line of every file is newly added.

    The title and description are deliberately neutral so they can't leak the label.
    """
    files = []
    for path, source in case.files.items():
        lines = source.splitlines()
        body = "\n".join("+" + line for line in lines)
        patch = f"@@ -0,0 +1,{len(lines)} @@\n{body}"
        files.append(
            FileDiff(
                path=path, status="added", additions=len(lines), deletions=0,
                patch=patch, hunks=parse_patch(patch),
            )
        )
    return PullRequestData(
        repo="eval/cases", number=1, title="Add " + ", ".join(case.files),
        body="", author="eval", base_branch="main", head_branch="eval",
        head_sha="0" * 40, files=files,
    )


@dataclass
class EvalReport:
    scores: list[CaseScore] = field(default_factory=list)
    findings: dict[str, list[Finding]] = field(default_factory=dict)
    pending: list[str] = field(default_factory=list)  # ran out of budget or quota
    errored: dict[str, str] = field(default_factory=dict)  # failed for another reason


def run_case(case: EvalCase, agents: tuple[str, ...]) -> list[Finding]:
    """The production pipeline minus GitHub: specialists, validator, local dedupe."""
    pr = build_pr(case)
    findings: list[Finding] = []
    for file_diff in pr.files:
        static = analyze_python_file(file_diff, case.files[file_diff.path])
        for agent in agents:
            findings.extend(SPECIALISTS[agent](pr, file_diff, static))

    kept, _dropped = validate_findings(pr, findings)
    return rank_findings(apply_groups(kept, exact_duplicate_groups(kept)))


def evaluate(
    cases: list[EvalCase],
    agents: tuple[str, ...] = ("security", "bugs"),
    tolerance: int = DEFAULT_TOLERANCE,
) -> EvalReport:
    report = EvalReport()
    for case in cases:
        try:
            findings = run_case(case, agents)
        except (EvalBudgetExhausted, LLMQuotaExhaustedError):
            report.pending.append(case.id)  # finish it on a later run
            continue
        except Exception as exc:  # noqa: BLE001 - one bad case must not stop the rest
            report.errored[case.id] = short_error(exc)
            continue
        report.findings[case.id] = findings
        report.scores.append(score_case(case, findings, tolerance))
    return report