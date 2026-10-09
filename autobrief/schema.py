"""Data contracts. The LLM must return an Extraction; everything downstream works on validated objects."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class Meeting(BaseModel):
    title: str
    date: date
    transcript: str  # one "Speaker: text" turn per line


class ActionItem(BaseModel):
    task: str = Field(description="What must be done, as a short imperative that makes sense on its own")
    owner: str | None = Field(description="Attendee who will do it, exactly as named in the transcript, else null")
    due: str | None = Field(description="Deadline as YYYY-MM-DD resolved against the meeting date, else null")
    evidence: str = Field(description="Exact sentence from the transcript where the commitment is made")
    confident: bool = Field(description="False if the commitment, owner or deadline is unclear")


class Extraction(BaseModel):
    summary: str = Field(description="Two sentences on what the meeting covered")
    decisions: list[str]
    action_items: list[ActionItem]
