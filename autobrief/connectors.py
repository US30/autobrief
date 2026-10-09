"""Outbound integrations over REST. Each one is optional and switched on by environment variables.

Tasks -> GitHub Issues (GITHUB_TOKEN + GITHUB_REPO="owner/repo"), else a local reference.
Review -> Slack incoming webhook (SLACK_WEBHOOK_URL), else nothing is sent and items wait in GET /review.
"""
from __future__ import annotations

import os

import httpx

TIMEOUT = 10


def create_task(item: dict, meeting_title: str) -> str:
    token, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPO")
    if not (token and repo):
        return f"local-{item['id']}"
    body = (f"Owner: {item['owner']}\nDue: {item['due'] or 'not set'}\nMeeting: {meeting_title}\n\n"
            f"> {item['evidence']}\n\nCreated by AutoBrief.")
    r = httpx.post(f"https://api.github.com/repos/{repo}/issues", timeout=TIMEOUT,
                   headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                   json={"title": item["task"], "body": body})
    r.raise_for_status()
    return r.json()["html_url"]


def notify_review(meeting_id: int, meeting_title: str, items: list[dict]) -> bool:
    """Post the items that need a human decision to Slack. Returns True if a message was sent."""
    url = os.getenv("SLACK_WEBHOOK_URL")
    if not url or not items:
        return False
    base = os.getenv("BASE_URL", "http://localhost:8000")
    lines = [f"• #{i['id']} {i['task']} (owner: {i['owner'] or '?'}, due: {i['due'] or '-'}): {i['review_reason']}" for i in items]
    text = (f"*AutoBrief: {len(items)} follow-up(s) from \"{meeting_title}\" need confirmation*\n" + "\n".join(lines)
            + f"\nReview: {base}/review?meeting_id={meeting_id}")
    httpx.post(url, json={"text": text}, timeout=TIMEOUT).raise_for_status()
    return True
