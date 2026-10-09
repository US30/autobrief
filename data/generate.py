"""Synthetic meeting transcripts with ground truth.

Each meeting mixes real commitments (six phrasings) with look-alikes that are not action items:
cancelled tasks, finished work, parked proposals and vague ideas.

Usage: python data/generate.py [--n 40] [--seed 7] [--out data/meetings.jsonl]
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

NAMES = ["Priya", "Arjun", "Meera", "Rohan", "Kavya", "Vikram", "Ananya", "Sahil", "Neha", "Dev"]
TITLES = ["Weekly project sync", "Pricing review", "Close process workshop", "Vendor selection check-in",
          "Steering committee prep", "Pilot rollout planning", "Data migration stand-up", "Client status call debrief"]
TASKS = [  # (verb phrase, noun phrase)
    ("send the revised proposal to the client", "the revised proposal"),
    ("update the financial model with Q3 actuals", "the financial model update"),
    ("book a workshop with the client's finance team", "the finance workshop"),
    ("draft the steering committee deck", "the steering committee deck"),
    ("clean up the vendor master data", "the vendor master cleanup"),
    ("share the interview notes with the team", "the interview notes"),
    ("reconcile the headcount numbers with HR", "the headcount reconciliation"),
    ("prepare the cost benchmark for logistics", "the logistics cost benchmark"),
    ("set up the shared project folder", "the shared project folder"),
    ("review the draft contract with legal", "the contract review"),
    ("build the dashboard mock-up for the CFO", "the CFO dashboard mock-up"),
    ("collect the invoice samples from accounts payable", "the invoice sample collection"),
    ("write the status report for the sponsor", "the sponsor status report"),
    ("schedule the kickoff call with the IT team", "the IT kickoff call"),
    ("map the current approval workflow", "the approval workflow map"),
    ("validate the savings estimate with procurement", "the savings estimate validation"),
    ("circulate the minutes of the last workshop", "the workshop minutes"),
    ("test the automation script on last month's data", "the automation script test"),
    ("confirm the budget with the engagement partner", "the budget confirmation"),
    ("prepare the training material for the pilot users", "the pilot training material"),
    ("pull the receivables ageing report", "the receivables ageing report"),
    ("document the data sources for the forecast", "the forecast data source list"),
    ("follow up with the bank on the pending statements", "the bank statement follow-up"),
    ("compare the three shortlisted vendors", "the vendor comparison"),
    ("translate the survey into Hindi", "the survey translation"),
    ("renew the analytics tool licence", "the licence renewal"),
]
DECISIONS = ["we go with the phased rollout", "the pilot starts with the Mumbai plant", "weekly check-ins move to Tuesdays",
             "we drop the third vendor from the shortlist", "the report goes out monthly, not weekly",
             "we keep the current approval limit", "the client demo is pushed by one week", "we use the client's template for all decks"]
FILLER = ["Numbers from the plant visit looked better than expected.", "The client was happy with last week's session.",
          "I am still waiting on access to their ERP.", "Traffic was terrible this morning, sorry I was late.",
          "The sponsor is travelling until Thursday.", "We are roughly on track against the plan.",
          "Their finance head asked good questions.", "Nothing blocking on my side."]


def due_for(rng: random.Random, today: date) -> tuple[str, str | None]:
    """Pick a deadline and say it the way people do. Meeting days are Mon-Wed so every phrase is unambiguous."""
    kind = rng.choice(["none", "none", "tomorrow", "friday", "monday", "explicit", "explicit"])
    if kind == "none" or (kind == "monday" and today.weekday() == 0):
        return "", None
    if kind == "tomorrow":
        return rng.choice([" by tomorrow", " by end of day tomorrow"]), str(today + timedelta(days=1))
    if kind == "friday":
        return rng.choice([" by Friday", " by the end of this week"]), str(today + timedelta(days=4 - today.weekday()))
    if kind == "monday":
        return " by Monday", str(today + timedelta(days=7 - today.weekday()))
    d = today + timedelta(days=rng.randint(8, 20))
    return f" by {d.strftime('%B')} {d.day}", str(d)


def action_block(rng, style: int, o: str, x: str, lead: str, t: str, d: str) -> list[str]:
    return [
        [f"{o}: I'll {t}{d}."],
        [f"{x}: {o}, can you {t}{d}?", f"{o}: Yes, will do."],
        [f"{x}: Someone needs to {t}.", f"{o}: Leave that with me{d or ', I will sort it out'}."],
        [f"{x}: I can {t}.", f"{lead}: Actually {o} is closer to that work. {o}, please take it{d}.", f"{o}: Okay, noted."],
        [f"{lead}: We still need to {t}.", f"{o}: Put my name on that{d}."],
        [f"{lead}: One more from my list: {o} to {t}{d}.", f"{o}: Yes, that is mine."],
    ][style]


def distractor_block(rng, style: int, a: str, lead: str, t: str, n: str) -> list[str]:
    return [
        [f"{a}: I'll {t}.", f"{lead}: No need, the client dropped that request. Skip it.", f"{a}: Okay, dropping it."],
        [f"{a}: Quick update: {n} is done. I finished it last week."],
        [f"{a}: Should we {t}?", f"{lead}: Not now. Let's park that until next quarter."],
        [f"{a}: At some point someone might want to {t}, but it is not a priority.", f"{lead}: Agreed, not for this sprint."],
    ][style]


def make_meeting(rng: random.Random, idx: int) -> dict:
    people = rng.sample(NAMES, rng.randint(3, 4))
    lead = people[0]
    today = date(2026, 9, 7) + timedelta(weeks=rng.randint(0, 7), days=rng.randint(0, 2))  # Mon-Wed
    tasks = rng.sample(TASKS, 8)
    blocks, gold = [], []
    for t, _ in tasks[:rng.randint(2, 5)]:
        style = rng.randrange(6)
        o = rng.choice(people[1:] if style in (3, 4, 5) else people)  # the lead does not assign work to themself
        x = rng.choice([p for p in people if p != o])
        phrase, due = due_for(rng, today)
        blocks.append(action_block(rng, style, o, x, lead, t, phrase))
        gold.append(dict(task=t, owner=o, due=due))
    for t, n in tasks[5:5 + rng.randint(1, 3)]:
        blocks.append(distractor_block(rng, rng.randrange(4), rng.choice(people[1:]), lead, t, n))
    decisions = rng.sample(DECISIONS, rng.randint(1, 2))
    blocks += [[f"{lead}: So we are agreed: {d}."] for d in decisions]
    blocks += [[f"{rng.choice(people)}: {f}"] for f in rng.sample(FILLER, 3)]
    rng.shuffle(blocks)
    lines = [f"{lead}: Thanks everyone, let's start."] + [l for b in blocks for l in b] + [f"{lead}: Good, that is all for today."]
    return dict(id=idx, title=rng.choice(TITLES), date=str(today), transcript="\n".join(lines),
                gold=dict(action_items=gold, decisions=decisions))


def generate(n: int = 40, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    return [make_meeting(rng, i) for i in range(1, n + 1)]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", default=str(Path(__file__).parent / "meetings.jsonl"))
    a = p.parse_args()
    rows = generate(a.n, a.seed)
    Path(a.out).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print(f"{len(rows)} meetings, {sum(len(r['gold']['action_items']) for r in rows)} gold action items -> {a.out}")
