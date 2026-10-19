"""Request/response models for the HTTP API."""

from pydantic import BaseModel, Field, model_validator

from app.schemas.review import ReviewStatus
from app.tools.github_client import parse_pr_url


class StartReviewRequest(BaseModel):
    pr_url: str | None = None
    repo: str | None = None
    pr_number: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _resolve(self):
        if self.pr_url:
            self.repo, self.pr_number = parse_pr_url(self.pr_url)  # ValueError -> 422
        elif not (self.repo and self.pr_number):
            raise ValueError("Provide pr_url, or both repo and pr_number")
        return self


class ApproveRequest(BaseModel):
    approved: list[int] = Field(
        default_factory=list,
        description="0-based positions in the review's findings list to post",
    )
    approve_all: bool = False


class ReviewAccepted(BaseModel):
    thread_id: str
    status: ReviewStatus
    started: bool
    status_url: str


def status_path(thread_id: str) -> str:
    """'o/r#1@abc' -> '/reviews/o/r/1/abc' (thread IDs aren't URL-safe)."""
    repo_full, rest = thread_id.split("#", 1)
    number, sha = rest.split("@", 1)
    return f"/reviews/{repo_full}/{number}/{sha}"