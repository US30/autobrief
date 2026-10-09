"""OpenAI client. One structured call per meeting.

Returns None when no key is set or the API fails, so the pipeline and tests run offline.
"""
from __future__ import annotations

import os
import time
from typing import TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()
T = TypeVar("T", bound=BaseModel)
DEFAULT_MODEL = "gpt-4.1-nano"
last_error: str | None = None  # last swallowed API error, so callers can report it


def available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def model_name() -> str:
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


def structured(prompt: str, schema: type[T], retries: int = 3) -> T | None:
    global last_error
    if not available():
        return None
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=model_name()).with_structured_output(schema)
    for i in range(retries):
        try:
            return llm.invoke(prompt)
        except Exception as e:  # rate limit / transient
            last_error = f"{type(e).__name__}: {str(e)[:300]}"
            time.sleep(2 ** i)
    return None
