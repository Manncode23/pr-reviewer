"""FastAPI application.

Run from the project root:
    uvicorn app.api.main:app --port 8000
Interactive docs: http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import reviews, webhooks
from app.core.checkpointer import postgres_checkpointer_pool
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.graph.builder import build_review_graph
from app.services.review_manager import ReviewManager
from app.services.review_service import ReviewService
from app.tools.github_client import GitHubClient

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(get_settings().log_level)
    with postgres_checkpointer_pool() as saver:
        client = GitHubClient()
        graph = build_review_graph(client, saver)
        manager = ReviewManager(ReviewService(graph, client))
        app.state.manager = manager
        logger.info("API ready")
        try:
            yield
        finally:
            manager.shutdown()


def create_app(*, use_lifespan: bool = True) -> FastAPI:
    """App factory. Tests pass use_lifespan=False and inject their own manager."""
    app = FastAPI(
        title="PR Reviewer",
        description="Multi-agent pull request reviewer built with LangGraph",
        lifespan=lifespan if use_lifespan else None,
    )
    app.include_router(reviews.router)
    app.include_router(webhooks.router)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()