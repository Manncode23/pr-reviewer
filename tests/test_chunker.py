from app.schemas.pr import FileDiff
from app.tools.diff_chunker import split_file_diff
from app.tools.diff_parser import format_file_diff, parse_patch


def _file(num_lines: int, hunks: int = 1, line_len: int = 60) -> FileDiff:
    parts, start = [], 1
    for _ in range(hunks):
        body = "\n".join("+" + "x" * line_len for _ in range(num_lines))
        parts.append(f"@@ -0,0 +{start},{num_lines} @@\n{body}")
        start += num_lines + 5
    patch = "\n".join(parts)
    return FileDiff(
        path="big.py", status="added", additions=num_lines * hunks,
        patch=patch, hunks=parse_patch(patch),
    )


def _all_lines(files: list[FileDiff]) -> list[int]:
    return sorted(
        line.new_line for f in files for h in f.hunks for line in h.lines
    )


def test_small_file_is_not_split():
    file_diff = _file(num_lines=5)
    chunks = split_file_diff(file_diff)
    assert len(chunks) == 1 and chunks[0] is file_diff


def test_many_hunks_are_grouped_into_chunks_without_losing_lines():
    file_diff = _file(num_lines=10, hunks=6)

    chunks = split_file_diff(file_diff, max_chars=1600)

    assert len(chunks) == 3
    assert _all_lines(chunks) == _all_lines([file_diff])  # nothing lost or duplicated


def test_single_huge_hunk_is_split_by_lines_and_stays_small():
    file_diff = _file(num_lines=60)

    chunks = split_file_diff(file_diff, max_chars=1500)

    assert len(chunks) == 3
    assert _all_lines(chunks) == _all_lines([file_diff])
    assert all(len(format_file_diff(c)) < 1500 + 300 for c in chunks)