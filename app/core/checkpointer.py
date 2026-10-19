"""Postgres-backed LangGraph checkpointers."""

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import get_settings
from app.schemas.findings import Category, Finding, Severity
from app.schemas.pr import DiffLine, FileDiff, Hunk, LineKind, PullRequestData
from app.schemas.review import Assignment
from app.schemas.static import StaticAnalysisResult, ToolIssue

# Every custom type that can end up inside the graph state. LangGraph only
# rebuilds registered types from a checkpoint, so new state models go here.
STATE_TYPES = [
    PullRequestData, FileDiff, Hunk, DiffLine, LineKind,
    StaticAnalysisResult, ToolIssue,
    Finding, Severity, Category,
    Assignment,
]


def review_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=STATE_TYPES)


@contextmanager
def postgres_checkpointer() -> Iterator[PostgresSaver]:
    """Single-connection checkpointer for scripts. Closes on exit."""
    with PostgresSaver.from_conn_string(get_settings().database_url) as saver:
        saver.serde = review_serde()
        saver.setup()  # creates the checkpoint tables on first run (safe to repeat)
        yield saver


@contextmanager
def postgres_checkpointer_pool(max_size: int = 5) -> Iterator[PostgresSaver]:
    """Pooled checkpointer for the long-running API server."""
    connection_kwargs = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
    with ConnectionPool(
        conninfo=get_settings().database_url,
        max_size=max_size,
        kwargs=connection_kwargs,
    ) as pool:
        saver = PostgresSaver(pool)
        saver.serde = review_serde()
        saver.setup()
        yield saver