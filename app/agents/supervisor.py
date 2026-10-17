"""Supervisor: decides which specialists review which files.

Rule-based for now (fast, free, deterministic). The graph only consumes
the list of Assignments, so this could become LLM-driven later.
"""

from pathlib import PurePosixPath

from app.schemas.pr import FileDiff, PullRequestData
from app.schemas.review import Assignment

PYTHON_SUFFIXES = {".py"}
OTHER_CODE_SUFFIXES = {
    ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".php",
    ".cs", ".c", ".cpp", ".rs", ".kt", ".swift",
}
CONFIG_SUFFIXES = {".yml", ".yaml", ".json", ".toml", ".ini", ".cfg"}


def is_test_file(path: str) -> bool:
    p = PurePosixPath(path.lower())
    name = p.name
    in_test_dir = any(part in {"test", "tests", "__tests__"} for part in p.parts[:-1])
    return (
        in_test_dir
        or name.startswith("test_")
        or name.endswith(("_test.py", "_test.go"))
        or ".test." in name
        or ".spec." in name
    )


def agents_for_file(file_diff: FileDiff) -> list[str]:
    """Return the names of the specialists that should review this file."""
    if file_diff.status == "removed" or not file_diff.hunks:
        return []

    path = file_diff.path
    name = PurePosixPath(path.lower()).name
    suffix = PurePosixPath(path.lower()).suffix

    if suffix in PYTHON_SUFFIXES:
        if is_test_file(path):
            return ["bugs", "style"]
        return ["security", "bugs", "style", "tests"]

    if suffix in OTHER_CODE_SUFFIXES:
        if is_test_file(path):
            return ["bugs"]
        return ["security", "bugs"]

    if suffix in CONFIG_SUFFIXES or name == "dockerfile" or name.startswith(".env"):
        return ["security"]

    return []  # docs, images, lockfiles, etc.


def plan_assignments(pr: PullRequestData) -> list[Assignment]:
    return [
        Assignment(file_path=f.path, agent=agent)
        for f in pr.files
        for agent in agents_for_file(f)
    ]