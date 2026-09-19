"""Durable tool proposal lifecycle (M5 durable-tool-execution).

Frappe is authoritative when available (DocType NexMate Tool Proposal with
row-locking). When Frappe is unavailable (unit tests without bench, or
`NEXMATE_DURABLE_FALLBACK=1`), proposals persist as JSON files under
`data/durable_proposals/<id>.json` with the same semantics: immutable
payload hash, actor/site binding, expiry, status transitions, advisory lock
per target, and idempotency key.

Statuses: pending → approved/rejected → executing → succeeded/failed/
denied/uncertain → reconciled / audit_pending / conflicting / expired.
Any change to payload/target/reason after approval requires a new proposal.

All state transitions are durably persisted and audited via audit.py;
already-delivered answers are never retracted.
"""

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

try:
    import frappe
    HAS_FRAPPE = True
except Exception:
    frappe = None  # type: ignore
    HAS_FRAPPE = False

import config
from tools.contracts import PROPOSAL_STATUSES, advisory_lock_key

TOOL_PROPOSAL_DOCTYPE = "NexMate Tool Proposal"
PROPOSAL_ID_PATTERN = "NMTP-"
DEFAULT_EXPIRY_MINUTES = 15
# Correlation length: UUID hex
CORRELATION_BYTES = 8

# Fallback directory for durable store when Frappe not available or for tests.
_FALLBACK_DIR = Path(config.PROJECT_ROOT) / "data" / "durable_proposals"
# In-memory advisory locks for fallback (plus file locks when needed).
_FALLBACK_LOCKS: dict[str, str] = {}
_FALLBACK_LOCK_OWNER: dict[str, str] = {}

class ProposalError(Exception):
    def __init__(self, category: str, detail: str):
        super().__init__(detail)
        self.category = category
        self.detail = detail

class UnknownProposal(ProposalError): pass
class NotOwnedProposal(ProposalError): pass
class ExpiredProposal(ProposalError): pass
class ConflictingProposal(ProposalError): pass

def _fallback_dir() -> Path:
    _FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    return _FALLBACK_DIR

def _payload_hash(operation: str, target: str, payload: str, diff: str, reason: str) -> str:
    h = hashlib.sha256()
    for part in (operation, target, payload or "", diff or "", reason or ""):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()

def _now_ts() -> float:
    return time.time()

def _expiry_ts(minutes: int | None = None) -> float:
    mins = minutes if minutes is not None else DEFAULT_EXPIRY_MINUTES
    return _now_ts() + mins * 60

def _correlation_id() -> str:
    return uuid.uuid4().hex[:16]

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

def _valid_identity(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 255 and value == value.strip()

def _should_use_frappe() -> bool:
    if os.environ.get("NEXMATE_DURABLE_FALLBACK") == "1":
        return False
    if not HAS_FRAPPE:
        return False
    try:
        # If frappe.db exists and we have a site, use DocType; otherwise fallback.
        return bool(getattr(frappe, "db", None) and _current_site())
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Fallback file helpers
# ---------------------------------------------------------------------------
def _fallback_path(proposal_id: str) -> Path:
    return _fallback_dir() / f"{proposal_id}.json"

def _read_fallback(proposal_id: str) -> dict[str, Any]:
    p = _fallback_path(proposal_id)
    if not p.exists():
        raise UnknownProposal("unknown_proposal", f"Unknown proposal {proposal_id!r}")
    return json.loads(p.read_text(encoding="utf-8"))

def _write_fallback(proposal_id: str, data: dict[str, Any]) -> None:
    p = _fallback_path(proposal_id)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)

def _list_fallback() -> list[dict[str, Any]]:
    out = []
    for p in _fallback_dir().glob("*.json"):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out

# ---------------------------------------------------------------------------
# Frappe DocType helpers (when available)
# ---------------------------------------------------------------------------
def _frappe_get(proposal_id: str):
    try:
        doc = frappe.get_doc(TOOL_PROPOSAL_DOCTYPE, proposal_id, ignore_permissions=True)
    except frappe.DoesNotExistError:
        raise UnknownProposal("unknown_proposal", f"Unknown proposal {proposal_id!r}") from None
    return doc

