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
    findings: list[Finding] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)