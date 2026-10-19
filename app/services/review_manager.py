"""Runs reviews in the background and tracks which ones are in flight.

A small worker pool (1 by default) acts as the job queue: extra PRs wait
their turn instead of hammering the LLM's rate limits.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from app.core.logging import get_logger
from app.core.resilience import short_error
from app.schemas.review import ReviewSession, ReviewStatus
from app.services.review_service import (
    ReviewNotFoundError,
    ReviewService,
    ReviewStateError,
)

logger = get_logger(__name__)


class SubmitResult(BaseModel):
    thread_id: str
    status: ReviewStatus
    started: bool  # False when an existing or in-flight review was reused


class ReviewManager:
    def __init__(self, service: ReviewService, max_workers: int = 1) -> None:
        self._service = service
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="review"
        )
        self._lock = threading.Lock()
        self._running: set[str] = set()
        self._failures: dict[str, str] = {}

    def submit(self, repo: str, pr_number: int, force: bool = False) -> SubmitResult:
        """Queue a review unless this commit already has one (idempotent).

        force=True discards the saved review first (refused if it was published).
        """
        thread_id, head_sha = self._service.resolve_thread(repo, pr_number)

        with self._lock:
            if thread_id in self._running:
                return SubmitResult(
                    thread_id=thread_id, status=ReviewStatus.RUNNING, started=False
                )
            existing = self._service.get(thread_id)
            if force and existing is not None:
                self._service.reset(thread_id)  # raises ReviewStateError if published
                existing = None
            if existing and existing.status is not ReviewStatus.INCOMPLETE:
                return SubmitResult(
                    thread_id=thread_id, status=existing.status, started=False
                )
            self._running.add(thread_id)
            self._failures.pop(thread_id, None)

        self._executor.submit(self._run, repo, pr_number, head_sha, thread_id)
        logger.info("Queued review %s", thread_id)
        return SubmitResult(thread_id=thread_id, status=ReviewStatus.RUNNING, started=True)

    def _run(self, repo: str, pr_number: int, head_sha: str, thread_id: str) -> None:
        try:
            self._service.start(repo, pr_number, head_sha)
        except Exception as exc:  # noqa: BLE001 - background job, must not die silently
            logger.error("Review %s failed: %s", thread_id, short_error(exc))
            with self._lock:
                self._failures[thread_id] = short_error(exc)
        finally:
            with self._lock:
                self._running.discard(thread_id)

    def status(self, thread_id: str) -> ReviewSession | None:
        with self._lock:
            running = thread_id in self._running
            error = self._failures.get(thread_id)

        if running:
            return ReviewSession(thread_id=thread_id, status=ReviewStatus.RUNNING)

        session = self._service.get(thread_id)
        if session is None:
            if error:
                return ReviewSession(
                    thread_id=thread_id, status=ReviewStatus.INCOMPLETE, error=error
                )
            return None
        if error and session.status is ReviewStatus.INCOMPLETE:
            session = session.model_copy(update={"error": error})
        return session

    def approve(
        self, thread_id: str, approved: list[int], approve_all: bool = False
    ) -> ReviewSession:
        with self._lock:
            if thread_id in self._running:
                raise ReviewStateError("Review is still running")

        if approve_all:
            session = self._service.get(thread_id)
            if session is None:
                raise ReviewNotFoundError(thread_id)
            approved = list(range(len(session.result.findings))) if session.result else []

        return self._service.approve(thread_id, approved)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)