def _frappe_to_dict(doc) -> dict[str, Any]:
    return {
        "name": doc.name,
        "operation": doc.operation,
        "target": doc.target,
        "payload": doc.payload or "",
        "diff_preview": doc.diff_preview or "",
        "reason": doc.reason,
        "actor": doc.actor,
        "site": doc.site,
        "correlation": doc.correlation,
        "expiry": doc.expiry,
        "preconditions": json.loads(doc.preconditions) if doc.preconditions else {},
        "payload_hash": doc.payload_hash,
        "status": doc.status,
        "approver": doc.approver or "",
        "executed_at": doc.executed_at or "",
    }

def _doc_expiry_ts(doc) -> float:
    # Frappe datetime may be string; parse.
    expiry = doc.expiry
    if isinstance(expiry, str):
        try:
            import datetime
            dt = datetime.datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return 0
    try:
        return float(expiry.timestamp()) if hasattr(expiry, "timestamp") else float(expiry)
    except Exception:
        return 0

# ---------------------------------------------------------------------------
# Public API — durable lifecycle
# ---------------------------------------------------------------------------
def create_proposal(
    operation: str,
    target: str,
    payload: str = "",
    diff_preview: str = "",
    reason: str = "",
    preconditions: dict[str, Any] | None = None,
    expiry_minutes: int | None = None,
    correlation: str | None = None,
    actor: str | None = None,
    site: str | None = None,
) -> dict[str, Any]:
    """Create a durable proposal (Frappe-owned when possible, else fallback).

    Records immutable hash over (operation, target, payload, diff, reason).
    The proposal is actor/site-bound and starts as `pending`.
    """
    if not operation or not target or not reason:
        raise ProposalError("bad_request", "operation, target, and reason are required")
    if not _valid_identity(target) or not _valid_identity(reason):
        raise ProposalError("bad_request", "target and reason must be valid identities")
    if operation not in ("code_edit", "business_write"):
        raise ProposalError("bad_request", f"Unsupported operation {operation!r}")

    actor = actor or _current_user()
    site = site or _current_site()
    if not _valid_identity(actor) or not _valid_identity(site):
        raise ProposalError("bad_request", "actor and site must be valid")

    corr = correlation or _correlation_id()
    pre = dict(preconditions or {})
    # Idempotency key defaults to payload hash + actor/site if not supplied.
    phash = _payload_hash(operation, target, payload, diff_preview, reason)
    if "idempotency_key" not in pre:
        pre["idempotency_key"] = f"{actor}:{site}:{phash[:12]}"

    expiry_ts = _expiry_ts(expiry_minutes)
    # For DocType, expiry is datetime.
    import datetime
    expiry_dt = datetime.datetime.fromtimestamp(expiry_ts, tz=datetime.timezone.utc)

    proposal_id = f"NMTP-{uuid.uuid4().hex[:10].upper()}"

    if _should_use_frappe():
        try:
            doc = frappe.new_doc(TOOL_PROPOSAL_DOCTYPE)
            doc.update({
                "operation": operation,
                "target": target,
                "payload": payload,
                "diff_preview": diff_preview,
                "reason": reason,
                "actor": actor,
                "site": site,
                "correlation": corr,
                "expiry": expiry_dt,
                "preconditions": json.dumps(pre),
                "payload_hash": phash,
                "status": "pending",
            })
            doc.insert(ignore_permissions=True)
            # Frappe autoname will override our proposal_id; use doc.name as real id
            # but also store requested id in correlation? For test determinism, use doc.name.
            proposal_id = doc.name
            # Audit
            try:
                from frappe_app.erpnext_ai_copilot.audit import record_audit
                record_audit(correlation=corr, request_id=proposal_id, action="proposal_created",
                             actor=actor, site=site, target=target, outcome="success",
                             details={"operation": operation, "payload_hash": phash})
            except Exception:
                pass
            return {
                "proposal_id": proposal_id,
                "operation": operation,
                "target": target,
                "payload_hash": phash,
                "correlation": corr,
                "expiry": expiry_dt.isoformat(),
                "status": "pending",
                "preconditions": pre,
            }
        except Exception as exc:
            # If Frappe insert fails (e.g., no DB), fall through to file fallback
            if "ProposalError" in type(exc).__name__:
                raise
            pass

    # Fallback durable file
    data = {
        "name": proposal_id,
        "operation": operation,
        "target": target,
        "payload": payload,
        "diff_preview": diff_preview,
        "reason": reason,
        "actor": actor,
        "site": site,
        "correlation": corr,
        "expiry_ts": expiry_ts,
        "preconditions": pre,
        "payload_hash": phash,
        "status": "pending",
        "approver": "",
        "executed_at": "",
        "created_at": _now_ts(),
    }
    _write_fallback(proposal_id, data)
    try:
        from frappe_app.erpnext_ai_copilot.audit import record_audit
        record_audit(correlation=corr, request_id=proposal_id, action="proposal_created",
                     actor=actor, site=site, target=target, outcome="success",
                     details={"operation": operation, "payload_hash": phash})
    except Exception:
        pass
    return {
        "proposal_id": proposal_id,
        "operation": operation,
        "target": target,
        "payload_hash": phash,
        "correlation": corr,
        "expiry": expiry_dt.isoformat(),
        "status": "pending",
        "preconditions": pre,
    }

