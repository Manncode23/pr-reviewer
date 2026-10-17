"""Validator: drops findings that are unanchored, low-confidence, or malformed.

Pure code, no LLM. Findings pointing at lines that aren't in the diff are
the classic symptom of a hallucinating model, and GitHub would reject
comments on those lines anyway.
"""

from app.core.logging import get_logger
from app.schemas.findings import Finding
from app.schemas.pr import PullRequestData
from app.tools.diff_parser import commentable_lines

logger = get_logger(__name__)

MIN_CONFIDENCE = 0.6


def validate_findings(
    pr: PullRequestData,
    findings: list[Finding],
    min_confidence: float = MIN_CONFIDENCE,
) -> tuple[list[Finding], list[str]]:
    """Return (kept findings, human-readable reasons for each dropped one)."""
    valid_lines = {f.path: commentable_lines(f) for f in pr.files}

    kept: list[Finding] = []
    dropped: list[str] = []

    for finding in findings:
        label = f"{finding.agent}:{finding.file_path}:{finding.line} '{finding.title}'"

        if finding.file_path not in valid_lines:
            dropped.append(f"{label} - unknown file")
        elif finding.line not in valid_lines[finding.file_path]:
            dropped.append(f"{label} - line not in diff")
        elif finding.confidence < min_confidence:
            dropped.append(f"{label} - low confidence ({finding.confidence:.2f})")
        elif not finding.title.strip() or not finding.explanation.strip():
            dropped.append(f"{label} - empty text")
        else:
            kept.append(finding)

    logger.info("Validator kept %d, dropped %d", len(kept), len(dropped))
    return kept, dropped