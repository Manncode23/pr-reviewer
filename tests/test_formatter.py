from app.schemas.findings import Severity
from app.schemas.pr import PullRequestData
from app.tools.review_formatter import (
    defang_mentions,
    format_comment,
    format_review_summary,
)
from tests.fakes import make_finding


def _pr() -> PullRequestData:
    return PullRequestData(
        repo="o/r", number=1, title="t", author="a",
        base_branch="main", head_branch="x", head_sha="abc",
    )


def test_comment_contains_key_parts():
    finding = make_finding("bugs", severity=Severity.HIGH, title="Divide by zero",
                           explanation="b can be zero")
    finding = finding.model_copy(update={"also_flagged_by": ["style"]})

    text = format_comment(finding)

    assert "[HIGH] Divide by zero" in text
    assert "b can be zero" in text
    assert "Suggested fix" in text
    assert "bugs reviewer" in text and "style" in text


def test_mentions_are_defanged():
    text = format_comment(make_finding("bugs", explanation="ping @octocat now"))
    assert "@octocat" not in text
    assert defang_mentions("@octocat") != "@octocat"


def test_summary_counts_by_severity():
    approved = [
        make_finding("a", severity=Severity.HIGH),
        make_finding("b", severity=Severity.HIGH),
        make_finding("c", severity=Severity.LOW),
    ]
    text = format_review_summary(_pr(), approved, total=5)

    assert "found 5 issue(s)" in text
    assert "3 were approved" in text
    assert "2 high, 1 low" in text