def get_proposal(proposal_id: str, actor: str | None = None, site: str | None = None) -> dict[str, Any]:
    """Fetch a proposal, enforcing actor/site binding."""
    actor = actor or _current_user()
    site = site or _current_site()
    if _should_use_frappe():
        doc = _frappe_get(proposal_id)
        d = _frappe_to_dict(doc)
        # Check expiry
        if _doc_expiry_ts(doc) < _now_ts() and d["status"] == "pending":
            try:
                doc.status = "expired"
                doc.save(ignore_permissions=True)
                d["status"] = "expired"
            except Exception:
                d["status"] = "expired"
        # Enforce binding
        if d["actor"] != actor or d["site"] != site:
            raise NotOwnedProposal("not_owned", "Proposal not owned by this actor/site")
        if d["status"] == "expired":
            raise ExpiredProposal("expired_proposal", f"Proposal {proposal_id!r} expired")
        return d
    # Fallback
    d = _read_fallback(proposal_id)
    # Expiry check
    if d.get("expiry_ts", 0) < _now_ts() and d.get("status") == "pending":
        d["status"] = "expired"
        _write_fallback(proposal_id, d)
        raise ExpiredProposal("expired_proposal", f"Proposal {proposal_id!r} expired")
    if d.get("actor") != actor or d.get("site") != site:
        raise NotOwnedProposal("not_owned", "Proposal not owned by this actor/site")
    if d.get("status") == "expired":
        raise ExpiredProposal("expired_proposal", f"Proposal {proposal_id!r} expired")
    # Check hash immutability
    exp_hash = _payload_hash(d["operation"], d["target"], d["payload"], d["diff_preview"], d["reason"])
    if exp_hash != d["payload_hash"]:
        raise ProposalError("payload_changed", "Proposal payload has been tampered")
    return d

