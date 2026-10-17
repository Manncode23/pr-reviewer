from app.schemas.pr import FileDiff
from app.tools.diff_parser import parse_patch
from app.tools.static_analysis import analyze_python_file

SOURCE_LINES = [
    "import sqlite3",
    "",
    'DB_PASSWORD = "admin123"',
    "",
    "",
    "def get_user(username):",
    '    conn = sqlite3.connect("app.db")',
    "    query = \"SELECT * FROM users WHERE name = '\" + username + \"'\"",
    "    try:",
    "        return conn.execute(query).fetchall()",
    "    except:",
    "        pass",
    "",
    "",
    "def divide(a, b):",
    "    return a / b",
]
CONTENT = "\n".join(SOURCE_LINES) + "\n"


def _file_diff(patch: str) -> FileDiff:
    return FileDiff(
        path="demo/user_service.py", status="added", additions=0, deletions=0,
        patch=patch, hunks=parse_patch(patch),
    )


def test_issues_reported_when_lines_are_added():
    patch = "@@ -0,0 +1,16 @@\n" + "\n".join("+" + line for line in SOURCE_LINES)
    result = analyze_python_file(_file_diff(patch), CONTENT)

    assert 3 in {i.line for i in result.bandit}   # hardcoded password
    assert 11 in {i.line for i in result.ruff}    # bare except


def test_issues_on_unchanged_lines_are_filtered_out():
    # Lines 1-14 are context; only the last two lines are added.
    patch = (
        "@@ -1,14 +1,16 @@\n"
        + "\n".join(" " + line for line in SOURCE_LINES[:14])
        + "\n"
        + "\n".join("+" + line for line in SOURCE_LINES[14:])
    )
    result = analyze_python_file(_file_diff(patch), CONTENT)

    assert all(i.line >= 15 for i in result.bandit + result.ruff)


def test_non_python_files_are_ignored():
    patch = "@@ -0,0 +1,1 @@\n+hello"
    file_diff = FileDiff(
        path="notes.txt", status="added", patch=patch, hunks=parse_patch(patch),
    )
    result = analyze_python_file(file_diff, "hello\n")
    assert result.bandit == [] and result.ruff == []