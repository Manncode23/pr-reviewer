from tests.api_helpers import STATUS_URL, wait_for_status

START = {"repo": "o/r", "pr_number": 1}


def test_health_ok(api_env):
    assert api_env.client.get("/health").json() == {"status": "ok"}


def test_start_review_runs_in_background(api_env):
    response = api_env.client.post("/reviews", json=START)

    assert response.status_code == 202
    data = response.json()
    assert data["thread_id"] == "o/r#1@abc123"
    assert data["status_url"] == STATUS_URL
    assert data["started"] is True

    body = wait_for_status(api_env.client, STATUS_URL, {"awaiting_approval"})
    assert len(body["result"]["findings"]) == 4


def test_start_accepts_a_pr_url(api_env):
    response = api_env.client.post(
        "/reviews", json={"pr_url": "https://github.com/o/r/pull/1"}
    )
    assert response.status_code == 202
    assert response.json()["thread_id"] == "o/r#1@abc123"


def test_start_validates_input(api_env):
    assert api_env.client.post("/reviews", json={}).status_code == 422
    assert api_env.client.post("/reviews", json={"pr_url": "not-a-url"}).status_code == 422


def test_duplicate_start_does_not_rerun(api_env):
    api_env.client.post("/reviews", json=START)
    wait_for_status(api_env.client, STATUS_URL, {"awaiting_approval"})
    calls_after_first = api_env.calls["count"]

    second = api_env.client.post("/reviews", json=START).json()

    assert second["started"] is False
    assert second["status"] == "awaiting_approval"
    assert api_env.calls["count"] == calls_after_first


def test_approve_posts_comments_and_blocks_double_approval(api_env):
    api_env.client.post("/reviews", json=START)
    wait_for_status(api_env.client, STATUS_URL, {"awaiting_approval"})

    first = api_env.client.post(f"{STATUS_URL}/approve", json={"approve_all": True})

    assert first.status_code == 200
    assert first.json()["status"] == "completed"
    assert first.json()["result"]["published"] is True
    assert len(api_env.github.posted) == 1
    assert len(api_env.github.posted[0]["comments"]) == 4

    second = api_env.client.post(f"{STATUS_URL}/approve", json={"approve_all": True})
    assert second.status_code == 409


def test_unknown_review_returns_404(api_env):
    assert api_env.client.get("/reviews/o/r/9/deadbeef").status_code == 404