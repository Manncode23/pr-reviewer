"""Thin wrapper around PyGithub that returns our own schemas."""

import re

from github import Auth, Github
from github.GithubException import GithubException

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.pr import FileDiff, PullRequestData
from app.tools.diff_parser import parse_patch

logger = get_logger(__name__)

_PR_URL_RE = re.compile(r"github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)")


class GitHubClientError(Exception):
    """Raised when a GitHub API call fails."""


def parse_pr_url(url: str) -> tuple[str, int]:
    """'https://github.com/owner/repo/pull/12' -> ('owner/repo', 12)"""
    match = _PR_URL_RE.search(url)
    if not match:
        raise ValueError(f"Not a valid GitHub pull request URL: {url}")
    return match.group(1), int(match.group(2))


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        token = token or get_settings().github_token.get_secret_value()
        self._gh = Github(auth=Auth.Token(token))

    def get_head_sha(self, repo_full_name: str, number: int) -> str:
        """Cheap call used to build the idempotent thread ID."""
        try:
            return self._gh.get_repo(repo_full_name).get_pull(number).head.sha
        except GithubException as exc:
            raise GitHubClientError(
                f"GitHub API error ({exc.status}) for {repo_full_name}#{number}: {exc.data}"
            ) from exc

    def get_pull_request(self, repo_full_name: str, number: int) -> PullRequestData:
        """Fetch PR metadata plus every changed file with parsed hunks."""
        try:
            repo = self._gh.get_repo(repo_full_name)
            pr = repo.get_pull(number)

            files: list[FileDiff] = []
            for f in pr.get_files():
                file_diff = FileDiff(
                    path=f.filename,
                    status=f.status,
                    additions=f.additions,
                    deletions=f.deletions,
                    patch=f.patch,
                )
                if f.patch:
                    file_diff.hunks = parse_patch(f.patch)
                else:
                    file_diff.skip_reason = "no patch (binary, renamed-only, or too large)"
                files.append(file_diff)

            logger.info("Fetched PR %s#%s with %d files", repo_full_name, number, len(files))
            return PullRequestData(
                repo=repo_full_name,
                number=number,
                title=pr.title,
                body=pr.body or "",
                author=pr.user.login,
                base_branch=pr.base.ref,
                head_branch=pr.head.ref,
                head_sha=pr.head.sha,
                files=files,
            )
        except GithubException as exc:
            raise GitHubClientError(
                f"GitHub API error ({exc.status}) for {repo_full_name}#{number}: {exc.data}"
            ) from exc

    def get_file_content(self, repo_full_name: str, path: str, ref: str) -> str | None:
        """Return a file's full text at a given commit, or None if unavailable."""
        try:
            repo = self._gh.get_repo(repo_full_name)
            contents = repo.get_contents(path, ref=ref)
        except GithubException as exc:
            logger.warning("Could not fetch %s@%s (status %s)", path, ref[:7], exc.status)
            return None

        if isinstance(contents, list):  # path is a directory
            return None
        try:
            return contents.decoded_content.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def post_review(
        self,
        repo_full_name: str,
        number: int,
        head_sha: str,
        body: str,
        comments: list[dict],
    ) -> None:
        """Post one review with inline comments (event=COMMENT: no approve/reject)."""
        try:
            repo = self._gh.get_repo(repo_full_name)
            pr = repo.get_pull(number)
            commit = repo.get_commit(head_sha)
            pr.create_review(commit=commit, body=body, event="COMMENT", comments=comments)
            logger.info("Posted review with %d comment(s) on %s#%s",
                        len(comments), repo_full_name, number)
        except GithubException as exc:
            raise GitHubClientError(
                f"Could not post review to {repo_full_name}#{number} "
                f"({exc.status}): {exc.data}"
            ) from exc