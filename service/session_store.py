"""Server-side session history (Phase 4 "session continuity").

Per-session JSON files under data/sessions/ — survives service restarts,
so refreshing the sidebar doesn't lose the thread (docs/PHASE_4_SPEC.md).
"Start fresh" = delete_session. Session ids are validated against
config.SESSION_ID_PATTERN before they ever touch the filesystem.

History is capped both in turns and characters: it exists so follow-ups
work without repeating context, not to grow unboundedly.
"""

import json
import re
import threading
from typing import Any

import config

_LOCK = threading.Lock()
_SESSION_ID_RE = re.compile(config.SESSION_ID_PATTERN)


class InvalidSessionId(ValueError):
    """Session id failed validation — never touches disk."""


def validate_session_id(session_id: str) -> str:
    if not session_id or not _SESSION_ID_RE.fullmatch(session_id):
        raise InvalidSessionId(
            "session_id must match [A-Za-z0-9_-]{1,64}"
        )
    return session_id


def _path(session_id: str) -> Any:
    return config.SESSIONS_DIR / f"{validate_session_id(session_id)}.json"


def load_history(session_id: str) -> list[dict[str, str]]:
    """Prior turns as [{'role','content'},...] (may be empty)."""
    path = _path(session_id)
    with _LOCK:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(
                f"Session file for {session_id!r} is unreadable: {exc}"
            ) from exc
    turns = data.get("turns", [])
    # Budget: most recent turns first, then char cap.
    trimmed = turns[-config.SESSION_MAX_TURNS:]
    total = 0
    out: list[dict[str, str]] = []
    for turn in reversed(trimmed):
        total += len(turn.get("content", ""))
        if total > config.SESSION_MAX_CHARS:
            break
        out.append(turn)
    return list(reversed(out))


def append_turn(session_id: str, role: str, content: str) -> int:
    """Append one turn; returns the new turn count."""
    if role not in ("user", "assistant"):
        raise ValueError(f"Invalid history role {role!r}")
    path = _path(session_id)
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {"turns": []}
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(
                f"Session file for {session_id!r} is unreadable: {exc}"
            ) from exc
        turns = data.get("turns", [])
        # Keep the raw store bounded too (prompt budget is applied at read).
        turns = turns[-(config.SESSION_MAX_TURNS * 4):]
        turns.append({"role": role, "content": content})
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"turns": turns}), encoding="utf-8")
        tmp.replace(path)
        return len(turns)


def delete_session(session_id: str) -> bool:
    """'Start fresh': clear visible thread state (resolved-issue knowledge
    in Chroma is untouched — that's permanent knowledge, not session
    state)."""
    path = _path(session_id)
    with _LOCK:
        existed = path.exists()
        if existed:
            path.unlink()
    return existed
