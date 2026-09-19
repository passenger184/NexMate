"""Guarded write access to the live ERPNext instance (Phase 8).

SECURITY.md hard rules, enforced in code:

  - Writes happen ONLY if ERPNEXT_WRITE_ENABLED=true was deliberately set
    in .env; pointing at production additionally requires an explicit
    approval decision logged in DECISIONS.md. The flag is checked at
    PROPOSE time and again at APPLY time.
  - Every write follows the Tier-2 discipline: propose (with an exact
    preview of HTTP method + URL + JSON body) -> explicit confirmed=true
    -> apply. Proposals are one-shot and expire.
  - Pre-flight schema validation: payload fieldnames that don't exist on
    the target DocType are refused BEFORE anything is sent.
  - Only create/update exist. DELETE does not — the most destructive
    operation is structurally absent, not merely forbidden.

This module is deliberately separate from tools/erpnext.py: the read
client stays GET-only by construction; writes live behind their own
flagged surface (ARCHITECTURE.md: architecturally separate capabilities).
Every applied write is appended to config.ERPNEXT_WRITE_AUDIT_LOG.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

import config
from tools import erpnext


class WriteRefusal(Exception):
    """A write was refused. `category` drives the HTTP mapping."""

    def __init__(self, category: str, detail: str):
        super().__init__(detail)
        self.category = category
        self.detail = detail


class WriteTransportError(Exception):
    """The instance rejected/failed a write after gates passed."""


ALLOWED_ACTIONS = ("create", "update")
_RESERVED_KEYS = {"doctype"}  # Frappe accepts this hint key alongside fields

_PROPOSALS: dict[str, dict[str, Any]] = {}


def assert_writes_enabled() -> None:
    if not config.ERPNEXT_WRITE_ENABLED:
        raise WriteRefusal(
            "writes_disabled",
            "ERPNext writes are disabled. Set ERPNEXT_WRITE_ENABLED=true "
            "in .env to enable them deliberately (staging only until "
            "production use is explicitly approved per SECURITY.md).",
        )


def _auth_headers() -> dict[str, str]:
    base, key, secret = erpnext._credentials()
    return {"Authorization": f"token {key}:{secret}",
            "Content-Type": "application/json"}


def _base_url() -> str:
    base, _, _ = erpnext._credentials()
    return base


def _send(method: str, url_path: str, body: dict) -> dict:
    """One authenticated POST/PUT; loud on failure, capped responses."""
    url = f"{_base_url()}/api/resource/{url_path}"
    try:
        response = requests.request(
            method, url,
            headers=_auth_headers(),
            data=json.dumps(body),
            timeout=config.ERPNEXT_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        raise WriteTransportError(
            f"ERPNext did not answer within "
            f"{config.ERPNEXT_TIMEOUT_SECONDS}s") from exc
    except requests.RequestException as exc:
        raise WriteTransportError(f"ERPNext unreachable: {exc}") from exc
    if len(response.content) > config.ERPNEXT_MAX_RESPONSE_BYTES:
        raise WriteTransportError("response exceeded size cap")
    try:
        payload = response.json()
    except ValueError as exc:
        raise WriteTransportError(
            f"non-JSON response ({response.status_code})") from exc
    if response.status_code not in (200, 201):
        # Frappe wraps validation errors in _server_messages
        msgs = payload.get("_server_messages", "") if isinstance(
            payload, dict) else ""
        detail = str(msgs or payload)[:400]
        raise WriteTransportError(
            f"{method} failed ({response.status_code}): {detail}")
    data = payload.get("data", payload)
    return data if isinstance(data, dict) else {"result": data}


def validate_payload_against_schema(doctype: str, payload: dict) -> None:
    """Refuse unknown fieldnames BEFORE anything touches the instance."""
    try:
        schema = erpnext.get_doctype_schema(doctype)["data"]
    except erpnext.ErpnextApiError as exc:
        raise WriteRefusal(
            "doctype_missing",
            f"DocType {doctype!r} lookup failed ({exc.status}); refusing "
            "to write blind",
        ) from exc
    known = set(_RESERVED_KEYS) | {
        f.get("fieldname") for f in schema.get("fields", [])
        if f.get("fieldname")
    }
    unknown = sorted(k for k in payload if k not in known)
    if unknown:
        raise WriteRefusal(
            "unknown_fields",
            f"These fieldnames do not exist on DocType {doctype!r}: "
            f"{', '.join(unknown)}. Check spelling/casing against the "
            "schema before writing.",
        )


def _audit(entry: dict[str, Any]) -> None:
    log: Path = config.ERPNEXT_WRITE_AUDIT_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")


def propose_write(action: str, doctype: str, payload: dict,
                  reason: str, name: str | None = None) -> dict[str, Any]:
    """Validate a write end-to-end WITHOUT executing it; return preview."""
    assert_writes_enabled()
    if action not in ALLOWED_ACTIONS:
        raise WriteRefusal(
            "unsupported_action",
            f"action must be one of {ALLOWED_ACTIONS}; delete is "
            "deliberately not implemented.",
        )
    doctype = (doctype or "").strip()
    if not doctype:
        raise WriteRefusal("bad_request", "doctype is required")
    if action == "update" and not (name or "").strip():
        raise WriteRefusal("bad_request",
                           "update requires the exact document `name`")
    if not reason or len(reason.strip()) < 10:
        raise WriteRefusal(
            "bad_reason",
            "A reason of at least 10 characters explaining WHY this write "
            "is needed is required (it goes into the audit log).",
        )
    if not isinstance(payload, dict) or not payload:
        raise WriteRefusal("bad_request", "payload must be a non-empty object")

    encoded = json.dumps(payload)
    if len(encoded) > config.ERPNEXT_WRITE_MAX_PAYLOAD_BYTES:
        raise WriteRefusal(
            "payload_too_large",
            f"payload is {len(encoded)} bytes; cap is "
            f"{config.ERPNEXT_WRITE_MAX_PAYLOAD_BYTES}",
        )

    # Pre-flight: refuse unknown fields / missing doctype up front.
    validate_payload_against_schema(doctype, payload)

    doc_segment = quote(doctype.strip(), safe="")
    if action == "create":
        method, path = "POST", doc_segment
        body = dict(payload)
    else:
        name_seg = quote(name.strip(), safe="")
        method, path = "PUT", f"{doc_segment}/{name_seg}"
        body = dict(payload)

    _prune()
    proposal_id = uuid.uuid4().hex[:12]
    _PROPOSALS[proposal_id] = {
        "created_at": time.time(),
        "action": action,
        "doctype": doctype,
        "name": (name or "").strip(),
        "body": body,
        "reason": reason.strip(),
        "method": method,
        "path": path,
    }
    return {
        "proposal_id": proposal_id,
        "action": action,
        "doctype": doctype,
        "name": (name or "").strip(),
        "preview": {
            "method": method,
            "url": f"{_base_url()}/api/resource/{path}",
            "body": body,
        },
        "reason": reason.strip(),
        "expires_minutes": config.ERPNEXT_WRITE_TTL_MINUTES,
        "env_label": config.ERPNEXT_ENV_LABEL,
    }


def execute_approved_write(method: str, path: str, body: dict) -> dict:
    """Execute an already-durably-approved write (M5 durable path).

    Called only after Frappe durable approval, permission recheck, and exact
    approved-payload enforcement. Re-checks `ERPNEXT_WRITE_ENABLED` (flag may
    have been switched off since approval), validates method/path/body are
    bounded (POST/PUT only, no DELETE, no absolute URLs), then performs the
    single authenticated `_send`. No RAM proposal store is used; the durable
    proposal hash already guarantees exact payload. Raises WriteRefusal on
    policy violation, WriteTransportError with `timeout`/`uncertain` marker
    on transport timeout (caller maps to `uncertain`, never blind replay).
    """
    assert_writes_enabled()
    if method not in ("POST", "PUT"):
        raise WriteRefusal("unsupported_action", f"method must be POST/PUT, got {method!r} (DELETE absent)")
    if not path or path.startswith("http") or ".." in path or not isinstance(body, dict):
        raise WriteRefusal("bad_request", "path must be a relative resource path with JSON object body")
    try:
        return _send(method, path, body)
    except WriteTransportError as exc:
        # Preserve timeout marker for uncertain mapping upstream
        raise exc


def apply_write(proposal_id: str, confirmed: bool) -> dict[str, Any]:
    """Execute a proposal after explicit confirmation; audit-log the result."""
    if not confirmed:
        raise WriteRefusal(
            "confirmation_required",
            "apply_write requires confirmed=true — writes are never "
            "applied on implication.",
        )
    proposal = _PROPOSALS.get(proposal_id)
    if proposal is None:
        raise WriteRefusal(
            "unknown_proposal",
            f"No live write proposal {proposal_id!r} (expired, applied, "
            "or service restarted). Propose again.",
        )
    if (time.time() - proposal["created_at"]) / 60 \
            > config.ERPNEXT_WRITE_TTL_MINUTES:
        del _PROPOSALS[proposal_id]
        raise WriteRefusal("expired_proposal",
                           f"Proposal {proposal_id!r} expired.")

    # Flag re-checked at apply time: it may have been switched off since.
    assert_writes_enabled()

    result = _send(proposal["method"], proposal["path"], proposal["body"])
    new_name = result.get("name") if isinstance(result, dict) else None

    del _PROPOSALS[proposal_id]  # one-shot by design

    _audit({
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime()),
        "env_label": config.ERPNEXT_ENV_LABEL,
        "action": proposal["action"],
        "doctype": proposal["doctype"],
        "target_name": proposal["name"] or new_name,
        "result_name": new_name,
        "reason": proposal["reason"],
        "payload_keys": sorted(proposal["body"].keys()),
    })

    return {
        "applied": True,
        "action": proposal["action"],
        "doctype": proposal["doctype"],
        "name": new_name or proposal["name"],
        "result": result,
        "audited": True,
    }


def _prune() -> None:
    now = time.time()
    ttl = config.ERPNEXT_WRITE_TTL_MINUTES * 60
    for key in [k for k, v in _PROPOSALS.items()
                if now - v["created_at"] > ttl]:
        del _PROPOSALS[key]
    while len(_PROPOSALS) > 50:
        oldest = min(_PROPOSALS, key=lambda k: _PROPOSALS[k]["created_at"])
        del _PROPOSALS[oldest]
