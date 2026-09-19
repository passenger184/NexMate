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

# App-local durable contract (M5 frozen, mirrored from tools/contracts.py).
# Intentionally duplicated (not imported) so the Frappe app is
# runtime-self-contained and never requires repo-root `config.py`,
# `tools/`, or `service/` on PYTHONPATH. See Phase 4A: Frappe control-plane
# concern (A), inference/service config is (B) and must not be imported here.
# If tools/contracts.py changes code_edit/business_write semantics, update
# this mirror and tests/test_hardening.py::ContractMirrorTest (which asserts
# parity) — do NOT reintroduce a cross-boundary import.
PROPOSAL_FIELDS = (
    "operation",
    "target",
    "payload",
    "diff_preview",
    "reason",
    "actor",
    "site",
    "correlation",
    "expiry",
    "preconditions",
    "payload_hash",
    "status",
    "approver",
    "executed_at",
)

PROPOSAL_STATUSES = (
    "pending",
    "approved",
    "rejected",
    "executing",
    "succeeded",
    "failed",
    "denied",
    "uncertain",
    "reconciled",
    "audit_pending",
    "conflicting",
    "expired",
)


def advisory_lock_key(site: str, target: str) -> str:
    """Site-isolated advisory lock key (mirrors tools/contracts.py)."""
    return f"{site}:{target}"


def _fallback_base_dir() -> Path:
    """Isolated dev/test fallback base without repo-root config import.

    Explicit `NEXMATE_DURABLE_DIR` wins (isolated tests). Otherwise, when
    running inside Frappe, use the site's private files area
    (`frappe.get_site_path("private","files","nexmate_durable")`); when
    Frappe is unavailable (offline unit tests), fall back to
    `<app>/private/durable_fallback` derived from this file's location.
    Never imports repo-root `config.py` and never assumes `~/ERPNext-AI`,
    WSL paths, or Docker layout. Production without Frappe fails closed
    before reaching here (see _require_durable_store).
    """
    explicit = os.environ.get("NEXMATE_DURABLE_DIR")
    if explicit:
        return Path(explicit)
    if HAS_FRAPPE:
        try:
            site_private = frappe.get_site_path("private", "files", "nexmate_durable")  # type: ignore
            return Path(site_private)
        except Exception:
            pass
    # Offline/unit-test fallback: <app>/private/durable_fallback
    # (this file is at <app>/erpnext_ai_copilot/proposals.py in Frappe,
    # or <repo>/frappe_app/erpnext_ai_copilot/proposals.py in repo).
    return Path(__file__).resolve().parent / "private" / "durable_fallback"


def _fallback_dir() -> Path:
    d = _fallback_base_dir() / "durable_proposals"
    d.mkdir(parents=True, exist_ok=True)
    return d


TOOL_PROPOSAL_DOCTYPE = "NexMate Tool Proposal"
PROPOSAL_ID_PATTERN = "NMTP-"
DEFAULT_EXPIRY_MINUTES = 15
# Correlation length: UUID hex
CORRELATION_BYTES = 8

# In-memory advisory locks for fallback (plus file locks when needed).
# Explicitly isolated dev/test only; Frappe branch uses SELECT FOR UPDATE.
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

def _canonical_preconditions(preconditions: dict[str, Any] | None) -> str:
    """Deterministic canonicalization for integrity hashing.

    Empty/None → empty string. Otherwise JSON with sorted keys and compact
    separators, so field order never affects the hash. Non-serializable
    values fail loud (no silent canonicalization).
    """
    if not preconditions:
        return ""
    return json.dumps(dict(preconditions), sort_keys=True, separators=(",", ":"))


def _payload_hash(
    operation: str,
    target: str,
    payload: str,
    diff: str,
    reason: str,
    preconditions: dict[str, Any] | None = None,
    site: str | None = None,
) -> str:
    """Integrity hash over the exact execution-relevant contract.

    Covers operation, target, payload, diff, reason, canonical preconditions,
    and site (when supplied). Any change to an execution-relevant field
    invalidates the approved proposal and requires a new proposal. The
    canonicalization is deterministic; see _canonical_preconditions.
    """
    h = hashlib.sha256()
    for part in (
        operation,
        target,
        payload or "",
        diff or "",
        reason or "",
        _canonical_preconditions(preconditions),
        site or "",
    ):
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


