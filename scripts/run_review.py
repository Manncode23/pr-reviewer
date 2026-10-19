"""Run a review, pick which findings to post, and publish them.

Run from the project root:
    python -m scripts.run_review https://github.com/owner/repo/pull/1
    python -m scripts.run_review https://github.com/owner/repo/pull/1 --force

Press Ctrl+C at the prompt and re-run the same command: the saved review
is reused instantly (no new LLM calls), because it's checkpointed in Postgres.
--force throws the saved review away and runs it again (not allowed once
its findings have been published).
"""

import argparse

from app.core.checkpointer import postgres_checkpointer
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.graph.builder import build_review_graph
from app.schemas.review import ReviewSession, ReviewStatus
from app.services.review_service import ReviewService, ReviewStateError
from app.tools.github_client import GitHubClient, parse_pr_url


def parse_selection(text: str, count: int) -> list[int]:
    """'all' | 'none' | '1,3,5' (1-based) -> list of 0-based indices."""
    text = text.strip().lower()
    if text in {"", "none", "n"}:
        return []
    if text in {"all", "a"}:
        return list(range(count))
    picked: list[int] = []
    for token in text.replace(" ", "").split(","):
        if token.isdigit() and 1 <= int(token) <= count:
            picked.append(int(token) - 1)
        else:
            print(f"  (ignoring '{token}')")
    return picked


def print_session(session: ReviewSession) -> None:
    result = session.result
    print(f"\nPR #{result.pr_number}: {result.title}")
    print(f"Thread: {session.thread_id} | status: {session.status.value}")
    print(
        f"Pipeline: {result.raw_findings_count} raw -> {len(result.dropped)} dropped "
        f"-> {len(result.findings)} final"
    )
    if result.degraded:
        print("WARNING: some reviewers failed, so this review may be incomplete.")
    print()
    for i, f in enumerate(result.findings, start=1):
        also = f" (also: {', '.join(f.also_flagged_by)})" if f.also_flagged_by else ""
        print(f"{i:>2}. [{f.severity.value.upper()}][{f.agent}] {f.file_path}:{f.line}  {f.title}{also}")
        print(f"      {f.explanation}")
    if result.dropped:
        print("\nDropped by validator:")
        for reason in result.dropped:
            print(f"  - {reason}")
    if result.errors:
        print("\nErrors:")
        for err in result.errors:
            print(f"  - {err}")
        if not result.published:
            print("(Fix the cause, then re-run with --force to review this commit again.)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pr_url")
    parser.add_argument(
        "--force", action="store_true",
        help="discard the saved review for this commit and run it again",
    )
    args = parser.parse_args()

    setup_logging(get_settings().log_level)
    repo, number = parse_pr_url(args.pr_url)

    with postgres_checkpointer() as saver:
        client = GitHubClient()
        service = ReviewService(build_review_graph(client, saver), client)

        if args.force:
            thread_id, _ = service.resolve_thread(repo, number)
            try:
                service.reset(thread_id)
            except ReviewStateError as exc:
                raise SystemExit(f"Cannot re-run: {exc}") from exc

        session = service.start(repo, number)
        print_session(session)

        if session.status is ReviewStatus.AWAITING_APPROVAL:
            count = len(session.result.findings)
            answer = input("\nPost which findings to GitHub? (all / none / e.g. 1,3,5): ")
            indices = parse_selection(answer, count)
            print(f"\nPosting {len(indices)} finding(s)...")
            session = service.approve(session.thread_id, indices)
            print(f"Published: {session.result.published}")
            for err in session.result.errors:
                print(f"  error: {err}")
        elif session.status is ReviewStatus.COMPLETED:
            print(f"\nThis commit was already reviewed. Published: {session.result.published}")


if __name__ == "__main__":
    main()