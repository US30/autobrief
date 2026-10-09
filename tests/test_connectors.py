import httpx

from autobrief import connectors

ITEM = dict(id=7, task="Send the proposal", owner="Arjun", due="2026-09-18", evidence="I'll send the proposal.", review_reason="no owner")


def test_task_stays_local_without_github_settings():
    assert connectors.create_task(ITEM, "Sync") == "local-7"


def test_github_issue_is_created_over_rest(monkeypatch):
    calls = []

    def post(url, **kw):
        calls.append((url, kw))
        return httpx.Response(201, json={"html_url": "https://github.com/acme/tasks/issues/1"}, request=httpx.Request("POST", url))

    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
    monkeypatch.setenv("GITHUB_REPO", "acme/tasks")
    monkeypatch.setattr(httpx, "post", post)
    assert connectors.create_task(ITEM, "Sync") == "https://github.com/acme/tasks/issues/1"
    url, kw = calls[0]
    assert url == "https://api.github.com/repos/acme/tasks/issues" and kw["headers"]["Authorization"] == "Bearer t0ken"
    assert kw["json"]["title"] == "Send the proposal" and "Owner: Arjun" in kw["json"]["body"]


def test_no_slack_message_without_webhook_or_items(monkeypatch):
    assert connectors.notify_review(1, "Sync", [ITEM]) is False
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    assert connectors.notify_review(1, "Sync", []) is False
