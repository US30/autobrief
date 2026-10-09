import pytest

from autobrief import db, llm
from autobrief.schema import Meeting

TRANSCRIPT = """Priya: Thanks everyone, let's start.
Arjun: I'll send the revised proposal to the client by Friday.
Priya: Meera, can you pull the receivables ageing report by tomorrow?
Meera: Yes, will do.
Arjun: Should we renew the analytics tool licence?
Priya: Not now. Let's park that until next quarter.
Priya: So we are agreed: we go with the phased rollout."""


@pytest.fixture()
def meeting():
    return Meeting(title="Weekly project sync", date="2026-09-14", transcript=TRANSCRIPT)  # a Monday


@pytest.fixture()
def con():
    return db.connect(":memory:")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests never call OpenAI, GitHub or Slack, even when real keys are in .env."""
    monkeypatch.setattr(llm, "available", lambda: False)
    for k in ("GITHUB_TOKEN", "GITHUB_REPO", "SLACK_WEBHOOK_URL", "WEBHOOK_SECRET"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture()
def fake_llm(monkeypatch):
    """Install a canned Extraction as the LLM's answer and record the prompt."""
    def install(extraction):
        seen = []
        monkeypatch.setattr(llm, "available", lambda: True)
        monkeypatch.setattr(llm, "structured", lambda prompt, schema, retries=3: seen.append(prompt) or extraction)
        return seen
    return install
