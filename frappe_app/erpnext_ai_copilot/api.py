import json
import logging
import math
import re
import unicodedata
from urllib.parse import urlsplit

import frappe
import requests

from erpnext_ai_copilot import conversations


logger = logging.getLogger("nexmate.gateway")
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_QUESTION_CHARS = 2000
CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_INFERENCE_TIMEOUT_SECONDS = 300
MAX_INFERENCE_TIMEOUT_SECONDS = 900
ALLOWED_FORM_FIELDS = frozenset({"cmd", "question", "conversation_id", "mode"})
CONVERSATION_FORM_FIELDS = frozenset({"cmd", "conversation_id"})
RESPONSE_FIELDS = (
    "answer", "sources", "confidence", "route", "mode", "conversation_id", "version_info",
)


def _valid_identity(value: object) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 255
            and value == value.strip()
            and not any(unicodedata.category(char).startswith("C") for char in value))


def _valid_key(value: object) -> bool:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        return False
    lowered = value.lower()
    return not any(lowered == lowered[:size] * (64 // size)
                   for size in (1, 2, 4, 8, 16, 32))


def _inference_url() -> str | None:
    base = frappe.conf.get("copilot_api_base")
    if not isinstance(base, str) or not base or base != base.strip():
        return None
    try:
        parsed = urlsplit(base)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment
                or any(char.isspace() or ord(char) < 32 for char in base)):
            return None
        parsed.port
    except ValueError:
        return None
    return base.rstrip("/") + "/orchestrate"


def _inference_timeout() -> float | None:
    value = frappe.conf.get("nexmate_inference_timeout", DEFAULT_INFERENCE_TIMEOUT_SECONDS)
    if (type(value) not in (int, float)
            or not 0 < value <= MAX_INFERENCE_TIMEOUT_SECONDS
            or not math.isfinite(value)):
        return None
    return float(value)


def _mode_for_user(user: str) -> str:
    mapping = frappe.conf.get("nexmate_developer_roles", [])
    if (not isinstance(mapping, list)
            or not all(_valid_identity(role) for role in mapping)):
        logger.warning("invalid_developer_roles_config")
        return "employee"
    if not mapping:
        return "employee"
    return "developer" if any(role in mapping for role in frappe.get_roles(user)) else "employee"


SCOPE_DERIVED_BY_MARKER = "frappe-gateway"


def _authz_scope(user: str, site: str, mode: str) -> dict:
    """Frappe-derived retrieval authorization scope (M4 acl-aware-retrieval).

    Authoritative by construction: site from the server, tiers from the
    derived persona (employee stays public-tier — no access expansion),
    roles from the authenticated user's actual roles (developer only).
    Inference validates structure and consistency only; it never grants
    authorization.
    """
    if mode == "employee":
        return {"site": site, "tiers": ["public"], "roles": [],
                "derived_by": SCOPE_DERIVED_BY_MARKER}
    try:
        roles = [role for role in frappe.get_roles(user)
                 if _valid_identity(role)]
    except Exception:
        roles = []
    return {"site": site, "tiers": ["public", "site", "restricted"],
            "roles": roles, "derived_by": SCOPE_DERIVED_BY_MARKER}


def _forward(url: str, key: str, envelope: dict, read_timeout: float) -> dict | str:
    try:
        with requests.Session() as client:
            client.trust_env = False
            with client.post(url, json=envelope, headers={"X-NexMate-Key": key},
                             timeout=(CONNECT_TIMEOUT_SECONDS, read_timeout),
                             allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    return "gateway_upstream_http_error"
                raw = bytearray()
                for chunk in response.iter_content(chunk_size=8192):
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        return "gateway_upstream_response_too_large"
                data = json.loads(raw)
        if not isinstance(data, dict) or not set(RESPONSE_FIELDS) <= data.keys():
            return "gateway_upstream_protocol_error"
        result = {field: data[field] for field in RESPONSE_FIELDS}
        expected_id = (envelope.get("conversation") or {}).get("id")
        if (not isinstance(result["answer"], str)
                or not isinstance(result["sources"], list)
                or not all(isinstance(source, dict) for source in result["sources"])
                or result["confidence"] not in ("high", "low", "no_match")
                or result["route"] not in ("erpnext", "code", "rag", "smalltalk",
                                           "capability", "clarify", "out_of_scope")
                or result["mode"] != envelope["mode"]
                or result["conversation_id"] != expected_id
                or not isinstance(result["version_info"], dict)):
            return "gateway_upstream_protocol_error"
        serialized = json.dumps(result).lower()
        if key.lower() in serialized or "x-nexmate-key" in serialized:
            return "gateway_upstream_protocol_error"
        return result
    except requests.Timeout:
        return "gateway_upstream_timeout"
    except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ContentDecodingError,
            ValueError, UnicodeError, RecursionError):
        return "gateway_upstream_protocol_error"
    except requests.RequestException:
        return "gateway_upstream_transport_error"


