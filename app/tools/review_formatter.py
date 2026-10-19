"""Turns findings into GitHub comment text."""

import re
from collections import Counter

from app.schemas.findings import SEVERITY_RANK, Finding, Severity
from app.schemas.pr import PullRequestData

_MENTION_RE = re.compile(r"(?<!\w)@(?=[A-Za-z0-9_-])")


def defang_mentions(text: str) -> str:
    """Insert an invisible character after '@' so GitHub won't ping anyone.

    Finding text comes from an LLM that read untrusted code, so we never
    let it trigger notifications.
    """
    return _MENTION_RE.sub("@\u200b", text)


def format_comment(finding: Finding) -> str:
    also = (
        f" (also flagged by {', '.join(finding.also_flagged_by)})"
        if finding.also_flagged_by
        else ""
    )
    body = (
        f"**[{finding.severity.value.upper()}] {finding.title}**\n\n"
        f"{finding.explanation}\n\n"
        f"**Suggested fix:**\n{finding.suggestion}\n\n"
        f"<sub>Reported by the {finding.agent} reviewer{also}</sub>"
    )
    return defang_mentions(body)


def format_review_summary(
    pr: PullRequestData, approved: list[Finding], total: int
) -> str:
    counts = Counter(f.severity for f in approved)
    ordered = sorted(counts, key=lambda s: SEVERITY_RANK[s])
    breakdown = ", ".join(f"{counts[s]} {s.value}" for s in ordered) or "none"
    return (
        "### Automated review\n\n"
        f"A multi-agent reviewer found {total} issue(s) in this pull request. "
        f"{len(approved)} were approved by a human and are posted as inline comments.\n\n"
        f"Severity breakdown of posted comments: {breakdown}."
    )