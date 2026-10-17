from app.schemas.pr import FileDiff, LineKind
from app.tools.diff_parser import commentable_lines, format_file_diff, parse_patch

SAMPLE_PATCH = "\n".join(
    [
        "@@ -1,4 +1,5 @@",
        " import os",
        "-import sys",
        "+import json",
        "+import sys",
        " ",
        " def main():",
    ]
)


def test_parse_single_hunk_line_numbers():
    hunks = parse_patch(SAMPLE_PATCH)
    assert len(hunks) == 1

    hunk = hunks[0]
    assert (hunk.old_start, hunk.old_count) == (1, 4)
    assert (hunk.new_start, hunk.new_count) == (1, 5)

    added = [l.new_line for l in hunk.lines if l.kind is LineKind.ADDED]
    removed = [l.old_line for l in hunk.lines if l.kind is LineKind.REMOVED]
    assert added == [2, 3]
    assert removed == [2]


def test_no_newline_marker_is_ignored():
    patch = "\n".join(["@@ -1 +1 @@", "-old", "+new", "\\ No newline at end of file"])
    hunks = parse_patch(patch)
    assert len(hunks[0].lines) == 2


def test_commentable_lines_and_formatting():
    file_diff = FileDiff(
        path="app.py", status="modified", additions=2, deletions=1,
        patch=SAMPLE_PATCH, hunks=parse_patch(SAMPLE_PATCH),
    )
    assert commentable_lines(file_diff) == {1, 2, 3, 4, 5}

    text = format_file_diff(file_diff)
    assert "+ import json" in text
    assert "- import sys" in text