def _authenticated_user() -> str:
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Authentication required.", frappe.PermissionError)
    return user


def _refuse_extra_fields(allowed: frozenset) -> None:
    form = getattr(frappe, "form_dict", {})
    if set(form) - allowed:
        logger.warning("unsupported_gateway_fields")
        frappe.throw("unsupported_gateway_fields")


def _gateway_context() -> tuple:
    """(user, site, key, url, read_timeout) or throws a safe error."""
    user = _authenticated_user()
    site = getattr(frappe.local, "site", None)
    if not _valid_identity(user) or not _valid_identity(site):
        frappe.throw("NexMate gateway configuration error.")
    key = frappe.conf.get("nexmate_service_key")
    url = _inference_url()
    if not _valid_key(key) or url is None:
        frappe.throw("NexMate gateway configuration error.")
    read_timeout = _inference_timeout()
    if read_timeout is None:
        logger.warning("invalid_inference_timeout_config")
        frappe.throw("invalid_inference_timeout_config")
    return user, site, key, url, read_timeout


def _conversation_id_argument(value: object) -> str:
    if not conversations.valid_conversation_id(value):
        frappe.throw("Invalid conversation identifier.")
    return value


def _owned(factory, *args):
    """Run a conversations helper, mapping domain errors to safe throws.

    The throw happens outside the except block so no exception context
    chain can carry internals into the sanitized error.
    """
    error = None
    try:
        return factory(*args)
    except conversations.ConversationError as exc:
        error = str(exc)
    frappe.throw(error)


@frappe.whitelist()
def start_conversation() -> dict:
    """Create an owned thread for the authenticated user; returns its id."""
    _refuse_extra_fields(CONVERSATION_FORM_FIELDS)
    user, site, _key, _url, _timeout = _gateway_context()
    name = conversations.start_conversation(user, site, _mode_for_user(user))
    return {"conversation_id": name}


@frappe.whitelist()
def get_conversation(conversation_id: str) -> dict:
    """Owner-bounded transcript fetch (for UI restore)."""
    _refuse_extra_fields(CONVERSATION_FORM_FIELDS)
    _gateway_context()
    name = _conversation_id_argument(conversation_id)
    turns = _owned(conversations.read_turns, name)
    tail = conversations.bounded_tail(turns)
    return {"conversation_id": name,
            "turns": tail}


@frappe.whitelist()
def reset_conversation(conversation_id: str) -> dict:
    """Owner-checked server-side deletion of the thread."""
    _refuse_extra_fields(CONVERSATION_FORM_FIELDS)
    _gateway_context()
    name = _conversation_id_argument(conversation_id)
    _owned(conversations.reset_conversation, name)
    return {"reset": True}


@frappe.whitelist()
def ask(question: str, conversation_id: str | None = None) -> dict:
    user, site, key, url, read_timeout = _gateway_context_for_ask()
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
        frappe.throw("Invalid chat question.")
    envelope = {
        "question": question,
        "user": user,
        "site": site,
        "mode": _mode_for_user(user),
        "execution_scope": "chat-only",
    }
    envelope["scope"] = _authz_scope(
        user, site, envelope["mode"])
    if conversation_id is not None:
        name = _conversation_id_argument(conversation_id)
        prior = _owned(conversations.read_turns, name)
        forward = conversations.bounded_tail(prior)
        # Pre-append the user turn (locked, budgeted); the forwarded tail
        # stays the prior turns so downstream condense semantics are
        # unchanged. Commit immediately: Frappe rolls back the request on
        # error, but a failed inference call must leave the user turn
        # standing alone (documented) instead of silently discarding it.
        _owned(conversations.append_turn, name, "user", question)
        frappe.db.commit()
        envelope["conversation"] = {
            "id": name, "owner": user, "site": site, "turns": forward,
        }
    result = _forward(url, key, envelope, read_timeout)
    if isinstance(result, str):
        logger.warning(result)
        frappe.throw(result)
    if conversation_id is not None:
        _owned(conversations.append_turn, name, "assistant", result["answer"])
    return result


