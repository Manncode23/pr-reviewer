"""Schemas for review findings.

RawFinding  -> what the LLM fills in (kept simple for structured output)
Finding     -> what the rest of our system uses (enriched and validated)
"""

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


class Category(str, Enum):
    SECURITY = "security"
    BUG = "bug"
    STYLE = "style"
    TESTS = "tests"


class RawFinding(BaseModel):
    """One issue as reported by the LLM."""

    line: int = Field(
        description="Line number in the NEW file, taken from the L<number> prefix in the diff"
    )
    severity: Severity = Field(
        description="critical, high, medium, low, or info"
    )
    title: str = Field(description="Short title, at most 10 words")
    explanation: str = Field(
        description="What the problem is and why it matters, in 1-3 sentences"
    )
    suggestion: str = Field(description="A concrete fix, ideally with a short code snippet")
    confidence: float = Field(
        description="Confidence the issue is real, from 0.0 to 1.0"
    )


class ReviewOutput(BaseModel):
    """The full structured response expected from a specialist agent."""

    findings: list[RawFinding] = Field(
        description="All issues found. Use an empty list if there are none."
    )


class Finding(BaseModel):
    """A finding enriched with context, used by the rest of the pipeline."""

    file_path: str
    line: int = Field(ge=1)
    severity: Severity
    category: Category
    title: str
    explanation: str
    suggestion: str
    confidence: float = Field(ge=0.0, le=1.0)
    agent: str
    # Other agents that reported the same problem (filled in by the aggregator)
    also_flagged_by: list[str] = Field(default_factory=list)