"""Pure scoring logic: compare findings with labeled expectations.

A finding matches an expected issue when it is in the same file and within
`tolerance` lines of the labeled line. Matching on location (not wording)
keeps the score fair to any phrasing the model chooses.
"""

from dataclasses import dataclass, field

from app.schemas.findings import Finding, Severity
from eval.dataset import EvalCase, ExpectedIssue, resolve_line

DEFAULT_TOLERANCE = 2
ALARMING = {Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM}


@dataclass
class CaseScore:
    case_id: str
    clean: bool
    expected: int
    findings: int
    matched_expected: int
    matched_findings: int
    missed: list[str] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)
    false_alarms: int = 0  # medium-or-worse findings on a clean case


def score_case(
    case: EvalCase, findings: list[Finding], tolerance: int = DEFAULT_TOLERANCE
) -> CaseScore:
    targets = [(issue, resolve_line(case, issue)) for issue in case.expected]

    def hits(finding: Finding, issue: ExpectedIssue, line: int) -> bool:
        return finding.file_path == issue.file and abs(finding.line - line) <= tolerance

    missed = [
        issue.label
        for issue, line in targets
        if not any(hits(f, issue, line) for f in findings)
    ]
    unmatched = [
        f for f in findings
        if not any(hits(f, issue, line) for issue, line in targets)
    ]

    return CaseScore(
        case_id=case.id,
        clean=case.is_clean,
        expected=len(targets),
        findings=len(findings),
        matched_expected=len(targets) - len(missed),
        matched_findings=len(findings) - len(unmatched),
        missed=missed,
        false_positives=[f"{f.file_path}:{f.line} {f.title}" for f in unmatched],
        false_alarms=sum(1 for f in unmatched if case.is_clean and f.severity in ALARMING),
    )


def summarize(scores: list[CaseScore]) -> dict:
    expected = sum(s.expected for s in scores)
    matched_expected = sum(s.matched_expected for s in scores)
    findings = sum(s.findings for s in scores)
    matched_findings = sum(s.matched_findings for s in scores)

    recall = matched_expected / expected if expected else None
    precision = matched_findings / findings if findings else None
    f1 = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)

    return {
        "cases": len(scores),
        "expected_issues": expected,
        "matched_issues": matched_expected,
        "findings": findings,
        "matched_findings": matched_findings,
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "clean_case_false_alarms": sum(s.false_alarms for s in scores),
    }