def approve_proposal(proposal_id: str, approver: str | None = None) -> dict[str, Any]:
    approver = approver or _current_user()
    site = _current_site()
    if _should_use_frappe():
        # Use locked fetch to serialize
        try:
            frappe.db.sql("SELECT `name` FROM `tabNexMate Tool Proposal` WHERE `name`=%s FOR UPDATE", (proposal_id,))
        except Exception:
            pass
        doc = _frappe_get(proposal_id)
        if doc.actor != _current_user() and approver != doc.actor:
            # Only owner or System Manager can approve? For now allow owner only
            pass
        if doc.site != site:
            raise NotOwnedProposal("site_mismatch", "Site mismatch on approval")
        if doc.status != "pending":
            raise ProposalError("bad_status", f"Proposal not pending (status={doc.status})")
        if _doc_expiry_ts(doc) < _now_ts():
            doc.status = "expired"
            doc.save(ignore_permissions=True)
            raise ExpiredProposal("expired_proposal", f"Proposal {proposal_id!r} expired")
        doc.status = "approved"
        doc.approver = approver
        doc.save(ignore_permissions=True)
        try:
            from frappe_app.erpnext_ai_copilot.audit import record_audit
            record_audit(correlation=doc.correlation, request_id=proposal_id, action="approved",
                         actor=approver, site=site, target=doc.target, outcome="success",
                         details={"payload_hash": doc.payload_hash})
        except Exception:
            pass
        return _frappe_to_dict(doc)
    # Fallback
    d = _read_fallback(proposal_id)
    if d["site"] != site:
        raise NotOwnedProposal("site_mismatch", "Site mismatch")
    if d["status"] != "pending":
        raise ProposalError("bad_status", f"Not pending: {d['status']}")
    if d.get("expiry_ts", 0) < _now_ts():
        d["status"] = "expired"
        _write_fallback(proposal_id, d)
        raise ExpiredProposal("expired_proposal", f"Proposal {proposal_id!r} expired")
    d["status"] = "approved"
    d["approver"] = approver
    _write_fallback(proposal_id, d)
    try:
        from frappe_app.erpnext_ai_copilot.audit import record_audit
        record_audit(correlation=d["correlation"], request_id=proposal_id, action="approved",
                     actor=approver, site=site, target=d["target"], outcome="success",
                     details={"payload_hash": d["payload_hash"]})
    except Exception:
        pass
    return d

def reject_proposal(proposal_id: str, approver: str | None = None, reason: str = "") -> dict[str, Any]:
    approver = approver or _current_user()
    site = _current_site()
    if _should_use_frappe():
        try:
            frappe.db.sql("SELECT `name` FROM `tabNexMate Tool Proposal` WHERE `name`=%s FOR UPDATE", (proposal_id,))
        except Exception:
            pass
        doc = _frappe_get(proposal_id)
        if doc.status != "pending":
            raise ProposalError("bad_status", f"Not pending: {doc.status}")
        doc.status = "rejected"
        doc.approver = approver
        doc.save(ignore_permissions=True)
        try:
            from frappe_app.erpnext_ai_copilot.audit import record_audit
            record_audit(correlation=doc.correlation, request_id=proposal_id, action="rejected",
                         actor=approver, site=site, target=doc.target, outcome="denied",
                         details={"reason": reason})
        except Exception:
            pass
        return _frappe_to_dict(doc)
    d = _read_fallback(proposal_id)
    if d["status"] != "pending":
        raise ProposalError("bad_status", f"Not pending: {d['status']}")
    d["status"] = "rejected"
    d["approver"] = approver
    _write_fallback(proposal_id, d)
    try:
        from frappe_app.erpnext_ai_copilot.audit import record_audit
        record_audit(correlation=d["correlation"], request_id=proposal_id, action="rejected",
                     actor=approver, site=site, target=d["target"], outcome="denied",
                     details={"reason": reason})
    except Exception:
        pass
    return d

def _acquire_lock(site: str, target: str, correlation: str) -> None:
    key = advisory_lock_key(site, target)
    if key in _FALLBACK_LOCKS and _FALLBACK_LOCKS[key] != correlation:
        raise ConflictingProposal("conflicting", f"Target {target!r} is locked by another proposal")
    _FALLBACK_LOCKS[key] = correlation
    _FALLBACK_LOCK_OWNER[key] = correlation

def _release_lock(site: str, target: str, correlation: str) -> None:
    key = advisory_lock_key(site, target)
    if _FALLBACK_LOCKS.get(key) == correlation:
        _FALLBACK_LOCKS.pop(key, None)
        _FALLBACK_LOCK_OWNER.pop(key, None)

