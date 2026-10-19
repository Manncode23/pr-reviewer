"""Endpoints to start, inspect, and approve reviews."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_manager
from app.api.schemas import ApproveRequest, ReviewAccepted, StartReviewRequest, status_path
from app.schemas.review import ReviewSession
from app.services.review_manager import ReviewManager
from app.services.review_service import ReviewNotFoundError, ReviewService, ReviewStateError
from app.tools.github_client import GitHubClientError

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _thread_id(owner: str, repo: str, pr_number: int, head_sha: str) -> str:
    return ReviewService.thread_id_for(f"{owner}/{repo}", pr_number, head_sha)


@router.post("", status_code=202, response_model=ReviewAccepted)
def start_review(body: StartReviewRequest, manager: ReviewManager = Depends(get_manager)):
    """Queue a review (idempotent per commit). Poll status_url for progress."""
    try:
        result = manager.submit(body.repo, body.pr_number)
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ReviewAccepted(
        thread_id=result.thread_id,
        status=result.status,
        started=result.started,
        status_url=status_path(result.thread_id),
    )


@router.get("/{owner}/{repo}/{pr_number}/{head_sha}", response_model=ReviewSession)
def get_review(
    owner: str, repo: str, pr_number: int, head_sha: str,
    manager: ReviewManager = Depends(get_manager),
):
    session = manager.status(_thread_id(owner, repo, pr_number, head_sha))
    if session is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return session


@router.post("/{owner}/{repo}/{pr_number}/{head_sha}/approve", response_model=ReviewSession)
def approve_review(
    owner: str, repo: str, pr_number: int, head_sha: str, body: ApproveRequest,
    manager: ReviewManager = Depends(get_manager),
):
    """Post the chosen findings to GitHub and finish the review."""
    thread_id = _thread_id(owner, repo, pr_number, head_sha)
    try:
        return manager.approve(thread_id, body.approved, body.approve_all)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Review not found") from exc
    except ReviewStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc