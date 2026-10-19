"""Review lifecycle: start (idempotent), inspect, approve."""

from langgraph.types import Command

from app.core.logging import get_logger
from app.schemas.review import ReviewResult, ReviewSession, ReviewStatus

logger = get_logger(__name__)


class ReviewNotFoundError(Exception):
    """No review exists for this thread ID."""


class ReviewStateError(Exception):
    """The review is not in a state that allows this action."""


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _to_result(values: dict) -> ReviewResult:
    pr = values["pr"]
    return ReviewResult(
        repo=pr.repo,
        pr_number=pr.number,
        title=pr.title,
        head_sha=pr.head_sha,
        raw_findings_count=len(values.get("findings", [])),
        findings=values.get("final_findings", []),
        dropped=values.get("dropped", []),
        errors=values.get("errors", []),
        published=values.get("published", False),
    )


class ReviewService:
    def __init__(self, graph, client) -> None:
        self._graph = graph
        self._client = client

    @staticmethod
    def thread_id_for(repo: str, pr_number: int, head_sha: str) -> str:
        return f"{repo}#{pr_number}@{head_sha}"

    def resolve_thread(self, repo: str, pr_number: int) -> tuple[str, str]:
        """Look up the PR's current commit and return (thread_id, head_sha)."""
        head_sha = self._client.get_head_sha(repo, pr_number)
        return self.thread_id_for(repo, pr_number, head_sha), head_sha

    def get(self, thread_id: str) -> ReviewSession | None:
        snapshot = self._graph.get_state(_config(thread_id))
        values = snapshot.values or {}
        if not values:
            return None

        if snapshot.next == ("approval",):
            status = ReviewStatus.AWAITING_APPROVAL
        elif snapshot.next:
            status = ReviewStatus.INCOMPLETE
        else:
            status = ReviewStatus.COMPLETED

        result = _to_result(values) if "pr" in values else None
        return ReviewSession(thread_id=thread_id, status=status, result=result)

    def start(
        self, repo: str, pr_number: int, head_sha: str | None = None
    ) -> ReviewSession:
        """Run a review, or reuse/continue the one that exists for this commit."""
        if head_sha is None:
            head_sha = self._client.get_head_sha(repo, pr_number)
        thread_id = self.thread_id_for(repo, pr_number, head_sha)
        config = _config(thread_id)

        existing = self.get(thread_id)
        if existing and existing.status is ReviewStatus.INCOMPLETE:
            logger.info("Continuing interrupted review %s", thread_id)
            self._graph.invoke(None, config=config)  # resume from last checkpoint
            return self.get(thread_id)
        if existing:
            logger.info("Reusing existing review %s (%s)", thread_id, existing.status.value)
            return existing

        self._graph.invoke(
            {"repo": repo, "pr_number": pr_number, "findings": [], "errors": []},
            config=config,
        )
        return self.get(thread_id)

    def approve(self, thread_id: str, approved_indices: list[int]) -> ReviewSession:
        """Resume a paused review. Indices refer to the final findings list."""
        session = self.get(thread_id)
        if session is None:
            raise ReviewNotFoundError(thread_id)
        if session.status is not ReviewStatus.AWAITING_APPROVAL:
            raise ReviewStateError(
                f"Review is {session.status.value}, not awaiting approval"
            )

        self._graph.invoke(
            Command(resume={"approved": approved_indices}), config=_config(thread_id)
        )
        return self.get(thread_id)