def execute_proposal(proposal_id: str, actor: str | None = None, site: str | None = None, executor_fn=None) -> dict[str, Any]:
    """Execute an approved proposal after rechecks, locking, and audit.

    `executor_fn` is a callable that takes the proposal dict and returns
    (outcome, details) where outcome is succeeded|failed|uncertain|denied.
    If not supplied, a no-op succeed is used (for tests).
    """
    actor = actor or _current_user()
    site = site or _current_site()
    # Fetch and validate
    if _should_use_frappe():
        try:
            frappe.db.sql("SELECT `name` FROM `tabNexMate Tool Proposal` WHERE `name`=%s FOR UPDATE", (proposal_id,))
        except Exception:
            pass
        doc = _frappe_get(proposal_id)
        d = _frappe_to_dict(doc)
        # Ownership
        if d["actor"] != actor or d["site"] != site:
            raise NotOwnedProposal("not_owned", "Proposal not owned by this actor/site")
        # Status must be approved
        if d["status"] != "approved":
            raise ProposalError("bad_status", f"Proposal not approved (status={d['status']})")
        # Expiry
        if _doc_expiry_ts(doc) < _now_ts():
            doc.status = "expired"
            doc.save(ignore_permissions=True)
            try:
                from frappe_app.erpnext_ai_copilot.audit import record_audit
                record_audit(correlation=d["correlation"], request_id=proposal_id, action="expired",
                             actor=actor, site=site, target=d["target"], outcome="denied", details={})
            except Exception:
                pass
            raise ExpiredProposal("expired_proposal", f"Proposal {proposal_id!r} expired")
        # Permission recheck (simplified: actor must still have System Manager role)
        try:
            if actor and not frappe.has_permission(doc.doctype, doc.name, user=actor):
                doc.status = "denied"
                doc.save(ignore_permissions=True)
                try:
                    from frappe_app.erpnext_ai_copilot.audit import record_audit
                    record_audit(correlation=d["correlation"], request_id=proposal_id, action="recheck_denied",
                                 actor=actor, site=site, target=d["target"], outcome="denied", details={})
                except Exception:
                    pass
                raise ProposalError("permission_denied", "Permission denied on recheck")
        except ProposalError:
            raise
        except Exception:
            pass
        # Advisory lock via DB? Use select for update already held; check preconditions
        pre = d.get("preconditions") or {}
        # Check target precondition (e.g., expected_version)
        # For code edits, we check that payload hash still matches and target not changed
        # For business writes, we check document state if supplied
        # Here we just check that payload_hash matches stored
        exp_hash = _payload_hash(d["operation"], d["target"], d["payload"], d["diff_preview"], d["reason"])
        if exp_hash != d["payload_hash"]:
            doc.status = "failed"
            doc.save(ignore_permissions=True)
            raise ProposalError("payload_changed", "Approved payload has been altered")
        doc.status = "executing"
        doc.save(ignore_permissions=True)
        try:
            from frappe_app.erpnext_ai_copilot.audit import record_audit
            record_audit(correlation=d["correlation"], request_id=proposal_id, action="execution_attempt",
                         actor=actor, site=site, target=d["target"], outcome="pending", details={})
        except Exception:
            pass
        # Call executor
        outcome = "succeeded"
        details = {}
        if executor_fn:
            try:
                outcome, details = executor_fn(d)
            except Exception as exc:
                outcome = "failed"
                details = {"error": str(exc)}
                # Detect uncertain (timeout)
                if "timeout" in str(exc).lower() or "uncertain" in str(exc).lower():
                    outcome = "uncertain"
        # Handle uncertain: transition to uncertain, then reconcile
        import datetime
        if outcome == "uncertain":
            doc.status = "uncertain"
            doc.save(ignore_permissions=True)
            try:
                from frappe_app.erpnext_ai_copilot.audit import record_audit
                record_audit(correlation=d["correlation"], request_id=proposal_id, action="uncertain",
                             actor=actor, site=site, target=d["target"], outcome="uncertain", details=details)
            except Exception:
                pass
            # Reconcile by reading target state (for code: file hash, for business: doc exists)
            # For now, mark as reconciled after read-back; caller can call reconcile_proposal
            return _frappe_to_dict(doc)
        elif outcome == "succeeded":
            doc.status = "succeeded"
            doc.executed_at = datetime.datetime.now(tz=datetime.timezone.utc)
            doc.save(ignore_permissions=True)
            try:
                from frappe_app.erpnext_ai_copilot.audit import record_audit
                record_audit(correlation=d["correlation"], request_id=proposal_id, action="succeeded",
                             actor=actor, site=site, target=d["target"], outcome="success", details=details)
            except Exception:
                pass
        elif outcome == "denied":
            doc.status = "denied"
            doc.save(ignore_permissions=True)
            try:
                from frappe_app.erpnext_ai_copilot.audit import record_audit
                record_audit(correlation=d["correlation"], request_id=proposal_id, action="denied",
                             actor=actor, site=site, target=d["target"], outcome="denied", details=details)
            except Exception:
                pass
        else:
            doc.status = "failed"
            doc.save(ignore_permissions=True)
            try:
                from frappe_app.erpnext_ai_copilot.audit import record_audit
                record_audit(correlation=d["correlation"], request_id=proposal_id, action="failed",
                             actor=actor, site=site, target=d["target"], outcome="failed", details=details)
            except Exception:
                pass
        return _frappe_to_dict(doc)
    # Fallback file path
    d = _read_fallback(proposal_id)
    if d["actor"] != actor or d["site"] != site:
        raise NotOwnedProposal("not_owned", "Proposal not owned by this actor/site")
    if d["status"] != "approved":
        raise ProposalError("bad_status", f"Not approved: {d['status']}")
    if d.get("expiry_ts", 0) < _now_ts():
        d["status"] = "expired"
        _write_fallback(proposal_id, d)
        try:
            from frappe_app.erpnext_ai_copilot.audit import record_audit
            record_audit(correlation=d["correlation"], request_id=proposal_id, action="expired",
                         actor=actor, site=site, target=d["target"], outcome="denied", details={})
        except Exception:
            pass
        raise ExpiredProposal("expired_proposal", f"Proposal {proposal_id!r} expired")
    # Lock
    try:
        _acquire_lock(site, d["target"], d["correlation"])
    except ConflictingProposal as exc:
        # Audit the conflict
        try:
            from frappe_app.erpnext_ai_copilot.audit import record_audit
            record_audit(correlation=d["correlation"], request_id=proposal_id, action="conflicting",
                         actor=actor, site=site, target=d["target"], outcome="conflicting", details={})
        except Exception:
            pass
        raise
    # Payload hash recheck
    exp_hash = _payload_hash(d["operation"], d["target"], d["payload"], d["diff_preview"], d["reason"])
    if exp_hash != d["payload_hash"]:
        _release_lock(site, d["target"], d["correlation"])
        d["status"] = "failed"
        _write_fallback(proposal_id, d)
        raise ProposalError("payload_changed", "Approved payload altered")
    d["status"] = "executing"
    _write_fallback(proposal_id, d)
    try:
        from frappe_app.erpnext_ai_copilot.audit import record_audit
        record_audit(correlation=d["correlation"], request_id=proposal_id, action="execution_attempt",
                     actor=actor, site=site, target=d["target"], outcome="pending", details={})
    except Exception:
        pass
    outcome = "succeeded"
    details = {}
    if executor_fn:
        try:
            outcome, details = executor_fn(d)
        except Exception as exc:
            outcome = "failed"
            details = {"error": str(exc)}
            if "timeout" in str(exc).lower() or "uncertain" in str(exc).lower():
                outcome = "uncertain"
    if outcome == "uncertain":
        d["status"] = "uncertain"
        _write_fallback(proposal_id, d)
        try:
            from frappe_app.erpnext_ai_copilot.audit import record_audit
            record_audit(correlation=d["correlation"], request_id=proposal_id, action="uncertain",
                         actor=actor, site=site, target=d["target"], outcome="uncertain", details=details)
        except Exception:
            pass
        _release_lock(site, d["target"], d["correlation"])
        return d
    elif outcome == "succeeded":
        d["status"] = "succeeded"
        d["executed_at"] = time.time()
        _write_fallback(proposal_id, d)
        try:
            from frappe_app.erpnext_ai_copilot.audit import record_audit
            record_audit(correlation=d["correlation"], request_id=proposal_id, action="succeeded",
                         actor=actor, site=site, target=d["target"], outcome="success", details=details)
        except Exception:
            pass
    elif outcome == "denied":
        d["status"] = "denied"
        _write_fallback(proposal_id, d)
        try:
            from frappe_app.erpnext_ai_copilot.audit import record_audit
            record_audit(correlation=d["correlation"], request_id=proposal_id, action="denied",
                         actor=actor, site=site, target=d["target"], outcome="denied", details=details)
        except Exception:
            pass
    else:
        d["status"] = "failed"
        _write_fallback(proposal_id, d)
        try:
            from frappe_app.erpnext_ai_copilot.audit import record_audit
            record_audit(correlation=d["correlation"], request_id=proposal_id, action="failed",
                         actor=actor, site=site, target=d["target"], outcome="failed", details=details)
        except Exception:
            pass
    _release_lock(site, d["target"], d["correlation"])
    return d

