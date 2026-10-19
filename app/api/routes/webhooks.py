"""GitHub webhook receiver."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.api.deps import get_manager, get_webhook_secret
from app.api.security import verify_signature
from app.core.logging import get_logger
from app.services.review_manager import ReviewManager
from app.tools.github_client import GitHubClientError

logger = get_logger(__name__)
router = APIRouter(tags=["webhooks"])

HANDLED_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


def _ignored(reason: str) -> JSONResponse:
    return JSONResponse(status_code=200, content={"status": "ignored", "reason": reason})


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    manager: ReviewManager = Depends(get_manager),
    secret: str | None = Depends(get_webhook_secret),
):
    if not secret:
        # Never run an unauthenticated webhook endpoint.
        raise HTTPException(status_code=503, detail="Webhook secret is not configured")

    body = await request.body()
    if not verify_signature(secret, body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    delivery = request.headers.get("X-GitHub-Delivery", "-")
    if event == "ping":
        return JSONResponse(status_code=200, content={"status": "pong"})
    if event != "pull_request":
        return _ignored(f"event '{event}' not handled")

    try:
        payload = json.loads(body)
        action = payload["action"]
        pull_request = payload["pull_request"]
        repo = payload["repository"]["full_name"]
        number = int(pull_request["number"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Malformed payload") from exc

    if action not in HANDLED_ACTIONS:
        return _ignored(f"action '{action}' not handled")
    if pull_request.get("draft"):
        return _ignored("draft pull request")

    logger.info("Webhook %s: %s %s#%s", delivery, action, repo, number)
    try:
        result = await run_in_threadpool(manager.submit, repo, number)
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "thread_id": result.thread_id,
            "started": result.started,
        },
    )