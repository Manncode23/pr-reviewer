"""Schemas for the review pipeline's plan and final result."""

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