"""Pydantic models describing a pull request and its diff."""

from enum import Enum

from pydantic import BaseModel, Field


class LineKind(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    CONTEXT = "context"


class DiffLine(BaseModel):
    kind: LineKind
    content: str
    old_line: int | None = None  # None for added lines
    new_line: int | None = None  # None for removed lines


class Hunk(BaseModel):
    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[DiffLine] = Field(default_factory=list)


class FileDiff(BaseModel):
    path: str
    status: str  # added | modified | removed | renamed ...
    additions: int = 0
    deletions: int = 0
    patch: str | None = None  # raw unified-diff text (None for binary/huge files)
    hunks: list[Hunk] = Field(default_factory=list)
    skip_reason: str | None = None  # set when the file can't be reviewed


class PullRequestData(BaseModel):
    repo: str  # "owner/name"
    number: int
    title: str
    body: str = ""
    author: str
    base_branch: str
    head_branch: str
    head_sha: str
    files: list[FileDiff] = Field(default_factory=list)

    @property
    def thread_id(self) -> str:
        """Stable ID used later for idempotency and checkpointing."""
        return f"{self.repo}#{self.number}@{self.head_sha}"