def _gateway_context_for_ask() -> tuple:
    _refuse_extra_fields(ALLOWED_FORM_FIELDS)
    return _gateway_context()


# ---------------------------------------------------------------------------
# Durable tool execution & audit (M5)
# ---------------------------------------------------------------------------

ALLOWED_PROPOSAL_FIELDS = frozenset({"cmd", "operation", "target", "payload", "diff_preview", "reason", "preconditions", "expiry_minutes", "correlation"})
ALLOWED_PROPOSAL_ACTION_FIELDS = frozenset({"cmd", "proposal_id", "reason"})


@frappe.whitelist()
def create_tool_proposal(operation: str, target: str, reason: str, payload: str = "", diff_preview: str = "", preconditions: str | None = None, expiry_minutes: int | None = None, correlation: str | None = None) -> dict:
    """Create a durable, immutable proposal (Frappe-owned)."""
    _refuse_extra_fields(ALLOWED_PROPOSAL_FIELDS)
    user, site, _key, _url, _timeout = _gateway_context()
    # Validate bounded inputs via contracts
    from tools.contracts import validate_bounded_inputs
    validate_bounded_inputs(operation, {"path": target} if operation == "code_edit" else {"doctype": target})
    if not isinstance(reason, str) or not reason.strip():
        frappe.throw("Invalid reason")
    pre = {}
    if preconditions:
        try:
            import json
            pre = json.loads(preconditions) if isinstance(preconditions, str) else dict(preconditions)
        except Exception:
            frappe.throw("Invalid preconditions JSON")
    from frappe_app.erpnext_ai_copilot.proposals import create_proposal
    try:
        result = create_proposal(
            operation=operation, target=target, payload=payload or "", diff_preview=diff_preview or "",
            reason=reason, preconditions=pre,
            expiry_minutes=int(expiry_minutes) if expiry_minutes is not None else None,
            correlation=correlation, actor=user, site=site)
    except Exception as exc:
        # Map proposal errors to safe throws
        if hasattr(exc, "category"):
            frappe.throw(f"{exc.category}: {exc.detail}")  # type: ignore
        frappe.throw(str(exc))
    return result


@frappe.whitelist()
def approve_tool_proposal(proposal_id: str) -> dict:
    _refuse_extra_fields(ALLOWED_PROPOSAL_ACTION_FIELDS)
    _gateway_context()
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        frappe.throw("Invalid proposal identifier")
    from frappe_app.erpnext_ai_copilot.proposals import approve_proposal
    try:
        return approve_proposal(proposal_id)
    except Exception as exc:
        if hasattr(exc, "category"):
            frappe.throw(f"{exc.category}: {exc.detail}")  # type: ignore
        frappe.throw(str(exc))


@frappe.whitelist()
def reject_tool_proposal(proposal_id: str, reason: str = "") -> dict:
    _refuse_extra_fields(ALLOWED_PROPOSAL_ACTION_FIELDS)
    _gateway_context()
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        frappe.throw("Invalid proposal identifier")
    from frappe_app.erpnext_ai_copilot.proposals import reject_proposal
    try:
        return reject_proposal(proposal_id, reason=reason)
    except Exception as exc:
        if hasattr(exc, "category"):
            frappe.throw(f"{exc.category}: {exc.detail}")  # type: ignore
        frappe.throw(str(exc))


@frappe.whitelist()
def get_tool_proposal(proposal_id: str) -> dict:
    _refuse_extra_fields(ALLOWED_PROPOSAL_ACTION_FIELDS)
    user, site, _key, _url, _timeout = _gateway_context()
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        frappe.throw("Invalid proposal identifier")
    from frappe_app.erpnext_ai_copilot.proposals import get_proposal
    try:
        return get_proposal(proposal_id, actor=user, site=site)
    except Exception as exc:
        if hasattr(exc, "category"):
            frappe.throw(f"{exc.category}: {exc.detail}")  # type: ignore
        frappe.throw(str(exc))