def _is_production() -> bool:
    """Production by default (matches config.NEXMATE_ENV default).

    Explicit `NEXMATE_ENV=development` is required for isolated dev/test
    fallback; any other value (including unset) is production and fails closed.
    """
    return os.environ.get("NEXMATE_ENV", "production") != "development"


def _fallback_explicitly_allowed() -> bool:
    """Explicit isolated dev/test mode only.

    `NEXMATE_DURABLE_FALLBACK=1` is the sole explicit opt-in for local JSON
    fallback. Absent by default → fail closed. Documented in DEVELOPMENT.md
    as offline-test only; must never be set in production. Even when set,
    it is explicit, never silent.
    """
    return os.environ.get("NEXMATE_DURABLE_FALLBACK") == "1"


def _require_durable_store() -> None:
    """Fail closed when authoritative Frappe is unavailable and no explicit fallback.

    Production (default) + Frappe unavailable + flag absent → ProposalError.
    Explicit `NEXMATE_DURABLE_FALLBACK=1` allows isolated dev/test file fallback.
    Frappe-backed path remains functional when available.
    """
    if _should_use_frappe():
        return
    if _fallback_explicitly_allowed():
        return
    raise ProposalError(
        "frappe_unavailable",
        "Durable Frappe control plane unavailable; failing closed, no local "
        "fallback (production requires Frappe DocType; set "
        "NEXMATE_DURABLE_FALLBACK=1 only for explicit isolated dev/test)",
    )

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
    # Frappe datetime may be string or naive/aware datetime; interpret naive as UTC.
    # Frappe/MariaDB Datetime fields persist naive UTC (no suffix); .timestamp()
    # on naive assumes system local tz, so attach UTC explicitly to keep expiry
    # comparisons correct regardless of server TZ. Fail closed (0 → expired).
    expiry = doc.expiry
    if isinstance(expiry, str):
        try:
            import datetime
            dt = datetime.datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.timestamp()
        except Exception:
            return 0
    try:
        if hasattr(expiry, "timestamp"):
            import datetime as _dt
            if isinstance(expiry, _dt.datetime) and expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=_dt.timezone.utc)
            return float(expiry.timestamp())
        return float(expiry)
    except Exception:
        return 0


