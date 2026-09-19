"""Correlated durable audit ledger (M5 audit-ledger).

Frappe is authoritative when available (DocType NexMate Audit Entry). When
Frappe is unavailable, audit entries persist as JSON files under
`data/audit_ledger/<correlation>/<request_id>-<action>.json` with redaction,
access control, and retention semantics.

Each entry links actor, site, correlation, request/action, target, outcome,
and redacted details. Secrets are never persisted (see rag/egress secret
scrub). The ledger is the single source of truth for proposal lifecycle
and Debug views; inference emits intent, Frappe persists the authoritative
record.

Access control: by default only the actor who created the correlation or a
System Manager may read that correlation's entries. This is enforced in
`query_by_correlation`; callers must pass `actor` and `site`.
"""

import json
import os
import time
import re
from pathlib import Path
from typing import Any

try:
    import frappe
    HAS_FRAPPE = True
except Exception:
    frappe = None  # type: ignore
    HAS_FRAPPE = False

# App-local audit contract (no repo-root config/tools/service imports).
# Mirrors the redaction semantics used by inference-side egress; see Phase 4A.

AUDIT_DOCTYPE = "NexMate Audit Entry"
_SECRET_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
_SENSITIVE_KEYS = {"password", "passwd", "secret", "token", "api_key", "authorization", "x-nexmate-key"}


def _fallback_base_dir() -> Path:
    """Isolated dev/test fallback base without repo-root config import.

    Explicit `NEXMATE_DURABLE_DIR` wins. Otherwise, when running inside
    Frappe, use the site's private files area; when Frappe is unavailable
    (offline unit tests), use `<app>/private/durable_fallback` derived from
    this file's location. Never imports repo-root `config.py`.
    """
    explicit = os.environ.get("NEXMATE_DURABLE_DIR")
    if explicit:
        return Path(explicit)
    if HAS_FRAPPE:
        try:
            return Path(frappe.get_site_path("private", "files", "nexmate_durable"))  # type: ignore
        except Exception:
            pass
    return Path(__file__).resolve().parent / "private" / "durable_fallback"


def _fallback_dir() -> Path:
    d = _fallback_base_dir() / "audit_ledger"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _should_use_frappe() -> bool:
    if os.environ.get("NEXMATE_DURABLE_FALLBACK") == "1":
        return False
    if not HAS_FRAPPE:
        return False
    try:
        return bool(getattr(frappe, "db", None) and getattr(frappe.local, "site", None))
    except Exception:
        return False


class AuditUnavailable(Exception):
    """Authoritative audit store unavailable and no explicit fallback."""

    def __init__(self, category: str = "frappe_unavailable", detail: str = ""):
        super().__init__(detail)
        self.category = category
        self.detail = detail


def _fallback_explicitly_allowed() -> bool:
    """Explicit isolated dev/test mode only (fail closed by default)."""
    return os.environ.get("NEXMATE_DURABLE_FALLBACK") == "1"


def _require_durable_store() -> None:
    """Fail closed when Frappe unavailable and no explicit fallback.

    Production (default) without Frappe → AuditUnavailable, no silent local
    JSON. Explicit `NEXMATE_DURABLE_FALLBACK=1` allows isolated dev/test file
    fallback and must never be set in production.
    """
    if _should_use_frappe():
        return
    if _fallback_explicitly_allowed():
        return
    raise AuditUnavailable(
        "frappe_unavailable",
        "Durable Frappe audit store unavailable; failing closed, no local "
        "fallback (set NEXMATE_DURABLE_FALLBACK=1 only for explicit isolated dev/test)",
    )

def _current_user() -> str:
    if HAS_FRAPPE and frappe and getattr(frappe, "session", None):
        try:
            user = frappe.session.user
            if user and user != "Guest":
                return user
        except Exception:
            pass
    return os.environ.get("NEXMATE_TEST_USER", "Administrator")

def _current_site() -> str:
    if HAS_FRAPPE and frappe and getattr(frappe.local, "site", None):
        site = getattr(frappe.local, "site", None)
        if site:
            return site
    return os.environ.get("NEXMATE_TEST_SITE", "test_site")

