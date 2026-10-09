import httpx

from autobrief import db, graph
from autobrief.schema import ActionItem, Extraction

GOOD = ActionItem(task="Send the revised proposal to the client", owner="Arjun", due="2026-09-18",
                  evidence="I'll send the revised proposal to the client by Friday.", confident=True)
INVENTED = ActionItem(task="Email the CEO", owner="Arjun", due=None, evidence="Arjun will email the CEO tonight.", confident=True)


def extraction(*items):
    return Extraction(summary="The team reviewed the proposal.", decisions=["we go with the phased rollout"], action_items=list(items))


def events(con):
    return [r["action"] for r in con.execute("SELECT action FROM events")]


def test_checked_item_becomes_a_task_and_invented_one_waits_for_review(con, meeting, fake_llm, monkeypatch):
    fake_llm(extraction(GOOD, INVENTED))
    posted = []
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: posted.append((url, kw["json"])) or httpx.Response(200, request=httpx.Request("POST", url)))
    s = graph.run(con, meeting)
    good, bad = db.get_meeting(con, s["meeting_id"])["items"]
    assert (good["status"], good["task_ref"]) == ("auto_approved", f"local-{good['id']}")
    assert (bad["status"], bad["task_ref"]) == ("needs_review", None) and "evidence" in bad["review_reason"]
    assert s["notified"] and "Email the CEO" in posted[0][1]["text"] and "Send the revised" not in posted[0][1]["text"]
    action, pending = s["email"].split("To be confirmed")
    assert "Arjun: Send the revised proposal to the client (due 2026-09-18)" in action and "Email the CEO" in pending
    assert events(con) == ["extracted", "task_created", "review_requested"]


def test_notify_step_is_skipped_when_nothing_needs_review(con, meeting, fake_llm):
    fake_llm(extraction(GOOD))
    s = graph.run(con, meeting)
    assert "notified" not in s and "review_requested" not in events(con) and "To be confirmed" not in s["email"]


def test_regex_fallback_never_creates_tasks_on_its_own(con, meeting, fake_llm):
    fake_llm(None)  # API failure
    s = graph.run(con, meeting)
    assert s["source"] == "rules" and len(s["items"]) == 2
    assert all(i["status"] == "needs_review" and i["task_ref"] is None for i in s["items"])