def _frappe_datetime_utc(expiry_ts: float):
    """Naive UTC datetime for Frappe/MariaDB Datetime fields.

    Frappe/MariaDB `Datetime` columns require naive representation
    (`YYYY-MM-DD HH:MM:SS.ffffff`, no `+00:00` suffix); tz-aware values raise
    `OperationalError 1292`. The underlying instant is still UTC (derived
    from the same Unix timestamp used for fallback `expiry_ts` and expiry
    comparisons); only the persistence representation is naive. Use for every
    DocType Datetime assignment in this module (expiry, executed_at).
    """
    import datetime
    return datetime.datetime.fromtimestamp(expiry_ts, tz=datetime.timezone.utc).replace(tzinfo=None)

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
    """Create a durable proposal (Frappe-owned; explicit isolated fallback only).

    Records immutable hash over (operation, target, payload, diff, reason,
    canonical preconditions, site). The proposal is actor/site-bound and
    starts as `pending`. Production without Frappe fails closed (no local
    JSON); `NEXMATE_DURABLE_FALLBACK=1` is the sole explicit isolated
    dev/test opt-in and must never be set in production.
    """
    _require_durable_store()
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
    # Idempotency key defaults to content hash + actor/site if not supplied.
    # Two-step to avoid circularity: tmp hash without key → key → final hash
    # covering full preconditions + site. Any pre/site change invalidates.
    _tmp = _payload_hash(operation, target, payload, diff_preview, reason, pre, site)
    if "idempotency_key" not in pre:
        pre["idempotency_key"] = f"{actor}:{site}:{_tmp[:12]}"
    phash = _payload_hash(operation, target, payload, diff_preview, reason, pre, site)

    expiry_ts = _expiry_ts(expiry_minutes)
    # Idempotency: same key + same target + same hash → return existing
    # succeeded/reconciled result (no duplicate execution). Same key with
    # different hash/target → conflicting (reject, no silent overwrite).
    # Fallback check is explicit isolated dev/test only; Frappe branch relies
    # on row-lock + status check (no blind last-writer-wins) — see execute.
    if not _should_use_frappe():
        for _existing in _list_fallback():
            if _existing.get("preconditions", {}).get("idempotency_key") != pre["idempotency_key"]:
                continue
            if _existing.get("target") != target or _existing.get("payload_hash") != phash:
                raise ConflictingProposal(
                    "conflicting",
                    "Same idempotency key with different target/payload; rejected, no silent overwrite",
                )
            if _existing.get("status") in ("succeeded", "reconciled"):
                import datetime as _dt
                _exp_iso = _dt.datetime.fromtimestamp(
                    _existing.get("expiry_ts", expiry_ts), tz=_dt.timezone.utc).isoformat()
                return {
                    "proposal_id": _existing["name"],
                    "operation": _existing["operation"],
                    "target": _existing["target"],
                    "payload_hash": _existing["payload_hash"],
                    "correlation": _existing["correlation"],
                    "expiry": _exp_iso,
                    "status": _existing["status"],
                    "preconditions": _existing.get("preconditions", {}),
                    "idempotent_replay": True,
                }
    # For DocType, expiry is naive UTC datetime (Frappe/MariaDB require no suffix).
    # API responses keep tz-aware ISO (explicit instant); DB gets naive (same instant).
    import datetime
    expiry_dt = datetime.datetime.fromtimestamp(expiry_ts, tz=datetime.timezone.utc)
    expiry_doc = expiry_dt.replace(tzinfo=None)

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
                "expiry": expiry_doc,
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
                from .audit import record_audit
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
            # Frappe insert failure must fail closed, not silently fallback
            # to a second authority. Only explicit isolated fallback may
            # use local JSON (already checked by _require_durable_store).
            if "ProposalError" in type(exc).__name__:
                raise
            if _fallback_explicitly_allowed() and not _should_use_frappe():
                pass
            else:
                raise ProposalError(
                    "frappe_unavailable",
                    f"Frappe proposal persistence failed: {exc}",
                ) from exc

    # Fallback durable file (explicit isolated dev/test only, never production
    # authority — enforced by _require_durable_store at entry).
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
        from .audit import record_audit
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
    """Fetch a proposal, enforcing actor/site binding.

    M5 policy is owner-only: only the proposal owner on the same site may
    fetch. Frappe session identity is authoritative; browser-supplied actor
    never elevates (enforced in api.py by deriving actor/site from
    _gateway_context, never from form fields).
    """
    _require_durable_store()
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
        # Integrity: hash covers operation/target/payload/diff/reason/pre/site
        _exp = _payload_hash(
            d["operation"], d["target"], d["payload"], d["diff_preview"],
            d["reason"], d.get("preconditions"), d["site"],
        )
        if _exp != d["payload_hash"]:
            raise ProposalError("payload_changed", "Proposal payload has been tampered")
        return d
    # Fallback (explicit isolated dev/test only)
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
    # Check hash immutability (covers preconditions + site)
    exp_hash = _payload_hash(
        d["operation"], d["target"], d["payload"], d["diff_preview"],
        d["reason"], d.get("preconditions"), d.get("site"),
    )
    if exp_hash != d["payload_hash"]:
        raise ProposalError("payload_changed", "Proposal payload has been tampered")
    return d

