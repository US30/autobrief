"""SQLite store: meetings, action items with review status, append-only event log."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "autobrief.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY, title TEXT, date TEXT, transcript TEXT, summary TEXT, decisions TEXT,
    source TEXT, email TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY, meeting_id INTEGER REFERENCES meetings(id), task TEXT, owner TEXT, due TEXT,
    evidence TEXT, status TEXT, review_reason TEXT, task_ref TEXT);
CREATE TABLE IF NOT EXISTS events (ts TEXT, meeting_id INTEGER, item_id INTEGER, actor TEXT, action TEXT, detail TEXT);
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Default data/autobrief.db, overridable with AUTOBRIEF_DB (tests use :memory:)."""
    con = sqlite3.connect(str(path or os.getenv("AUTOBRIEF_DB") or DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def log(con, meeting_id: int, item_id: int | None, actor: str, action: str, detail: str = "") -> None:
    con.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
                [datetime.now().isoformat(timespec="seconds"), meeting_id, item_id, actor, action, detail])
    con.commit()


def save_meeting(con, m, extraction, source: str, items: list[dict]) -> tuple[int, list[dict]]:
    mid = con.execute("INSERT INTO meetings (title, date, transcript, summary, decisions, source, created_at) VALUES (?,?,?,?,?,?,?)",
                      [m.title, str(m.date), m.transcript, extraction.summary, json.dumps(extraction.decisions), source,
                       datetime.now().isoformat(timespec="seconds")]).lastrowid
    saved = []
    for it in items:
        iid = con.execute("INSERT INTO items (meeting_id, task, owner, due, evidence, status, review_reason) VALUES (?,?,?,?,?,?,?)",
                          [mid, it["task"], it["owner"], it["due"], it["evidence"], it["status"], it["review_reason"]]).lastrowid
        saved.append(it | {"id": iid, "task_ref": None})
    con.commit()
    log(con, mid, None, "autobrief", "extracted", f"{len(items)} items via {source}")
    return mid, saved


def get_meeting(con, mid: int) -> dict | None:
    row = con.execute("SELECT * FROM meetings WHERE id = ?", [mid]).fetchone()
    if not row:
        return None
    items = [dict(r) for r in con.execute("SELECT * FROM items WHERE meeting_id = ? ORDER BY id", [mid])]
    return dict(row) | {"decisions": json.loads(row["decisions"]), "items": items}


def get_item(con, item_id: int) -> dict | None:
    row = con.execute("SELECT * FROM items WHERE id = ?", [item_id]).fetchone()
    return dict(row) if row else None


def update_item(con, item_id: int, **fields) -> None:
    con.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?", [*fields.values(), item_id])
    con.commit()