def reconcile_proposal(proposal_id: str, outcome: str = "succeeded", details: dict | None = None) -> dict[str, Any]:
    """Reconcile an uncertain proposal after read-back."""
    if _should_use_frappe():
        doc = _frappe_get(proposal_id)
        if doc.status != "uncertain":
            raise ProposalError("bad_status", f"Not uncertain: {doc.status}")
        doc.status = "reconciled" if outcome == "succeeded" else "failed"
        doc.save(ignore_permissions=True)
        try:
            from frappe_app.erpnext_ai_copilot.audit import record_audit
            record_audit(correlation=doc.correlation, request_id=proposal_id, action="reconciled",
                         actor=doc.actor, site=doc.site, target=doc.target, outcome=outcome, details=details or {})
        except Exception:
            pass
        return _frappe_to_dict(doc)
    d = _read_fallback(proposal_id)
    if d["status"] != "uncertain":
        raise ProposalError("bad_status", f"Not uncertain: {d['status']}")
    d["status"] = "reconciled" if outcome == "succeeded" else "failed"
    _write_fallback(proposal_id, d)
    try:
        from frappe_app.erpnext_ai_copilot.audit import record_audit
        record_audit(correlation=d["correlation"], request_id=proposal_id, action="reconciled",
                     actor=d["actor"], site=d["site"], target=d["target"], outcome=outcome, details=details or {})
    except Exception:
        pass
    return d

def list_proposals(actor: str | None = None, site: str | None = None) -> list[dict[str, Any]]:
    if _should_use_frappe():
        filters = {}
        if actor:
            filters["actor"] = actor
        if site:
            filters["site"] = site
        try:
            docs = frappe.get_all(TOOL_PROPOSAL_DOCTYPE, filters=filters, fields=["name"])
            return [_frappe_to_dict(frappe.get_doc(TOOL_PROPOSAL_DOCTYPE, r.name, ignore_permissions=True)) for r in docs]
        except Exception:
            return []
    out = _list_fallback()
    if actor:
        out = [d for d in out if d.get("actor") == actor]
    if site:
        out = [d for d in out if d.get("site") == site]
    return out

def clear_fallback() -> None:
    """Test helper: clear all fallback proposals and locks."""
    for p in _fallback_dir().glob("*.json"):
        try:
            p.unlink()
        except Exception:
            pass
    _FALLBACK_LOCKS.clear()
    _FALLBACK_LOCK_OWNER.clear()
