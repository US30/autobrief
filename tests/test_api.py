import pytest
from fastapi.testclient import TestClient

from autobrief import api


@pytest.fixture()
def client(con, monkeypatch):
    monkeypatch.setattr(api, "_con", con)
    return TestClient(api.app)


def payload(meeting):
    return meeting.model_dump(mode="json")


def test_webhook_review_approve_flow(client, meeting):
    m = client.post("/webhook/transcript", json=payload(meeting)).json()  # offline -> regex fallback -> all need review
    assert m["source"] == "rules" and [i["status"] for i in m["items"]] == ["needs_review"] * 2
    first, second = (i["id"] for i in client.get("/review").json())
    ok = client.post(f"/review/{first}", json={"user": "priya", "decision": "approved", "due": "2026-09-17"}).json()
    assert ok["status"] == "approved" and ok["task_ref"] == f"local-{first}" and ok["due"] == "2026-09-17"
    assert client.post(f"/review/{second}", json={"user": "priya", "decision": "rejected"}).json()["task_ref"] is None
    after = client.get(f"/meetings/{m['id']}").json()
    assert "(due 2026-09-17)" in after["email"] and "To be confirmed" not in after["email"]
    assert client.get("/review").json() == []


def test_review_errors(client, meeting):
    item = client.post("/webhook/transcript", json=payload(meeting)).json()["items"][0]["id"]
    assert client.post(f"/review/{item}", json={"user": "u", "decision": "maybe"}).status_code == 422
    assert client.post("/review/999", json={"user": "u", "decision": "approved"}).status_code == 404
    client.post(f"/review/{item}", json={"user": "u", "decision": "approved"})
    assert client.post(f"/review/{item}", json={"user": "u", "decision": "rejected"}).status_code == 409
    assert client.get("/meetings/999").status_code == 404


def test_webhook_secret_is_enforced_when_set(client, meeting, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "s3cret")
    assert client.post("/webhook/transcript", json=payload(meeting)).status_code == 401
    assert client.post("/webhook/transcript", json=payload(meeting), headers={"X-Webhook-Secret": "s3cret"}).status_code == 200
