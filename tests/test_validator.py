from app.agents.validator import validate_findings
from app.schemas.findings import Category, Finding, Severity
from app.schemas.pr import FileDiff, PullRequestData
from app.tools.diff_parser import parse_patch

PATCH = "@@ -0,0 +1,3 @@\n+a = 1\n+b = 2\n+c = 3"


def _pr() -> PullRequestData:
    return PullRequestData(
        repo="o/r", number=1, title="t", author="a",
        base_branch="main", head_branch="x", head_sha="abc",
        files=[
            FileDiff(
                path="app.py", status="added", additions=3,
                patch=PATCH, hunks=parse_patch(PATCH),
            )
        ],
    )


def _finding(line=1, confidence=0.9, path="app.py") -> Finding:
    return Finding(
        file_path=path, line=line, severity=Severity.MEDIUM, category=Category.BUG,
        title="Some issue", explanation="Because.", suggestion="Fix it.",
        confidence=confidence, agent="bugs",
    )


def test_valid_finding_is_kept():
    kept, dropped = validate_findings(_pr(), [_finding(line=2)])
    assert len(kept) == 1 and dropped == []


def test_finding_on_line_outside_diff_is_dropped():
    kept, dropped = validate_findings(_pr(), [_finding(line=99)])
    assert kept == []
    assert "line not in diff" in dropped[0]


def test_low_confidence_finding_is_dropped():
    kept, dropped = validate_findings(_pr(), [_finding(confidence=0.3)])
    assert kept == []
    assert "low confidence" in dropped[0]


def test_finding_for_unknown_file_is_dropped():
    kept, dropped = validate_findings(_pr(), [_finding(path="other.py")])
    assert kept == []
    assert "unknown file" in dropped[0]