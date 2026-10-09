from datetime import date

from autobrief import extract
from autobrief.schema import ActionItem

MON = date(2026, 9, 14)


def item(**kw):
    base = dict(task="Send the revised proposal to the client", owner="Arjun", due="2026-09-18",
                evidence="I'll send the revised proposal to the client by Friday.", confident=True)
    return ActionItem(**(base | kw))


def test_participants_in_speaking_order(meeting):
    assert extract.participants(meeting.transcript) == ["Priya", "Arjun", "Meera"]


def test_resolve_due_phrases():
    assert extract.resolve_due("Friday", MON) == "2026-09-18"
    assert extract.resolve_due("end of day tomorrow", MON) == "2026-09-15"
    assert extract.resolve_due("the end of this week", MON) == "2026-09-18"
    assert extract.resolve_due("Monday", MON) == "2026-09-21"  # never the meeting day itself
    assert extract.resolve_due("October 3", MON) == "2026-10-03"
    assert extract.resolve_due("soon", MON) is None


def test_rule_baseline_finds_direct_commitments_only(meeting):
    got = {(i.owner, i.due) for i in extract.rule_extract(meeting).action_items}
    assert got == {("Arjun", "2026-09-18"), ("Meera", "2026-09-15")}


def test_prompt_gives_the_model_date_weekday_and_attendees(meeting, fake_llm):
    seen = fake_llm(None)
    extract.llm_extract(meeting)
    assert "2026-09-14 (Monday)" in seen[0] and "Attendees: Priya, Arjun, Meera" in seen[0]


def test_review_reasons(meeting):
    assert extract.review_reason(item(), meeting) is None
    assert "evidence" in extract.review_reason(item(evidence="Arjun promised to email the CEO."), meeting)
    assert extract.review_reason(item(owner=None), meeting) == "no owner"
    assert "not an attendee" in extract.review_reason(item(owner="Rahul"), meeting)
    assert "before the meeting" in extract.review_reason(item(due="2026-09-01"), meeting)
    assert "valid date" in extract.review_reason(item(due="next week"), meeting)
    assert "uncertain" in extract.review_reason(item(confident=False), meeting)