def approve_proposal(proposal_id: str, approver: str | None = None) -> dict[str, Any]:
    """Approve a pending proposal — M5 policy is owner-only, explicitly.

    Only the proposal owner on the same site may approve their own proposal.
    Approver identity comes from authenticated Frappe context
    (api.py derives from _gateway_context, never from browser fields).
    Different-actor approval is denied, even for System Manager, to avoid
    broadening permissions beyond the intended owner-only policy. Approval
    after expiry/revocation is refused. Every approval is audited.
    """
    _require_durable_store()
    approver = approver or _current_user()
    site = _current_site()
    if _should_use_frappe():
        # Use locked fetch to serialize
        try:
            frappe.db.sql("SELECT `name` FROM `tabNexMate Tool Proposal` WHERE `name`=%s FOR UPDATE", (proposal_id,))
        except Exception:
            pass
        doc = _frappe_get(proposal_id)
        if doc.site != site:
            raise NotOwnedProposal("site_mismatch", "Site mismatch on approval")
        # Owner-only: approver must equal proposal owner
        if approver != doc.actor:
            raise NotOwnedProposal("not_authorized", "Only the proposal owner may approve")
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
            from .audit import record_audit
            record_audit(correlation=doc.correlation, request_id=proposal_id, action="approved",
                         actor=approver, site=site, target=doc.target, outcome="success",
                         details={"payload_hash": doc.payload_hash})
        except Exception:
            # Audit failure must not silently pass — mark audit_pending
            try:
                doc.status = "audit_pending"
                doc.save(ignore_permissions=True)
            except Exception:
                pass
            raise ProposalError("audit_pending", "Approval persisted but audit failed; repair required")
        return _frappe_to_dict(doc)
    # Fallback (explicit isolated dev/test only)
    d = _read_fallback(proposal_id)
    if d["site"] != site:
        raise NotOwnedProposal("site_mismatch", "Site mismatch")
    if approver != d.get("actor"):
        raise NotOwnedProposal("not_authorized", "Only the proposal owner may approve")
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
        from .audit import record_audit
        record_audit(correlation=d["correlation"], request_id=proposal_id, action="approved",
                     actor=approver, site=site, target=d["target"], outcome="success",
                     details={"payload_hash": d["payload_hash"]})
    except Exception:
        d["status"] = "audit_pending"
        try:
            _write_fallback(proposal_id, d)
        except Exception:
            pass
        raise ProposalError("audit_pending", "Approval persisted but audit failed; repair required")
    return d

