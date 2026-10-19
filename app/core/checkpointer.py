"""Postgres-backed LangGraph checkpointer."""

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver

from app.core.config import get_settings


@contextmanager
def postgres_checkpointer() -> Iterator[PostgresSaver]:
    """Yield a ready-to-use checkpointer; connection closes on exit."""
    with PostgresSaver.from_conn_string(get_settings().database_url) as saver:
        saver.setup()  # creates the checkpoint tables on first run (safe to repeat)
        yield saver