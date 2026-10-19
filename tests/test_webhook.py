from app.api.deps import get_webhook_secret
from tests.api_helpers import STATUS_URL, pr_payload, wait_for_status, webhook_request


def test_valid_pull_request_event_starts_a_review(api_env):
    response = webhook_request(api_env.client, pr_payload())

    assert response.status_code == 202
    assert response.json()["thread_id"] == "o/r#1@abc123"
    wait_for_status(api_env.client, STATUS_URL, {"awaiting_approval"})


def test_bad_signature_is_rejected(api_env):
    response = webhook_request(api_env.client, pr_payload(), signature="sha256=deadbeef")

    assert response.status_code == 401
    assert api_env.calls["count"] == 0


def test_ping_is_answered(api_env):
    response = webhook_request(api_env.client, {"zen": "hello"}, event="ping")

    assert response.status_code == 200
    assert response.json() == {"status": "pong"}


def test_irrelevant_actions_are_ignored(api_env):
    response = webhook_request(api_env.client, pr_payload(action="closed"))

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert api_env.calls["count"] == 0


def test_draft_pull_requests_are_ignored(api_env):
    response = webhook_request(api_env.client, pr_payload(draft=True))

    assert response.json()["status"] == "ignored"
    assert api_env.calls["count"] == 0


def test_webhook_refused_when_secret_is_not_configured(api_env):
    api_env.app.dependency_overrides[get_webhook_secret] = lambda: None

    response = webhook_request(api_env.client, pr_payload())

    assert response.status_code == 503