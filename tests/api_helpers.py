"""Helpers for API tests."""

import hashlib
import hmac
import json
import time

WEBHOOK_SECRET = "test-secret"
STATUS_URL = "/reviews/o/r/1/abc123"  # thread o/r#1@abc123 from FakeClient


def sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def pr_payload(action: str = "opened", draft: bool = False, number: int = 1) -> dict:
    return {
        "action": action,
        "pull_request": {"number": number, "draft": draft},
        "repository": {"full_name": "o/r"},
    }


def webhook_request(client, payload: dict, event: str = "pull_request", signature=None):
    body = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": event,
        "X-Hub-Signature-256": signature or sign(body),
    }
    return client.post("/webhooks/github", content=body, headers=headers)


def wait_for_status(client, url: str, wanted: set[str], timeout: float = 5.0) -> dict:
    """Poll a review until its status is one of `wanted`."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        response = client.get(url)
        if response.status_code == 200:
            last = response.json()
            if last["status"] in wanted:
                return last
        time.sleep(0.05)
    raise AssertionError(f"Review never reached {wanted}; last seen: {last}")