"""Run static analysis + the security agent on a real PR.

Run from the project root:
    python -m scripts.run_security_agent https://github.com/owner/repo/pull/1
"""

import argparse

from app.agents.security import review_security
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.schemas.findings import SEVERITY_RANK
from app.schemas.static import StaticAnalysisResult
from app.tools.diff_parser import commentable_lines
from app.tools.github_client import GitHubClient, parse_pr_url
from app.tools.static_analysis import analyze_python_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pr_url")
    args = parser.parse_args()

    setup_logging(get_settings().log_level)
    repo, number = parse_pr_url(args.pr_url)
    client = GitHubClient()
    pr = client.get_pull_request(repo, number)

    all_findings = []
    for file_diff in pr.files:
        result = StaticAnalysisResult()
        if file_diff.status != "removed":
            content = client.get_file_content(pr.repo, file_diff.path, pr.head_sha)
            if content:
                result = analyze_python_file(file_diff, content)

        print(f"\n--- Static analysis for {file_diff.path} ---")
        for issue in result.bandit + result.ruff:
            print(f"  [{issue.tool} {issue.rule_id}] line {issue.line}: {issue.message}")
        if not (result.bandit or result.ruff):
            print("  (no issues on added lines)")

        valid_lines = commentable_lines(file_diff)
        for f in review_security(pr, file_diff, result.bandit):
            all_findings.append((f, f.line in valid_lines))

    all_findings.sort(key=lambda item: (SEVERITY_RANK[item[0].severity], item[0].line))

    print(f"\n===== {len(all_findings)} security finding(s) =====\n")
    for f, line_ok in all_findings:
        print(f"[{f.severity.value.upper()}] {f.file_path}:{f.line}  {f.title}")
        print(f"  confidence: {f.confidence:.2f} | line in diff: {line_ok}")
        print(f"  why: {f.explanation}")
        print(f"  fix: {f.suggestion}\n")


if __name__ == "__main__":
    main()