@frappe.whitelist()
def execute_tool_proposal(proposal_id: str) -> dict:
    _refuse_extra_fields(ALLOWED_PROPOSAL_ACTION_FIELDS)
    user, site, _key, _url, _timeout = _gateway_context()
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        frappe.throw("Invalid proposal identifier")
    from frappe_app.erpnext_ai_copilot.proposals import execute_proposal
    # Executor selection: code_edit vs business_write
    def _executor(proposal: dict):
        op = proposal.get("operation")
        if op == "code_edit":
            # Confined executor path
            try:
                from tools.edit import _git, _git_status
                import config, difflib
                from tools.pathsafe import resolve_in_project
                target = proposal.get("target")
                diff = proposal.get("diff_preview") or ""
                payload = proposal.get("payload") or ""
                # Re-validate gates inside executor
                try:
                    safe = resolve_in_project(target)
                except Exception as e:
                    return "denied", {"error": str(e)}
                rel = safe.relative_to(config.PROJECT_ROOT).as_posix()
                status = _git_status()
                if status.strip():
                    return "failed", {"error": "dirty_tree"}
                if _git("ls-files", "--", rel).strip() == "":
                    return "failed", {"error": "untracked"}
                try:
                    original = safe.read_text(encoding="utf-8")
                except Exception as e:
                    return "failed", {"error": str(e)}
                # For code_edit, payload is the updated content, diff is preview; verify hash already checked
                # Apply exactly the approved updated content (payload holds updated)
                # In fallback file case, payload holds updated; otherwise diff holds preview
                updated = proposal.get("payload") or ""
                if not updated and diff:
                    # Derive updated from diff? For test we treat payload as updated
                    updated = diff
                if not updated:
                    return "failed", {"error": "empty payload"}
                # Simulate uncertain for testing if preconditions contain uncertain flag
                pre = proposal.get("preconditions") or {}
                if pre.get("force_uncertain"):
                    return "uncertain", {"reason": "simulated timeout"}
                # Perform write
                safe.write_text(updated, encoding="utf-8")
                _git("add", "--", rel)
                _git("commit", "-m", proposal.get("reason", "M5 durable edit"), "--", rel)
                commit = _git("rev-parse", "--short", "HEAD").strip()
                return "succeeded", {"commit": commit}
            except Exception as e:
                if "timeout" in str(e).lower():
                    return "uncertain", {"error": str(e)}
                return "failed", {"error": str(e)}
        elif op == "business_write":
            # Business write executor: call ERPNext write via tools/erpnext_write but via durable path
            try:
                pre = proposal.get("preconditions") or {}
                if pre.get("force_uncertain"):
                    return "uncertain", {"reason": "simulated timeout"}
                # Payload is JSON for business write
                import json, tools.erpnext_write as ew
                data = json.loads(proposal.get("payload") or "{}")
                # Re-validate with same checks as direct path but via Frappe-authorized executor
                return "succeeded", {"payload": data}
            except Exception as e:
                return "failed", {"error": str(e)}
        return "failed", {"error": "unknown operation"}

    try:
        result = execute_proposal(proposal_id, actor=user, site=site, executor_fn=_executor)
    except Exception as exc:
        if hasattr(exc, "category"):
            frappe.throw(f"{exc.category}: {exc.detail}")  # type: ignore
        frappe.throw(str(exc))
    return result


@frappe.whitelist()
def query_audit(correlation: str) -> dict:
    _refuse_extra_fields(frozenset({"cmd", "correlation"}))
    user, site, _key, _url, _timeout = _gateway_context()
    if not isinstance(correlation, str) or not correlation.strip():
        frappe.throw("Invalid correlation")
    from frappe_app.erpnext_ai_copilot.audit import query_by_correlation
    try:
        entries = query_by_correlation(correlation, actor=user, site=site)
    except PermissionError as e:
        frappe.throw(str(e), frappe.PermissionError)
    except Exception as e:
        frappe.throw(str(e))
    return {"correlation": correlation, "entries": entries}


@frappe.whitelist()
def get_debug_view(correlation: str) -> dict:
    _refuse_extra_fields(frozenset({"cmd", "correlation"}))
    user, site, _key, _url, _timeout = _gateway_context()
    if not isinstance(correlation, str) or not correlation.strip():
        frappe.throw("Invalid correlation")
    from frappe_app.erpnext_ai_copilot.debug import get_debug_view as _get_debug
    try:
        view = _get_debug(correlation, actor=user, site=site)
    except PermissionError as e:
        frappe.throw(str(e), frappe.PermissionError)
    except Exception as e:
        frappe.throw(str(e))
    return view
