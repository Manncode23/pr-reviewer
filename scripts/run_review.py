"""Run the full multi-agent review on a real PR.

Run from the project root:
    python -m scripts.run_review https://github.com/owner/repo/pull/1
    python -m scripts.run_review https://github.com/owner/repo/pull/1 --graph
"""

import argparse
from collections import Counter

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.graph.builder import build_review_graph
from app.services.review_service import review_pull_request
from app.tools.github_client import parse_pr_url


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pr_url")
    parser.add_argument("--graph", action="store_true", help="print the graph as Mermaid")
    args = parser.parse_args()

    setup_logging(get_settings().log_level)

    if args.graph:
        print(build_review_graph().get_graph().draw_mermaid())

    repo, number = parse_pr_url(args.pr_url)
    result = review_pull_request(repo, number)

    print(f"\nPR #{result.pr_number}: {result.title}")
    by_agent = Counter(f.agent for f in result.findings)
    print(f"Total findings: {len(result.findings)}  {dict(by_agent)}\n")

    for f in result.findings:
        print(f"[{f.severity.value.upper()}][{f.agent}] {f.file_path}:{f.line}  {f.title}")
        print(f"  confidence: {f.confidence:.2f}")
        print(f"  why: {f.explanation}")
        print(f"  fix: {f.suggestion}\n")

    if result.errors:
        print("ERRORS:")
        for err in result.errors:
            print(f"  - {err}")


if __name__ == "__main__":
    main()