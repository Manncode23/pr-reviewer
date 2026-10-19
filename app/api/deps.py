"""FastAPI dependencies."""

from fastapi import Request

from app.core.config import get_settings
from app.services.review_manager import ReviewManager


def get_manager(request: Request) -> ReviewManager:
    return request.app.state.manager


def get_webhook_secret() -> str | None:
    secret = get_settings().github_webhook_secret
    value = secret.get_secret_value() if secret else ""
    return value or None