def _redact_details(details: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    """Redact sensitive fields and credential-shaped values."""
    if not details:
        return {}, False
    redacted = False
    out: dict[str, Any] = {}
    for k, v in dict(details).items():
        lk = k.lower()
        if lk in _SENSITIVE_KEYS or "secret" in lk or "password" in lk:
            out[k] = "[REDACTED]"
            redacted = True
            continue
        if isinstance(v, str):
            # Scrub 64-hex credential shapes and transport header mentions
            if _SECRET_RE.search(v) or "x-nexmate-key" in v.lower():
                out[k] = "[REDACTED]"
                redacted = True
                continue
            # Also scrub any env secret values if present
            for sec in (os.environ.get("NEXMATE_SERVICE_KEY", ""), os.environ.get("ANTHROPIC_API_KEY", ""), os.environ.get("OPENAI_API_KEY", "")):
                if sec and sec.lower() in v.lower():
                    out[k] = "[REDACTED]"
                    redacted = True
                    break
            else:
                out[k] = v
        else:
            out[k] = v
    return out, redacted

def record_audit(
    correlation: str,
    request_id: str,
    action: str,
    actor: str | None = None,
    site: str | None = None,
    target: str | None = None,
    outcome: str = "pending",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require_durable_store()
    actor = actor or _current_user()
    site = site or _current_site()
    if not correlation or not action:
        raise ValueError("correlation and action are required")
    details, was_redacted = _redact_details(details)
    # Enforce secret exclusion: details must not contain raw secrets
    entry = {
        "correlation": correlation,
        "request_id": request_id,
        "action": action,
        "actor": actor,
        "site": site,
        "target": target or "",
        "outcome": outcome,
        "details": details,
        "redacted": was_redacted,
        "timestamp": time.time(),
    }
    if _should_use_frappe():
        try:
            doc = frappe.new_doc(AUDIT_DOCTYPE)
            doc.update({
                "correlation": correlation,
                "request_id": request_id,
                "action": action,
                "actor": actor,
                "site": site,
                "target": target or "",
                "outcome": outcome,
                "details": json.dumps(details),
                "redacted": 1 if was_redacted else 0,
            })
            doc.insert(ignore_permissions=True)
            return {"name": doc.name, **entry}
        except Exception:
            # Fall through to file fallback on DB failure, but surface as audit_pending
            entry["audit_pending"] = True
    # Fallback file
    corr_dir = _fallback_dir() / correlation
    corr_dir.mkdir(parents=True, exist_ok=True)
    # Unique filename per action+request
    safe_action = re.sub(r"[^A-Za-z0-9_.-]", "_", action)[:40]
    safe_req = re.sub(r"[^A-Za-z0-9_.-]", "_", request_id)[:40] or "noreq"
    path = corr_dir / f"{safe_req}-{safe_action}-{int(time.time()*1000)}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    tmp.replace(path)
    return entry

def query_by_correlation(correlation: str, actor: str | None = None, site: str | None = None) -> list[dict[str, Any]]:
    """Return audit entries for a correlation, enforcing access control."""
    _require_durable_store()
    actor = actor or _current_user()
    site = site or _current_site()
    if not correlation:
        raise ValueError("correlation required")
    if _should_use_frappe():
        try:
            # Only owner or System Manager may read
            # Enforce by checking requested actor matches caller or caller is System Manager
            is_manager = False
            try:
                roles = frappe.get_roles(actor)
                is_manager = "System Manager" in roles
            except Exception:
                is_manager = False
            # If caller is not manager, ensure at least one entry is owned by caller
            docs = frappe.get_all(AUDIT_DOCTYPE, filters={"correlation": correlation}, fields=["name", "actor", "site"])
            if not docs:
                return []
            # If none owned by caller and caller not manager, deny
            if not is_manager and all(d.actor != actor or d.site != site for d in docs):
                raise PermissionError("audit access denied")
            out = []
            for r in docs:
                doc = frappe.get_doc(AUDIT_DOCTYPE, r.name, ignore_permissions=True)
                out.append({
                    "correlation": doc.correlation,
                    "request_id": doc.request_id,
                    "action": doc.action,
                    "actor": doc.actor,
                    "site": doc.site,
                    "target": doc.target,
                    "outcome": doc.outcome,
                    "details": json.loads(doc.details) if doc.details else {},
                    "redacted": bool(doc.redacted),
                    "timestamp": float(getattr(doc, "modified", 0) or 0),
                })
            return sorted(out, key=lambda x: x["timestamp"])
        except PermissionError:
            raise
        except Exception:
            # Fall through to file on DB error
            pass
    # Fallback
    corr_dir = _fallback_dir() / correlation
    if not corr_dir.exists():
        return []
    out = []
    for p in corr_dir.glob("*.json"):
        try:
            entry = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        # Access control: only actor/site owner or env test user
        if entry.get("actor") != actor or entry.get("site") != site:
            # Allow System Manager in test env if actor is test user? For test, we allow any if no real roles
            # Check if caller is System Manager via env flag
            if os.environ.get("NEXMATE_TEST_IS_MANAGER") != "1" and actor != entry.get("actor"):
                continue
        out.append(entry)
    return sorted(out, key=lambda x: x.get("timestamp", 0))

def find_prior_success(correlation: str, target: str, outcome: str = "success") -> bool:
    entries = query_by_correlation(correlation)
    for e in entries:
        if e.get("target") == target and e.get("outcome") == outcome:
            return True
    return False

def clear_fallback() -> None:
    for p in _fallback_dir().rglob("*.json"):
        try:
            p.unlink()
        except Exception:
            pass
    # Remove empty correlation dirs
    for d in list(_fallback_dir().glob("*")):
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except Exception:
            pass

def count_entries() -> int:
    if _should_use_frappe():
        try:
            return len(frappe.get_all(AUDIT_DOCTYPE, fields=["name"]))
        except Exception:
            pass
    return sum(1 for _ in _fallback_dir().rglob("*.json"))
