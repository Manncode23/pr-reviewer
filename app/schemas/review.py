"""Schemas for the review pipeline's plan, result, and session status."""

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.findings import Finding


class Assignment(BaseModel):
    """One unit of work: run `agent` on `file_path`."""

    file_path: str
    agent: str


class ReviewResult(BaseModel):
    repo: str
    pr_number: int
    title: str
    head_sha: str
    raw_findings_count: int = 0  # before validation and dedupe
    findings: list[Finding] = Field(default_factory=list)  # final, ranked
    dropped: list[str] = Field(default_factory=list)  # reasons the validator dropped items
    errors: list[str] = Field(default_factory=list)
    published: bool = False  # True once approved findings were posted to GitHub


class ReviewStatus(str, Enum):
    AWAITING_APPROVAL = "awaiting_approval"  # paused at the human gate
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"  # a run stopped midway (crash); can be continued


class ReviewSession(BaseModel):
    thread_id: str
    status: ReviewStatus
    result: ReviewResult | None = None