"""Authoritative capability registry for NexMate.

Single source of truth for what the assistant can actually do. Every
entry is derived from implemented, wired-up functionality — the
"what can you do?" answer and clarification options are rendered from
this list, never from model memory.

To add a future capability: append one dict with the fields below. No
router redesign needed — the orchestrator matches on `route`.
"""

from typing import Any

CAPABILITIES: list[dict[str, Any]] = [
    {
        "id": "docs",
        "label": "ERPNext and Frappe documentation",
        "description": (
            "Answer how-to and concept questions from the official "
            "documentation, with cited sources."
        ),
        "route": "rag",
        "needs_retrieval": True,
        "needs_live_data": False,
        "needs_auth": False,
        "modes": ["developer", "employee"],
        "example": "How do I create a Sales Invoice?",
    },
    {
        "id": "live_data",
        "label": "Live ERPNext data lookups",
        "description": (
            "Look up schemas, documents, lists, and counts on your "
            "connected ERPNext instance."
        ),
        "route": "erpnext",
        "needs_retrieval": False,
        "needs_live_data": True,
        "needs_auth": False,
        "modes": ["developer", "employee"],
        "example": "How many submitted Sales Orders are there?",
    },
    {
        "id": "code",
        "label": "This project's source code",
        "description": (
            "Search and explain this repository's code, including error "
            "diagnosis and a live file listing."
        ),
        "route": "code",
        "needs_retrieval": False,
        "needs_live_data": False,
        "needs_auth": False,
        "modes": ["developer"],
        "example": "Why does resolve_in_project raise on symlinks?",
    },
]


def for_mode(mode: str) -> list[dict[str, Any]]:
    """Capabilities visible to the given user mode."""
    return [c for c in CAPABILITIES if mode in c["modes"]]


def render_capability_answer(mode: str = "developer") -> str:
    """Deterministic capability summary built only from the registry."""
    lines = ["Here's what I can help with:", ""]
    for cap in for_mode(mode):
        lines.append(
            f"- **{cap['label']}** — {cap['description']} "
            f"Try asking: \"{cap['example']}\""
        )
    return "\n".join(lines)


def render_clarification(topic: str | None = None) -> str:
    """Targeted clarification whose options name only real capabilities.

    `topic` is a short noun phrase from the user's message (or None).
    Every option maps to a registry capability, so we never offer what
    the system cannot handle.
    """
    subject = f"“{topic}”" if topic else "that"
    return (
        f"I want to make sure I help with the right thing — {subject} "
        f"could mean a few different things. Are you asking:\n\n"
        f"1. How {subject} works in ERPNext (documentation)?\n"
        f"2. About your live {subject} data on the connected instance "
        f"(lists, statuses, counts)?\n"
        f"3. About {subject} in this project's source code "
        f"(developer mode only)?"
    )


def render_out_of_scope() -> str:
    """Polite scope boundary. Points at real capabilities, claims none."""
    return (
        "That's outside what I can help with — I answer ERPNext and "
        "Frappe questions, look at this project's source code, and check "
        "live data on your connected ERPNext instance. "
        "Try asking something like “How do I create a Sales Invoice?”"
    )