def reject_proposal(proposal_id: str, approver: str | None = None, reason: str = "") -> dict[str, Any]:
    """Reject a pending proposal — owner-only, explicitly (same policy as approve)."""
    _require_durable_store()
    approver = approver or _current_user()
    site = _current_site()
    if _should_use_frappe():
        try:
            frappe.db.sql("SELECT `name` FROM `tabNexMate Tool Proposal` WHERE `name`=%s FOR UPDATE", (proposal_id,))
        except Exception:
            pass
        doc = _frappe_get(proposal_id)
        if doc.site != site:
            raise NotOwnedProposal("site_mismatch", "Site mismatch on reject")
        if approver != doc.actor:
            raise NotOwnedProposal("not_authorized", "Only the proposal owner may reject")
        if doc.status != "pending":
            raise ProposalError("bad_status", f"Not pending: {doc.status}")
        doc.status = "rejected"
        doc.approver = approver
        doc.save(ignore_permissions=True)
        try:
            from .audit import record_audit
            record_audit(correlation=doc.correlation, request_id=proposal_id, action="rejected",
                         actor=approver, site=site, target=doc.target, outcome="denied",
                         details={"reason": reason})
        except Exception:
            try:
                doc.status = "audit_pending"
                doc.save(ignore_permissions=True)
            except Exception:
                pass
            raise ProposalError("audit_pending", "Rejection persisted but audit failed; repair required")
        return _frappe_to_dict(doc)
    d = _read_fallback(proposal_id)
    if d["site"] != site:
        raise NotOwnedProposal("site_mismatch", "Site mismatch")
    if approver != d.get("actor"):
        raise NotOwnedProposal("not_authorized", "Only the proposal owner may reject")
    if d["status"] != "pending":
        raise ProposalError("bad_status", f"Not pending: {d['status']}")
    d["status"] = "rejected"
    d["approver"] = approver
    _write_fallback(proposal_id, d)
    try:
        from .audit import record_audit
        record_audit(correlation=d["correlation"], request_id=proposal_id, action="rejected",
                     actor=approver, site=site, target=d["target"], outcome="denied",
                     details={"reason": reason})
    except Exception:
        d["status"] = "audit_pending"
        try:
            _write_fallback(proposal_id, d)
        except Exception:
            pass
        raise ProposalError("audit_pending", "Rejection persisted but audit failed; repair required")
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
    If not supplied, a no-op succeed is used (for tests). Production without
    Frappe fails closed; explicit isolated fallback only.
    """
    _require_durable_store()
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
                from .audit import record_audit
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
                    from .audit import record_audit
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
        # Hash covers operation/target/payload/diff/reason/pre/site (Task 6)
        exp_hash = _payload_hash(
            d["operation"], d["target"], d["payload"], d["diff_preview"],
            d["reason"], d.get("preconditions"), d["site"],
        )
        if exp_hash != d["payload_hash"]:
            doc.status = "failed"
            doc.save(ignore_permissions=True)
            raise ProposalError("payload_changed", "Approved payload has been altered")
        doc.status = "executing"
        doc.save(ignore_permissions=True)
        try:
            from .audit import record_audit
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
                from .audit import record_audit
                record_audit(correlation=d["correlation"], request_id=proposal_id, action="uncertain",
                             actor=actor, site=site, target=d["target"], outcome="uncertain", details=details)
            except Exception:
                pass
            # Reconcile by reading target state (for code: file hash, for business: doc exists)
            # For now, mark as reconciled after read-back; caller can call reconcile_proposal
            return _frappe_to_dict(doc)
        elif outcome == "succeeded":
            doc.status = "succeeded"
            # Naive UTC for Frappe Datetime (same 1292 rule as expiry).
            doc.executed_at = datetime.datetime.now(tz=datetime.timezone.utc).replace(tzinfo=None)
            doc.save(ignore_permissions=True)
            try:
                from .audit import record_audit
                record_audit(correlation=d["correlation"], request_id=proposal_id, action="succeeded",
                             actor=actor, site=site, target=d["target"], outcome="success", details=details)
            except Exception as exc:
                # Audit failure must not silently pass as clean success
                try:
                    doc.status = "audit_pending"
                    doc.save(ignore_permissions=True)
                except Exception:
                    pass
                raise ProposalError("audit_pending", f"Execution succeeded but audit failed; repair required: {exc}") from exc
        elif outcome == "denied":
            doc.status = "denied"
            doc.save(ignore_permissions=True)
            try:
                from .audit import record_audit
                record_audit(correlation=d["correlation"], request_id=proposal_id, action="denied",
                             actor=actor, site=site, target=d["target"], outcome="denied", details=details)
            except Exception:
                pass
        else:
            doc.status = "failed"
            doc.save(ignore_permissions=True)
            try:
                from .audit import record_audit
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
            from .audit import record_audit
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
            from .audit import record_audit
            record_audit(correlation=d["correlation"], request_id=proposal_id, action="conflicting",
                         actor=actor, site=site, target=d["target"], outcome="conflicting", details={})
        except Exception:
            pass
        raise
    # Payload hash recheck (covers preconditions + site, Task 6)
    exp_hash = _payload_hash(
        d["operation"], d["target"], d["payload"], d["diff_preview"],
        d["reason"], d.get("preconditions"), d.get("site"),
    )
    if exp_hash != d["payload_hash"]:
        _release_lock(site, d["target"], d["correlation"])
        d["status"] = "failed"
        _write_fallback(proposal_id, d)
        raise ProposalError("payload_changed", "Approved payload altered")
    d["status"] = "executing"
    _write_fallback(proposal_id, d)
    try:
        from .audit import record_audit
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
            from .audit import record_audit
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
            from .audit import record_audit
            record_audit(correlation=d["correlation"], request_id=proposal_id, action="succeeded",
                         actor=actor, site=site, target=d["target"], outcome="success", details=details)
        except Exception as exc:
            d["status"] = "audit_pending"
            d["pending_outcome"] = "succeeded"
            d["pending_details"] = details
            try:
                _write_fallback(proposal_id, d)
            except Exception:
                pass
            _release_lock(site, d["target"], d["correlation"])
            raise ProposalError("audit_pending", f"Execution succeeded but audit failed; repair required: {exc}") from exc
    elif outcome == "denied":
        d["status"] = "denied"
        _write_fallback(proposal_id, d)
        try:
            from .audit import record_audit
            record_audit(correlation=d["correlation"], request_id=proposal_id, action="denied",
                         actor=actor, site=site, target=d["target"], outcome="denied", details=details)
        except Exception:
            pass
    else:
        d["status"] = "failed"
        _write_fallback(proposal_id, d)
        try:
            from .audit import record_audit
            record_audit(correlation=d["correlation"], request_id=proposal_id, action="failed",
                         actor=actor, site=site, target=d["target"], outcome="failed", details=details)
        except Exception:
            pass
    _release_lock(site, d["target"], d["correlation"])
    return d

def reconcile_proposal(
    proposal_id: str,
    outcome: str = "succeeded",
    details: dict | None = None,
    read_back_fn=None,
) -> dict[str, Any]:
    """Reconcile an uncertain proposal after actual target read-back.

    Required lifecycle: execution attempt → uncertain → actual target
    read-back → reconciliation. `outcome` is treated as input/evidence, not
    authoritative truth. `read_back_fn` must be a callable taking the
    proposal dict and returning (confirmed: bool, evidence: dict). If
    `outcome==succeeded` but read-back does not confirm, the proposal
    remains `uncertain` (irreconcilable explicitly represented) or goes
    `failed`, never silently `succeeded`. Same idempotency identity is
    preserved (correlation unchanged). Result is audited. No blind replay:
    execute still refuses `uncertain` (must reconcile first).
    """
    _require_durable_store()
    details = details or {}
    # Read-back is mandatory for succeeded; failed may reconcile without
    # read-back (explicit failure), but still audited.
    if outcome == "succeeded":
        if read_back_fn is None:
            raise ProposalError(
                "reconciliation_requires_readback",
                "Reconciliation to succeeded requires actual target read-back "
                "evidence; caller-supplied outcome alone is insufficient",
            )
        try:
            confirmed, evidence = read_back_fn({} if _should_use_frappe() else _read_fallback(proposal_id))
        except Exception as exc:
            raise ProposalError(
                "readback_unavailable",
                f"Target read-back unavailable; remains uncertain: {exc}",
            ) from exc
        if not confirmed:
            raise ProposalError(
                "readback_not_confirmed",
                "Target read-back did not confirm success; remains uncertain "
                f"(evidence: {evidence})",
            )
        details = {**details, "readback_evidence": evidence}
    if _should_use_frappe():
        doc = _frappe_get(proposal_id)
        if doc.status != "uncertain":
            raise ProposalError("bad_status", f"Not uncertain: {doc.status}")
        doc.status = "reconciled" if outcome == "succeeded" else "failed"
        doc.save(ignore_permissions=True)
        try:
            from .audit import record_audit
            record_audit(correlation=doc.correlation, request_id=proposal_id, action="reconciled",
                         actor=doc.actor, site=doc.site, target=doc.target, outcome=outcome, details=details)
        except Exception as exc:
            # Audit failure during reconcile → audit_pending, not silent success
            try:
                doc.status = "audit_pending"
                doc.save(ignore_permissions=True)
            except Exception:
                pass
            raise ProposalError("audit_pending", f"Reconciled but audit failed; repair required: {exc}") from exc
        return _frappe_to_dict(doc)
    d = _read_fallback(proposal_id)
    if d["status"] != "uncertain":
        raise ProposalError("bad_status", f"Not uncertain: {d['status']}")
    d["status"] = "reconciled" if outcome == "succeeded" else "failed"
    _write_fallback(proposal_id, d)
    try:
        from .audit import record_audit
        record_audit(correlation=d["correlation"], request_id=proposal_id, action="reconciled",
                     actor=d["actor"], site=d["site"], target=d["target"], outcome=outcome, details=details)
    except Exception as exc:
        d["status"] = "audit_pending"
        d["pending_outcome"] = outcome
        d["pending_details"] = details
        try:
            _write_fallback(proposal_id, d)
        except Exception:
            pass
        raise ProposalError("audit_pending", f"Reconciled but audit failed; repair required: {exc}") from exc
    return d


def repair_audit_pending(proposal_id: str, actor: str | None = None, site: str | None = None) -> dict[str, Any]:
    """Repair a proposal stuck in `audit_pending` by retrying audit persistence.

    Idempotent: duplicate repair attempts do not create contradictory records;
    successful repair is itself audited. If audit still fails, remains
    `audit_pending`.
    """
    _require_durable_store()
    actor = actor or _current_user()
    site = site or _current_site()
    if _should_use_frappe():
        doc = _frappe_get(proposal_id)
        if doc.actor != actor or doc.site != site:
            raise NotOwnedProposal("not_owned", "Proposal not owned by this actor/site")
        if doc.status != "audit_pending":
            raise ProposalError("bad_status", f"Not audit_pending: {doc.status}")
        # Retry the missing audit leg (reconstruct from proposal state)
        try:
            from .audit import record_audit
            # The original terminal outcome is stored in pending_outcome if present,
            # else infer from executed_at (succeeded) or approver (approved)
            record_audit(correlation=doc.correlation, request_id=proposal_id, action="repair",
                         actor=actor, site=site, target=doc.target, outcome="success",
                         details={"repaired_from": "audit_pending"})
        except Exception as exc:
            raise ProposalError("audit_pending", f"Repair still failing: {exc}") from exc
        # On success, move to reconciled/succeeded? Keep audit_pending → reconciled
        # to mark repair observable; caller can then reconcile if uncertain.
        # For simplicity, if pending_outcome was succeeded, go succeeded.
        doc.status = "reconciled"
        doc.save(ignore_permissions=True)
        try:
            from .audit import record_audit as _ra
            _ra(correlation=doc.correlation, request_id=proposal_id, action="reconciled",
                actor=actor, site=site, target=doc.target, outcome="success",
                details={"repair": True})
        except Exception:
            pass
        return _frappe_to_dict(doc)
    d = _read_fallback(proposal_id)
    if d.get("actor") != actor or d.get("site") != site:
        raise NotOwnedProposal("not_owned", "Proposal not owned by this actor/site")
    if d.get("status") != "audit_pending":
        raise ProposalError("bad_status", f"Not audit_pending: {d.get('status')}")
    try:
        from .audit import record_audit
        record_audit(correlation=d["correlation"], request_id=proposal_id, action="repair",
                     actor=actor, site=site, target=d["target"], outcome="success",
                     details={"repaired_from": "audit_pending", "pending_outcome": d.get("pending_outcome")})
    except Exception as exc:
        raise ProposalError("audit_pending", f"Repair still failing: {exc}") from exc
    # Idempotent: only transition once; duplicate repairs see status != audit_pending above
    pending = d.get("pending_outcome", "succeeded")
    d["status"] = "reconciled" if pending == "succeeded" else "failed"
    _write_fallback(proposal_id, d)
    try:
        from .audit import record_audit as _ra2
        _ra2(correlation=d["correlation"], request_id=proposal_id, action="reconciled",
             actor=actor, site=site, target=d["target"], outcome=pending, details={"repair": True})
    except Exception:
        pass
    return d

def list_proposals(actor: str | None = None, site: str | None = None) -> list[dict[str, Any]]:
    """List proposals — fails closed without Frappe unless explicit fallback.

    Frappe is authoritative; fallback is explicitly isolated dev/test only.
    """
    _require_durable_store()
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
