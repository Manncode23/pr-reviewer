"""Shared test doubles (no network, no LLM)."""

from app.schemas.findings import Category, Finding, Severity
from app.schemas.pr import FileDiff, PullRequestData
from app.tools.diff_parser import parse_patch

PATCH = "@@ -0,0 +1,2 @@\n+def f():\n+    return 1"
AGENTS = {"security", "bugs", "style", "tests"}
THREAD_ID = "o/r#1@abc123"


class FakeClient:
    def __init__(self) -> None:
        self.posted: list[dict] = []

    def get_head_sha(self, repo, number):
        return "abc123"

    def get_pull_request(self, repo, number):
        return PullRequestData(
            repo=repo, number=number, title="t", author="a",
            base_branch="main", head_branch="x", head_sha="abc123",
            files=[
                FileDiff(
                    path="app/service.py", status="added", additions=2,
                    patch=PATCH, hunks=parse_patch(PATCH),
                )
            ],
        )

    def get_file_content(self, repo, path, ref):
        return None  # skips static analysis

    def post_review(self, repo, number, head_sha, body, comments):
        self.posted.append(
            {"repo": repo, "number": number, "sha": head_sha, "body": body, "comments": comments}
        )


def make_finding(
    name, line=1, severity=Severity.LOW, title=None, explanation="x", confidence=0.9
) -> Finding:
    return Finding(
        file_path="app/service.py", line=line, severity=severity,
        category=Category.BUG, title=title or name, explanation=explanation,
        suggestion="y", confidence=confidence, agent=name,
    )


def fake_specialist(name: str):
    def run(pr, file_diff, static):
        return [make_finding(name)]
    return run


def failing_specialist(pr, file_diff, static):
    raise RuntimeError("boom")


def thread_config(thread_id: str = THREAD_ID) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def initial_state() -> dict:
    return {"repo": "o/r", "pr_number": 1, "findings": [], "errors": []}