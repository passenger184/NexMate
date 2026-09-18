"""Frappe-side owned-conversation helpers (frappe-owned-conversation-state).

Frappe is authoritative for authenticated user identity, current site, and
conversation ownership. Every document helper below enforces owner+site
explicitly; privileged Frappe roles cannot bypass these checks — NexMate
API authorization is separate from administrative DocType access.

``bounded_tail`` is pure (no Frappe) so budget behavior is unit-testable in
isolation. Budgets mirror the inference prompt constants
(``SESSION_MAX_TURNS``/``SESSION_MAX_CHARS``): the forward tail matches what
inference accepts, storage keeps headroom so trimming never destroys the
forward window.
"""

import re

import frappe

CONVERSATION_DOCTYPE = "NexMate Conversation"
# Conservative on purpose: the gateway only ever handles identifiers it
# minted (autoname NM-#####), and the same pattern gates the inference
# side, so neither side can smuggle separator/whitespace tricks.
CONVERSATION_ID_PATTERN = r"[A-Za-z0-9_.~@-]{1,140}"

FORWARD_MAX_TURNS = 6
FORWARD_MAX_CHARS = 6000
STORE_MAX_TURNS = 24
STORE_MAX_CHARS = 24000

_VALID_ROLES = ("user", "assistant")


class ConversationError(Exception):
    """Base for safe, throw-ready conversation failures (no secrets inside)."""


class UnknownConversation(ConversationError):
    """Identifier malformed or names no record."""


class NotOwnedConversation(ConversationError):
    """Record exists but is owned by someone else or bound to another site."""


class ConversationBusy(ConversationError):
    """A conflicting concurrent mutation holds the document lock; retry."""


def valid_conversation_id(value: object) -> bool:
    return (isinstance(value, str)
            and re.fullmatch(CONVERSATION_ID_PATTERN, value) is not None)


def bounded_tail(turns: object, max_turns: int = FORWARD_MAX_TURNS,
                 max_chars: int = FORWARD_MAX_CHARS) -> list[dict[str, str]]:
    """Most-recent-wins truncation to budget; pure function (no Frappe).

    Always keeps the newest turn even if it alone exceeds the budget, so a
    single long message can never erase the thread it belongs to.
    """
    if not isinstance(turns, list):
        return []
    kept: list[dict[str, str]] = []
    total = 0
    for turn in reversed(turns[-max_turns:]):
        content = turn.get("content", "") if isinstance(turn, dict) else ""
        if not isinstance(content, str):
            content = ""
        if kept:
            if total + len(content) > max_chars:
                break
            total += len(content)
        else:
            total += len(content)
        kept.append({"role": turn.get("role"), "content": content})
    return list(reversed(kept))


def _current_user() -> str:
    return frappe.session.user


def _current_site() -> str:
    return getattr(frappe.local, "site", None)


def get_owned_doc(name: str):
    """Owner+site checked fetch (no lock). Raises Unknown/NotOwned."""
    if not valid_conversation_id(name):
        raise UnknownConversation("Unknown conversation.")
    try:
        doc = frappe.get_doc(CONVERSATION_DOCTYPE, name, ignore_permissions=True)
    except frappe.DoesNotExistError:
        raise UnknownConversation("Unknown conversation.") from None
    if (getattr(doc, "owner_user", None) != _current_user()
            or getattr(doc, "site", None) != _current_site()):
        raise NotOwnedConversation("Conversation is not owned by this user on this site.")
    return doc


def locked_doc(name: str):
    """Serialize mutations: row-lock the conversation, then owned-fetch.

    Runs inside the request transaction, so concurrent appends queue on the
    database lock instead of interleaving. Lock failures surface as
    ConversationBusy (loud, retryable) — persisted turns are never silently
    overwritten.
    """
    if not valid_conversation_id(name):
        raise UnknownConversation("Unknown conversation.")
    try:
        frappe.db.sql(
            "SELECT `name` FROM `tabNexMate Conversation` WHERE `name`=%s FOR UPDATE",
            (name,),
        )
    except Exception as exc:
        raise ConversationBusy(
            "Conversation is busy; please retry.") from exc
    return get_owned_doc(name)


def start_conversation(user: str, site: str, mode: str) -> str:
    """Create an owned thread; returns its document name."""
    doc = frappe.new_doc(CONVERSATION_DOCTYPE)
    doc.update({"owner_user": user, "site": site, "persona": mode})
    doc.insert(ignore_permissions=True)
    return doc.name


def read_turns(name: str) -> list[dict[str, str]]:
    """Owner-checked read of the full stored thread (oldest first)."""
    doc = get_owned_doc(name)
    return [{"role": getattr(row, "role", None),
             "content": getattr(row, "content", "") or ""}
            for row in (doc.get("turns") or [])]


def append_turn(name: str, role: str, content: str) -> list[dict[str, str]]:
    """Locked append with storage-budget trim; returns the forward tail."""
    if role not in _VALID_ROLES:
        raise ValueError(f"Invalid history role {role!r}")
    if not isinstance(content, str) or not content:
        raise ValueError("Turn content must be a nonempty string")
    doc = locked_doc(name)
    stored = [{"role": getattr(row, "role", None),
               "content": getattr(row, "content", "") or ""}
              for row in (doc.get("turns") or [])]
    stored.append({"role": role, "content": content})
    trimmed = bounded_tail(stored, STORE_MAX_TURNS, STORE_MAX_CHARS)
    doc.set("turns", [])
    for turn in trimmed:
        doc.append("turns", turn)
    doc.save(ignore_permissions=True)
    return bounded_tail(trimmed)


def reset_conversation(name: str) -> bool:
    """Owner-checked server-side deletion of the thread."""
    doc = locked_doc(name)
    frappe.delete_doc(CONVERSATION_DOCTYPE, doc.name, ignore_permissions=True)
    return True
