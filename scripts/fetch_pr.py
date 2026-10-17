"""Stage 2 smoke test: fetch a PR and print its parsed diff.

Run from the project root:
    python -m scripts.fetch_pr https://github.com/owner/repo/pull/1
"""

import argparse

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.tools.diff_parser import commentable_lines, format_file_diff
from app.tools.github_client import GitHubClient, parse_pr_url


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pr_url", help="Full GitHub pull request URL")
    args = parser.parse_args()

    setup_logging(get_settings().log_level)
    repo, number = parse_pr_url(args.pr_url)
    pr = GitHubClient().get_pull_request(repo, number)

    print(f"\nPR #{pr.number}: {pr.title}")
    print(f"Author: {pr.author} | {pr.head_branch} -> {pr.base_branch}")
    print(f"Thread ID: {pr.thread_id}")
    print(f"Files changed: {len(pr.files)}\n")

    for f in pr.files:
        lines = sorted(commentable_lines(f))
        print(f"- {f.path} [{f.status}] hunks={len(f.hunks)} "
              f"commentable_lines={len(lines)} skip={f.skip_reason}")

    print("\n===== Formatted diff (what the LLM will see) =====\n")
    for f in pr.files:
        if f.hunks:
            print(format_file_diff(f))
            print()


if __name__ == "__main__":
    main()