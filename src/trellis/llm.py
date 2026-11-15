"""NanoGPT chat completions (OpenAI-compatible), with JSON extraction, validate-then-retry, and a usage log.

Tests set `FAKE` to a function (model, messages) -> str so no network call is made.
"""

import json
import logging
import re
import sqlite3
import time
from collections.abc import Callable

import httpx

from trellis.config import Settings
from trellis.db import now_utc

log = logging.getLogger(__name__)
FAKE: Callable[[str, list[dict]], str] | None = None
DAILY_CAP_DEFAULT = 400


class LLMError(Exception):
    pass


def extract_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^<think>.*?</think>\s*", "", text, flags=re.S)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in response")
    return json.loads(text[start:end + 1])


def _log(conn, user_id, purpose, model, usage, ms, ok, error=None):
    conn.execute(
        """INSERT INTO llm_call(user_id, purpose, model, prompt_tokens, completion_tokens, duration_ms, ok, error,
                                created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id, purpose, model, usage.get("prompt_tokens"), usage.get("completion_tokens"), ms, int(ok),
         (error or "")[:500] or None, now_utc()))


def calls_today(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM llm_call WHERE created_at >= date('now')").fetchone()[0]


def call_llm(conn: sqlite3.Connection, s: Settings, *, purpose: str, model: str, messages: list[dict],
             user_id: int | None = None, temperature: float = 0.3, max_tokens: int = 2500) -> str:
    import os

    cap = int(os.environ.get("LLM_DAILY_CAP", DAILY_CAP_DEFAULT))
    if calls_today(conn) >= cap:
        raise LLMError(f"daily LLM call cap ({cap}) reached")
    t0 = time.monotonic()
    usage: dict = {}
    try:
        if FAKE is not None:
            text = FAKE(model, messages)
        else:
            if not s.nanogpt_api_key:
                raise LLMError("NANOGPT_API_KEY is not set")
            r = httpx.post(f"{s.nanogpt_base_url.rstrip('/')}/chat/completions",
                           headers={"Authorization": f"Bearer {s.nanogpt_api_key}"},
                           json={"model": model, "messages": messages, "temperature": temperature,
                                 "max_tokens": max_tokens},
                           timeout=180)
            r.raise_for_status()
            body = r.json()
            usage = body.get("usage") or {}
            text = body["choices"][0]["message"]["content"] or ""
    except Exception as e:
        _log(conn, user_id, purpose, model, usage, int((time.monotonic() - t0) * 1000), False, f"{type(e).__name__}: {e}")
        raise
    _log(conn, user_id, purpose, model, usage, int((time.monotonic() - t0) * 1000), True)
    return text


def call_json(conn: sqlite3.Connection, s: Settings, *, purpose: str, model: str, messages: list[dict],
              validate: Callable[[dict], list[str]], user_id: int | None = None, max_tokens: int = 2500,
              temperature: float = 0.3) -> dict:
    """Call, extract JSON, validate; on failure send the errors back once. Raises LLMError if both tries fail.

    `validate` may also normalise the object in place; it returns a list of human-readable errors."""
    messages = list(messages)
    errors: list[str] = []
    for attempt in range(2):
        raw = call_llm(conn, s, purpose=purpose, model=model, messages=messages, user_id=user_id,
                       max_tokens=max_tokens, temperature=temperature)
        try:
            obj = extract_json(raw)
            errors = validate(obj)
        except (ValueError, TypeError, KeyError) as e:
            obj, errors = None, [f"could not parse a JSON object: {e}"]
        if obj is not None and not errors:
            return obj
        log.info("%s attempt %d failed validation: %s", purpose, attempt + 1, errors[:5])
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": "That failed validation:\n- " + "\n- ".join(errors[:20])
                      + "\nFix these and return the full JSON object again, with no other text."}]
    raise LLMError(f"{purpose}: invalid output after retry: {'; '.join(errors[:5])}")
