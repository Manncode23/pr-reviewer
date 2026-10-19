"""Send a signed fake 'pull_request opened' webhook to the local API.

Needs GITHUB_WEBHOOK_SECRET in .env (same value the server was started with).

    python -m scripts.send_test_webhook Manncode23/querymind 1
    python -m scripts.send_test_webhook Manncode23/querymind 1 --tamper   # expect 401
"""

import argparse
import hashlib
import hmac
import json

import httpx

from app.core.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", help="owner/name")
    parser.add_argument("pr_number", type=int)
    parser.add_argument("--url", default="http://localhost:8000/webhooks/github")
    parser.add_argument("--tamper", action="store_true", help="send a wrong signature")
    args = parser.parse_args()

    secret = get_settings().github_webhook_secret
    if not secret or not secret.get_secret_value():
        raise SystemExit("Set GITHUB_WEBHOOK_SECRET in .env first")

    payload = {
        "action": "opened",
        "pull_request": {"number": args.pr_number, "draft": False},
        "repository": {"full_name": args.repo},
    }
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(
        secret.get_secret_value().encode(), body, hashlib.sha256
    ).hexdigest()
    if args.tamper:
        signature = "sha256=" + "0" * 64

    response = httpx.post(
        args.url,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": signature,
        },
        timeout=30,
    )
    print(response.status_code, response.text)


if __name__ == "__main__":
    main()