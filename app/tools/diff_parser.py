"""Parse GitHub unified-diff patches into structured hunks.

GitHub's API returns a `patch` string per file. We turn it into Hunk and
DiffLine objects so we always know the real line numbers on the new
(right-hand) side of the diff.
"""

import re

from app.schemas.pr import DiffLine, FileDiff, Hunk, LineKind

# Matches e.g. "@@ -10,7 +10,9 @@ def foo():"  (counts are optional)
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_patch(patch: str) -> list[Hunk]:
    """Convert a unified-diff patch string into a list of Hunks."""
    hunks: list[Hunk] = []
    current: Hunk | None = None
    old_ln = new_ln = 0

    for raw in patch.splitlines():
        match = _HUNK_RE.match(raw)
        if match:
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            current = Hunk(
                header=raw,
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
            )
            hunks.append(current)
            old_ln, new_ln = old_start, new_start
            continue

        if current is None:
            continue  # text before the first hunk header

        if raw.startswith("\\"):
            continue  # "\ No newline at end of file"

        if raw.startswith("+"):
            current.lines.append(
                DiffLine(kind=LineKind.ADDED, content=raw[1:], new_line=new_ln)
            )
            new_ln += 1
        elif raw.startswith("-"):
            current.lines.append(
                DiffLine(kind=LineKind.REMOVED, content=raw[1:], old_line=old_ln)
            )
            old_ln += 1
        else:
            content = raw[1:] if raw.startswith(" ") else raw
            current.lines.append(
                DiffLine(
                    kind=LineKind.CONTEXT,
                    content=content,
                    old_line=old_ln,
                    new_line=new_ln,
                )
            )
            old_ln += 1
            new_ln += 1

    return hunks


def commentable_lines(file_diff: FileDiff) -> set[int]:
    """New-file line numbers that appear in the diff (added or context).

    A review comment can only be attached to these lines, so the
    validator uses this set to reject findings pointing elsewhere.
    """
    lines: set[int] = set()
    for hunk in file_diff.hunks:
        for line in hunk.lines:
            if line.new_line is not None:
                lines.add(line.new_line)
    return lines


def format_file_diff(file_diff: FileDiff) -> str:
    """Render a file's diff as text with explicit new-file line numbers.

    This is what the LLM agents will read, so they can cite exact lines.
    """
    out = [f"FILE: {file_diff.path} ({file_diff.status}, "
           f"+{file_diff.additions}/-{file_diff.deletions})"]
    for hunk in file_diff.hunks:
        out.append(hunk.header)
        for line in hunk.lines:
            if line.kind is LineKind.ADDED:
                out.append(f"L{line.new_line:>4} + {line.content}")
            elif line.kind is LineKind.CONTEXT:
                out.append(f"L{line.new_line:>4}   {line.content}")
            else:
                out.append(f"       - {line.content}")
    return "\n".join(out)