"""LangGraph pipeline: extract -> check -> save -> create tasks -> (notify reviewers) -> draft email.

Items that pass every check become tasks at once. The rest wait for a human in the review queue.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from autobrief import connectors, db, extract
from autobrief.schema import Extraction, Meeting


class State(TypedDict, total=False):
    meeting: Meeting
    extraction: Extraction
    source: str  # llm | rules
    items: list[dict]
    meeting_id: int
    notified: bool
    email: str


def check_items(m: Meeting, ex: Extraction, source: str) -> list[dict]:
    items = []
    for it in ex.action_items:
        # the regex fallback has no context, so nothing it finds is trusted without a human
        reason = "LLM unavailable, found by regex fallback" if source == "rules" else extract.review_reason(it, m)
        items.append(it.model_dump(exclude={"confident"}) | dict(status="needs_review" if reason else "auto_approved",
                                                                  review_reason=reason))
    return items


def compose_email(title: str, date: str, summary: str, decisions: list[str], items: list[dict]) -> str:
    """Template, not LLM: the email can only contain what was extracted and checked."""
    def line(i):
        return f"- {i['owner'] or 'Unassigned'}: {i['task']}" + (f" (due {i['due']})" if i["due"] else "")

    done = [i for i in items if i["status"] in ("auto_approved", "approved")]
    wait = [i for i in items if i["status"] == "needs_review"]
    parts = [f"Subject: Follow-up: {title} ({date})", "", "Hi all,", "", summary]
    for head, rows in [("Decisions", [f"- {d}" for d in decisions]), ("Action items", [line(i) for i in done]),
                       ("To be confirmed", [line(i) for i in wait])]:
        if rows:
            parts += ["", head, *rows]
    return "\n".join(parts + ["", "Thanks"])


def build_graph(con, use_llm: bool = True):
    def n_extract(s: State):
        ex = extract.llm_extract(s["meeting"]) if use_llm else None
        return {"extraction": ex or extract.rule_extract(s["meeting"]), "source": "llm" if ex else "rules"}

    def n_check(s: State):
        return {"items": check_items(s["meeting"], s["extraction"], s["source"])}

    def n_save(s: State):
        mid, items = db.save_meeting(con, s["meeting"], s["extraction"], s["source"], s["items"])
        return {"meeting_id": mid, "items": items}

    def n_tasks(s: State):
        for it in s["items"]:
            if it["status"] == "auto_approved":
                it["task_ref"] = connectors.create_task(it, s["meeting"].title)
                db.update_item(con, it["id"], task_ref=it["task_ref"])
                db.log(con, s["meeting_id"], it["id"], "autobrief", "task_created", it["task_ref"])
        return {"items": s["items"]}

    def n_notify(s: State):
        pending = [i for i in s["items"] if i["status"] == "needs_review"]
        sent = connectors.notify_review(s["meeting_id"], s["meeting"].title, pending)
        db.log(con, s["meeting_id"], None, "autobrief", "review_requested", f"{len(pending)} items, slack={sent}")
        return {"notified": sent}

    def n_email(s: State):
        m, ex = s["meeting"], s["extraction"]
        email = compose_email(m.title, str(m.date), ex.summary, ex.decisions, s["items"])
        con.execute("UPDATE meetings SET email = ? WHERE id = ?", [email, s["meeting_id"]])
        con.commit()
        return {"email": email}

    g = StateGraph(State)
    for name, fn in [("extract", n_extract), ("check", n_check), ("save", n_save), ("tasks", n_tasks),
                     ("notify", n_notify), ("email", n_email)]:
        g.add_node(name, fn)
    g.add_edge(START, "extract")
    for a, b in [("extract", "check"), ("check", "save"), ("save", "tasks"), ("notify", "email")]:
        g.add_edge(a, b)
    g.add_conditional_edges("tasks", lambda s: "notify" if any(i["status"] == "needs_review" for i in s["items"]) else "email")
    g.add_edge("email", END)
    return g.compile()


def run(con, meeting: Meeting, use_llm: bool = True) -> State:
    return build_graph(con, use_llm).invoke({"meeting": meeting})
