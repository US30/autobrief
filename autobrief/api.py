"""FastAPI app. Run: uvicorn autobrief.api:app --reload

POST /webhook/transcript   a meeting tool (or curl) posts a transcript; the pipeline runs and returns the result
GET  /review               items waiting for a human
POST /review/{item_id}     approve (optionally fixing owner or due date) or reject
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from autobrief import connectors, db, graph
from autobrief.schema import Meeting

app = FastAPI(title="AutoBrief")
_con = None


def con():
    global _con
    if _con is None:
        _con = db.connect()
    return _con


class Decision(BaseModel):
    user: str
    decision: str  # approved | rejected
    owner: str | None = None
    due: str | None = None


@app.post("/webhook/transcript")
def webhook(m: Meeting, use_llm: bool = True, x_webhook_secret: str | None = Header(default=None)):
    secret = os.getenv("WEBHOOK_SECRET")
    if secret and x_webhook_secret != secret:
        raise HTTPException(401, "bad webhook secret")
    s = graph.run(con(), m, use_llm)
    return db.get_meeting(con(), s["meeting_id"])


@app.get("/meetings/{meeting_id}")
def meeting(meeting_id: int):
    m = db.get_meeting(con(), meeting_id)
    if not m:
        raise HTTPException(404, "no such meeting")
    return m


@app.get("/review")
def review(meeting_id: int | None = None):
    rows = con().execute("SELECT i.*, m.title AS meeting FROM items i JOIN meetings m ON m.id = i.meeting_id "
                         "WHERE i.status = 'needs_review' AND (? IS NULL OR i.meeting_id = ?) ORDER BY i.id",
                         [meeting_id, meeting_id]).fetchall()
    return [dict(r) for r in rows]


@app.post("/review/{item_id}")
def decide(item_id: int, d: Decision):
    if d.decision not in ("approved", "rejected"):
        raise HTTPException(422, "decision must be approved or rejected")
    item = db.get_item(con(), item_id)
    if not item:
        raise HTTPException(404, "no such item")
    if item["status"] != "needs_review":
        raise HTTPException(409, f"item is already {item['status']}")
    item |= {k: v for k, v in dict(owner=d.owner, due=d.due).items() if v}  # reviewer may correct owner / due
    item["status"] = d.decision
    if d.decision == "approved":
        item["task_ref"] = connectors.create_task(item, db.get_meeting(con(), item["meeting_id"])["title"])
    db.update_item(con(), item_id, owner=item["owner"], due=item["due"], status=item["status"], task_ref=item["task_ref"])
    db.log(con(), item["meeting_id"], item_id, d.user, d.decision, item["task_ref"] or "")
    m = db.get_meeting(con(), item["meeting_id"])  # refresh the draft so it reflects the decision
    email = graph.compose_email(m["title"], m["date"], m["summary"], m["decisions"], m["items"])
    con().execute("UPDATE meetings SET email = ? WHERE id = ?", [email, m["id"]])
    con().commit()
    return item
