"""Entry point for running a review. The API layer (Stage 8) will call this."""

from app.core.logging import get_logger
from app.graph.builder import build_review_graph
from app.schemas.findings import SEVERITY_RANK
from app.schemas.review import ReviewResult
from app.tools.github_client import GitHubClient

logger = get_logger(__name__)


def review_pull_request(
    repo: str, pr_number: int, client: GitHubClient | None = None
) -> ReviewResult:
    graph = build_review_graph(client)
    state = graph.invoke(
        {"repo": repo, "pr_number": pr_number, "findings": [], "errors": []}
    )

    pr = state["pr"]
    findings = sorted(
        state.get("findings", []),
        key=lambda f: (f.file_path, SEVERITY_RANK[f.severity], f.line),
    )
    return ReviewResult(
        repo=pr.repo,
        pr_number=pr.number,
        title=pr.title,
        head_sha=pr.head_sha,
        findings=findings,
        errors=state.get("errors", []),
    )