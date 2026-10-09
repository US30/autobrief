"""Turn a transcript into decisions and action items, then decide which items a human must confirm.

llm_extract   one OpenAI structured call
rule_extract  regex baseline (offline fallback and the eval's point of comparison)
review_reason deterministic checks on each item; the model's own confidence is only one of them
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from rapidfuzz import fuzz

from autobrief import llm
from autobrief.schema import ActionItem, Extraction, Meeting

TURN = re.compile(r"^([A-Z][\w .'-]{0,30}?):\s+(.+)$")
EVIDENCE_MIN = 90
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]

PROMPT = """You extract follow-ups from a meeting transcript for a consulting team.

Meeting: {title}
Date: {date} ({weekday})
Attendees: {people}

Rules:
- An action item is a task an attendee committed to or was assigned and accepted in this meeting.
- Do not include work that is already done, proposals that were rejected or parked, cancelled tasks, or vague ideas with no owner.
- If a task is reassigned, the owner is the person who ends up with it.
- owner must be one of the attendees. due is YYYY-MM-DD worked out from the meeting date, or null if no deadline was said.
- evidence is the exact sentence, copied from the transcript, where the commitment is made.
- decisions are things the group agreed, not tasks.

Transcript:
{transcript}"""


def turns(transcript: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for line in transcript.splitlines() if (m := TURN.match(line.strip()))]


def participants(transcript: str) -> list[str]:
    return list(dict.fromkeys(s for s, _ in turns(transcript)))


def llm_extract(m: Meeting) -> Extraction | None:
    return llm.structured(PROMPT.format(title=m.title, date=m.date, weekday=m.date.strftime("%A"),
                                        people=", ".join(participants(m.transcript)), transcript=m.transcript), Extraction)


def resolve_due(phrase: str, today: date) -> str | None:
    """'Friday', 'tomorrow', 'the end of this week', 'October 3' -> ISO date after the meeting date."""
    p = phrase.lower()
    if "tomorrow" in p:
        return str(today + timedelta(days=1))
    if "end of this week" in p or "end of the week" in p:
        return str(today + timedelta(days=(4 - today.weekday()) % 7))
    for i, d in enumerate(WEEKDAYS):
        if d in p:
            return str(today + timedelta(days=(i - today.weekday() - 1) % 7 + 1))
    if md := re.search(rf"({'|'.join(MONTHS)}) (\d{{1,2}})", p):
        d = date(today.year, MONTHS.index(md.group(1)) + 1, int(md.group(2)))
        return str(d if d >= today else d.replace(year=today.year + 1))
    return None


SELF = re.compile(r"\bI(?:'ll| will) (.+?)(?: by ([^.?!]+))?[.?!]")
ASK = re.compile(r"^(\w+), (?:can|could) you (.+?)(?: by ([^.?!]+))?\?")


def rule_extract(m: Meeting) -> Extraction:
    """Baseline: 'I'll <task> [by <when>]' and '<Name>, can you <task> [by <when>]?'. No context, so it over-triggers."""
    people = participants(m.transcript)
    items = []
    for speaker, text in turns(m.transcript):
        hit = [(speaker, *g.groups()) for g in [SELF.search(text)] if g]
        hit += [g.groups() for g in [ASK.match(text)] if g and g.group(1) in people]
        for owner, task, when in hit:
            items.append(ActionItem(task=task.strip().capitalize(), owner=owner, due=resolve_due(when, m.date) if when else None,
                                    evidence=text, confident=True))
    return Extraction(summary=f"{m.title}: {len(items)} follow-ups found by the rule baseline.", decisions=[], action_items=items)


def review_reason(item: ActionItem, m: Meeting) -> str | None:
    """Why a human must confirm this item before a task is created. None means it can go through."""
    people = participants(m.transcript)
    if fuzz.partial_ratio(item.evidence.lower(), m.transcript.lower()) < EVIDENCE_MIN:
        return "evidence quote not found in transcript"
    if not item.owner:
        return "no owner"
    if item.owner not in people:
        return "owner is not an attendee"
    if item.due:
        try:
            if date.fromisoformat(item.due) < m.date:
                return "due date is before the meeting"
        except ValueError:
            return "due date is not a valid date"
    if not item.confident:
        return "model marked it uncertain"
    return None
