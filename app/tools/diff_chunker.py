"""Split big file diffs into chunks that fit comfortably in one LLM call."""

from app.schemas.pr import DiffLine, FileDiff, Hunk

MAX_CHUNK_CHARS = 15000  # roughly 4k tokens of diff text
MAX_CHUNKS_PER_FILE = 3  # hard cap so one huge file can't eat the whole quota

_LINE_OVERHEAD = 12  # "L1234 + " prefix plus newline


def _line_cost(line: DiffLine) -> int:
    return len(line.content) + _LINE_OVERHEAD


def _hunk_cost(hunk: Hunk) -> int:
    return len(hunk.header) + sum(_line_cost(line) for line in hunk.lines)


def _split_hunk(hunk: Hunk, budget: int) -> list[Hunk]:
    """Cut one oversized hunk into runs of lines.

    Every line keeps its real line number, so the LLM can still cite exact lines.
    """
    pieces: list[Hunk] = []
    current: list[DiffLine] = []
    used = 0
    for line in hunk.lines:
        cost = _line_cost(line)
        if current and used + cost > budget:
            pieces.append(hunk.model_copy(update={"lines": current}))
            current, used = [], 0
        current.append(line)
        used += cost
    if current:
        pieces.append(hunk.model_copy(update={"lines": current}))

    for piece in pieces[1:]:
        piece.header = f"{hunk.header} (continued)"
    return pieces


def split_file_diff(file_diff: FileDiff, max_chars: int | None = None) -> list[FileDiff]:
    """Return the file as one or more chunks, each small enough for one LLM call."""
    limit = max_chars or MAX_CHUNK_CHARS

    pieces: list[Hunk] = []
    for hunk in file_diff.hunks:
        if _hunk_cost(hunk) > limit:
            pieces.extend(_split_hunk(hunk, limit))
        else:
            pieces.append(hunk)

    groups: list[list[Hunk]] = []
    current: list[Hunk] = []
    used = 0
    for hunk in pieces:
        cost = _hunk_cost(hunk)
        if current and used + cost > limit:
            groups.append(current)
            current, used = [], 0
        current.append(hunk)
        used += cost
    if current:
        groups.append(current)

    if len(groups) <= 1:
        return [file_diff]
    return [file_diff.model_copy(update={"hunks": hunks}) for hunks in groups]