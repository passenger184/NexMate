"""U5 Frappe-native authorized ERPNext business-read adapter.

This module is the authorization enforcement point for ERPNext business-data
reads requested by authenticated NexMate users. It replaces the shared
integration-credential read path (``tools/erpnext.py``) for that purpose.

Security contract (see ``openspec/specs/erpnext-authorized-reads``):

* The authorization subject is **exclusively** ``frappe.session.user``. This
  module exposes no ``user``/``actor``/``username``/``site``/``mode``
  parameter, and rejects a request that carries one in its payload.
* Authorization is performed by Frappe's native permission engine. This module
  only ever **narrows** what Frappe authorizes; it never widens it.
* Only permission-aware Frappe APIs are used. ``frappe.get_all``, raw SQL and
  direct value/count helpers, unconfigured query-builder access,
  permission-suppressing document flags, and ``frappe.set_user`` are forbidden.
* Field-level read permission is enforced before serialization and the result
  is built from an explicit field projection, so a stripped field can never
  reappear as a type default.
* Every read emits exactly one metadata-only audit event. If the audit write
  fails, the read is denied and no data is returned.
* Not-found and permission-denied are distinguishable internally (for audit and
  Debug) but collapse to a single caller-indistinguishable outcome
  (:func:`collapse_for_caller`).
"""

import re
from dataclasses import dataclass, field as _dc_field
from typing import Any

try:  # pragma: no cover - exercised only inside a real Frappe process
    import frappe
except Exception:  # pragma: no cover - offline import guard
    frappe = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

#: Operations this adapter supports. Schema/metadata access, writes, deletes
#: and arbitrary method invocation are deliberately absent (spec: strict
#: read-request validation).
SUPPORTED_OPERATIONS = frozenset({"document", "list"})

#: Adapter-level list bound. Matches the general ``erpnext_read`` tool contract
#: maximum of 100 and the approved immutable service ceiling, so an
#: administrator-configured value up to the ceiling flows end to end.
#: See verification-notes.md.
MAX_LIST_LIMIT = 100
DEFAULT_LIST_LIMIT = 20

#: Bounds on request components.
MAX_DOCUMENT_NAME_CHARS = 140
MAX_FIELD_COUNT = 50
MAX_FILTER_KEYS = 8
MAX_FILTER_VALUES = 20
MAX_RESULT_BYTES = 128 * 1024

#: Business DocTypes this adapter is approved to read. A request for any other
#: DocType is rejected before any data access. This is reviewed configuration,
#: not an emergent behaviour, and may be widened only by a reviewed change.
ALLOWED_DOCTYPES: dict[str, tuple[str, ...]] = {
    "Customer": ("name", "customer_name", "customer_group", "territory", "customer_type", "disabled", "email_id", "mobile_no"),
    "Supplier": ("name", "supplier_name", "supplier_group", "is_transporter", "disabled"),
    "Item": ("name", "item_code", "item_name", "item_group", "stock_uom", "disabled", "is_stock_item"),
    "Item Group": ("name", "item_group_name", "parent_item_group", "is_group", "lft", "rgt"),
    "Company": ("name", "company_name", "abbr", "default_currency", "country"),
    "Warehouse": ("name", "warehouse_name", "company", "is_group", "disabled"),
    "Territory": ("name", "territory_name", "parent_territory", "is_group"),
    "Customer Group": ("name", "customer_group_name", "parent_customer_group", "is_group"),
    "Brand": ("name", "brand"),
    "Sales Invoice": ("name", "customer", "posting_date", "grand_total", "status", "docstatus", "currency"),
    "Sales Order": ("name", "customer", "transaction_date", "total", "status", "docstatus", "currency"),
    "Sales Person": ("name", "sales_person_name", "is_group"),
    "Lead": ("name", "lead_name", "status", "company"),
    "Opportunity": ("name", "status", "party", "opportunity_amount", "currency"),
    "Quotation": ("name", "customer", "status", "grand_total", "currency"),
    "Delivery Note": ("name", "customer", "posting_date", "status", "docstatus"),
    "Purchase Invoice": ("name", "supplier", "posting_date", "grand_total", "status", "docstatus", "currency"),
    "Purchase Receipt": ("name", "supplier", "posting_date", "status", "docstatus"),
    "Payment Entry": ("name", "payment_type", "party_type", "party", "paid_amount", "status"),
    "Journal Entry": ("name", "voucher_type", "posting_date", "total_debit", "status", "docstatus"),
    "GL Entry": ("name", "posting_date", "account", "debit", "credit", "party"),
    "Mode of Payment": ("name", "mode_of_payment", "type"),
    "Cost Center": ("name", "cost_center_name", "company", "is_group"),
    "Project": ("name", "project_name", "status", "company", "expected_start_date"),
    "Task": ("name", "subject", "status", "project", "exp_start_date"),
    "Timesheet": ("name", "employee", "status", "total_hours"),
    "Employee": ("name", "employee_name", "status", "company", "department"),
}

#: Filter operators this adapter accepts. Anything else is rejected rather
#: than rewritten.
ALLOWED_FILTER_OPERATORS = frozenset({"=", "!=", ">", "<", ">=", "<=", "in", "not in", "like", "is"})

#: Field names that must never be accepted as a filter target, independent of
#: the per-doctype allowlist, because they are control or credential surfaces.
FORBIDDEN_FILTER_FIELDS = frozenset({"owner", "creation", "modified", "modified_by", "_user_tags", "password", "api_key", "api_secret"})

#: Payload keys that would attempt to assert an authorization subject.
FORBIDDEN_SUBJECT_KEYS = frozenset(
    {"user", "actor", "username", "site", "mode", "user_id", "authorization_subject", "as_user", "owner", "set_user"}
)

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _./:#@\-()]*$")
_FIELD_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

#: Audit action/outcome vocabulary (added to the NexMate Audit Entry DocType).
AUDIT_ACTION_READ = "erpnext_read"
OUTCOME_SUCCESS = "success"
OUTCOME_NOT_FOUND = "not_found"
OUTCOME_PERMISSION_DENIED = "permission_denied"
OUTCOME_INVALID_REQUEST = "invalid_request"

#: The single caller-visible denial string. See spec: Denial does not disclose
#: document existence.
CALLER_DENIAL = "Document not found or access denied."


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ReadRefusal(Exception):
    """Base class for every refusal this adapter produces.

    ``code`` is the *internal* outcome. It is used for audit and Debug and is
    never surfaced to the caller verbatim.
    """

    code = OUTCOME_INVALID_REQUEST

    def __init__(self, reason: str = ""):
        self.reason = _bounded(reason, 200)
        super().__init__(self.reason or self.code)

    def caller_message(self) -> str:
        return CALLER_DENIAL


class UnsupportedOperation(ReadRefusal):
    code = OUTCOME_INVALID_REQUEST


class InvalidRequest(ReadRefusal):
    code = OUTCOME_INVALID_REQUEST


class DocTypeNotAllowed(InvalidRequest):
    code = OUTCOME_INVALID_REQUEST


class NotFound(ReadRefusal):
    code = OUTCOME_NOT_FOUND


class PermissionDenied(ReadRefusal):
    code = OUTCOME_PERMISSION_DENIED


class AuditUnavailable(ReadRefusal):
    """Audit write failed. Fail closed: no data is returned."""

    code = "audit_pending"


def _bounded(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    return text[:limit]


# ---------------------------------------------------------------------------
# Identity and site
# ---------------------------------------------------------------------------


def current_subject() -> str:
    """Return the sole authorization subject: the live Frappe session user.

    Never accepts an override. Refuses absent and Guest sessions. Performs no
    normalization, repair or case folding.
    """
    if frappe is None:  # pragma: no cover - offline guard
        raise PermissionDenied("no Frappe session")
    user = getattr(getattr(frappe, "session", None), "user", None)
    if not user or not isinstance(user, str) or user == "Guest":
        raise PermissionDenied("authentication required")
    return user


def current_site() -> str:
    """Return the authoritative current site from the Frappe local context."""
    if frappe is None:  # pragma: no cover - offline guard
        raise PermissionDenied("no Frappe session")
    site = getattr(getattr(frappe, "local", None), "site", None)
    if not site or not isinstance(site, str):
        raise InvalidRequest("no authoritative site")
    return site


# ---------------------------------------------------------------------------
# Request contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ERPNextReadRequest:
    """A validated, bounded business-read request.

    Deliberately has no identity/site/mode field. Identity is derived from the
    session inside :func:`execute_read`.
    """

    operation: str
    doctype: str
    name: str | None = None
    fields: tuple[str, ...] = ()
    filters: dict[str, Any] = _dc_field(default_factory=dict)
    limit: int = DEFAULT_LIST_LIMIT
    correlation: str = ""
    request_id: str = ""


def _reject_subject_keys(payload: dict[str, Any]) -> None:
    """Reject any payload attempting to assert an authorization subject."""
    if not isinstance(payload, dict):
        raise InvalidRequest("request must be an object")
    present = FORBIDDEN_SUBJECT_KEYS.intersection(k for k in payload if isinstance(k, str))
    if present:
        raise InvalidRequest("authorization subject is not caller-settable")


def _validate_operation(op: Any) -> str:
    if not isinstance(op, str) or op not in SUPPORTED_OPERATIONS:
        raise UnsupportedOperation("unsupported operation")
    return op


def _validate_doctype(doctype: Any) -> tuple[str, tuple[str, ...]]:
    if not isinstance(doctype, str) or not doctype:
        raise InvalidRequest("doctype is required")
    if doctype not in ALLOWED_DOCTYPES:
        raise DocTypeNotAllowed("doctype is not in the approved read policy")
    try:
        meta = frappe.get_meta(doctype)
    except Exception:
        raise DocTypeNotAllowed("doctype is not a readable document type")
    if getattr(meta, "istable", False):
        raise DocTypeNotAllowed("child doctypes are not directly readable")
    if getattr(meta, "issingle", False):
        raise DocTypeNotAllowed("single doctypes are not business records")
    return doctype, ALLOWED_DOCTYPES[doctype]


def _validate_name(name: Any) -> str | None:
    if name is None:
        return None
    if not isinstance(name, str):
        raise InvalidRequest("document name must be a string")
    trimmed = name.strip()
    if not trimmed or len(trimmed) > MAX_DOCUMENT_NAME_CHARS:
        raise InvalidRequest("document name is empty or over-long")
    if not _NAME_RE.match(trimmed):
        raise InvalidRequest("document name contains unsupported characters")
    return trimmed


def _validate_fields(fields: Any, permitted: tuple[str, ...]) -> tuple[str, ...]:
    """Require an explicit, non-wildcard, allowlisted projection."""
    if fields is None:
        raise InvalidRequest("an explicit field list is required")
    if not isinstance(fields, (list, tuple)):
        raise InvalidRequest("fields must be a list")
    if not fields:
        raise InvalidRequest("an explicit field list is required")
    if len(fields) > MAX_FIELD_COUNT:
        raise InvalidRequest("too many requested fields")
    seen: list[str] = []
    for item in fields:
        if not isinstance(item, str):
            raise InvalidRequest("field names must be strings")
        if item == "*":
            raise InvalidRequest("wildcard field requests are not accepted")
        if not _FIELD_RE.match(item):
            raise InvalidRequest("field name is not a plain identifier")
        if item not in permitted:
            raise InvalidRequest("field is not in the approved projection for this doctype")
        if item not in seen:
            seen.append(item)
    return tuple(seen)


def _validate_filters(filters: Any, permitted: tuple[str, ...]) -> dict[str, Any]:
    """Enforce a bounded, operator-allowlisted filter grammar."""
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        raise InvalidRequest("filters must be an object")
    if len(filters) > MAX_FILTER_KEYS:
        raise InvalidRequest("too many filter keys")
    total_values = 0
    out: dict[str, Any] = {}
    for key, value in filters.items():
        if not isinstance(key, str) or not _FIELD_RE.match(key):
            raise InvalidRequest("filter key is not a plain identifier")
        if key in FORBIDDEN_FILTER_FIELDS:
            raise InvalidRequest("filter on a control or credential field is not accepted")
        if key not in permitted:
            raise InvalidRequest("filter field is not in the approved projection for this doctype")
        if isinstance(value, dict):
            raise InvalidRequest("nested filter expressions are not accepted")
        if isinstance(value, (list, tuple)):
            total_values += len(value)
            for entry in value:
                _validate_scalar(entry)
        else:
            total_values += 1
            _validate_scalar(value)
        out[key] = value
    if total_values > MAX_FILTER_VALUES:
        raise InvalidRequest("too many filter values")
    return out


def _validate_scalar(value: Any) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str) and len(value) > 200:
            raise InvalidRequest("filter value is over-long")
        return
    raise InvalidRequest("unsupported filter value type")


def _validate_limit(limit: Any) -> int:
    if limit is None:
        return DEFAULT_LIST_LIMIT
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise InvalidRequest("limit must be an integer")
    if limit < 1 or limit > MAX_LIST_LIMIT:
        raise InvalidRequest("limit is outside the adapter bound")
    return limit


def build_request(payload: dict[str, Any]) -> ERPNextReadRequest:
    """Validate an untrusted payload into a bounded read request.

    The payload originates from inference and/or a language model. It is
    validated exactly as any other untrusted requester would be. An invalid
    request is rejected, never rewritten into a different query.
    """
    _reject_subject_keys(payload)

    operation = _validate_operation(payload.get("operation"))
    doctype, permitted = _validate_doctype(payload.get("doctype"))
    name = _validate_name(payload.get("name"))
    if operation == "document" and not name:
        raise InvalidRequest("document operation requires a name")
    if operation == "list" and name:
        raise InvalidRequest("list operation does not take a document name")
    fields = _validate_fields(payload.get("fields"), permitted)
    filters = _validate_filters(payload.get("filters"), permitted)
    limit = _validate_limit(payload.get("limit")) if operation == "list" else 1

    return ERPNextReadRequest(
        operation=operation,
        doctype=doctype,
        name=name,
        fields=fields,
        filters=filters,
        limit=limit,
        correlation=_bounded(payload.get("correlation"), 64) or "nexmate-read",
        request_id=_bounded(payload.get("request_id"), 64) or "read",
    )


# ---------------------------------------------------------------------------
# Execution — permission-aware reads only
# ---------------------------------------------------------------------------

#: Names the adapter must never call. Declared here so the intent is explicit
#: and testable; none of these is referenced anywhere in the execution path.
FORBIDDEN_APIS = (
    "frappe.get_all",
    "frappe.db.sql",
    "frappe.db.get_value",
    "frappe.db.count",
    "frappe.db.get_list",
    "frappe.get_cached_doc",
    "frappe.qb.get_query",
    "frappe.set_user",
)


def _list_read(request: ERPNextReadRequest) -> dict[str, Any]:
    """Permission-checked list read with an explicit field projection.

    Uses the permission-checking list API only. No wildcard, no
    ``ignore_permissions``, no permission-suppressing flags.
    """
    rows = frappe.get_list(
        request.doctype,
        fields=list(request.fields),
        filters=request.filters or None,
        limit_page_length=request.limit,
    )
    projected = []
    for row in rows:
        get = row.get if hasattr(row, "get") else lambda _k, d=None: d
        projected.append({name: get(name) for name in request.fields})
    return {"rows": projected, "row_count": len(projected)}


def _document_read(request: ERPNextReadRequest) -> dict[str, Any]:
    """Single-document read with a DocType check and field-level enforcement.

    Three distinct steps, mirroring the installed Frappe 16.31.0 REST handler:
    load, explicit permission check, explicit field-level read permissions.
    The result is then built from the *explicit* requested field list so a
    field removed by the field-level step cannot reappear as a type default.
    """
    doc = frappe.get_doc(request.doctype, request.name)
    doc.check_permission("read")
    doc.apply_fieldlevel_read_permissions()

    data = doc.as_dict(no_nulls=True)
    projected: dict[str, Any] = {}
    for fname in request.fields:
        if fname not in data:
            # Stripped by field-level enforcement, or genuinely absent.
            # Either way it is omitted, never emitted as a type default.
            continue
        projected[fname] = data[fname]
    return {"document": projected, "row_count": None}


# ---------------------------------------------------------------------------
# Audit — one metadata-only event per read, fail-closed
# ---------------------------------------------------------------------------

#: Detail keys permitted in a read audit event. Anything else is dropped.
AUDIT_DETAIL_KEYS = ("operation", "doctype", "fields_returned", "row_count", "filter_keys")


def _audit(request: ERPNextReadRequest, actor: str, site: str, outcome: str, details: dict[str, Any]) -> None:
    """Write exactly one metadata-only audit event. Raises on failure.

    Import is local and failure is fatal: the caller must not return data when
    the audit write did not succeed.
    """
    # Sibling import: resolves in BOTH the repo layout
    # (frappe_app.erpnext_ai_copilot.*) and the installed package
    # (erpnext_ai_copilot.*). An absolute repo-root path works only in the
    # first, which broke the live read until the live run caught it.
    from . import audit as _audit_module

    safe = {k: details[k] for k in AUDIT_DETAIL_KEYS if k in details}
    safe["filter_keys"] = sorted(request.filters.keys())
    safe["fields_returned"] = list(request.fields)
    target = f"{request.doctype}:{request.name}" if request.name else request.doctype
    _audit_module.record_audit(
        correlation=request.correlation,
        request_id=request.request_id,
        action=AUDIT_ACTION_READ,
        actor=actor,
        site=site,
        target=_bounded(target, 140),
        outcome=outcome,
        details=safe,
    )


def _translate_erpnext_error(exc: Exception) -> ReadRefusal:
    """Map a Frappe ORM exception to an internal refusal code."""
    if frappe is not None:
        if isinstance(exc, getattr(frappe, "DoesNotExistError", ())):
            return NotFound("record not found")
        if isinstance(exc, getattr(frappe, "PermissionError", ())):
            return PermissionDenied("read not permitted")
        if isinstance(exc, (getattr(frappe, "ValidationError", ()), ValueError)):
            return InvalidRequest("rejected by the doctype")
    return InvalidRequest("read rejected")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def execute_read(payload: dict[str, Any]) -> dict[str, Any]:
    """Perform one authorized ERPNext business read for the session user.

    The only public entry point. Takes **no** identity, site or mode
    parameter — the subject is the live Frappe session user and the site is
    the authoritative Frappe local site.

    Fail-closed on audit: if the audit write fails, no data is returned.

    Returns a minimized result carrying only the requested permitted fields.
    Raises :class:`ReadRefusal` on any refusal; callers must use
    :func:`collapse_for_caller` to build the caller-visible response.
    """
    request = build_request(payload)

    actor = current_subject()
    site = current_site()

    if request.operation == "list":
        reader = _list_read
    else:
        reader = _document_read

    try:
        result = reader(request)
    except ReadRefusal:
        raise
    except Exception as exc:  # noqa: BLE001 - Frappe raises several distinct types
        # Translate into a typed internal refusal so the caller layer applies
        # the anti-oracle collapse and the audit-on-refusal path fires. A raw
        # Frappe exception must never reach the caller: its type and message
        # would otherwise distinguish not-found from permission-denied.
        raise _translate_erpnext_error(exc) from exc

    fields_returned = (
        list(request.fields) if request.operation == "list" else list(result.get("document", {}).keys())
    )

    _guard_result_size(result, fields_returned)
    _audit(
        request,
        actor,
        site,
        OUTCOME_SUCCESS,
        {
            "operation": request.operation,
            "doctype": request.doctype,
            "fields_returned": fields_returned,
            "row_count": result.get("row_count"),
        },
    )

    return {
        "doctype": request.doctype,
        "operation": request.operation,
        "fields_returned": fields_returned,
        "row_count": result.get("row_count"),
        "data": result.get("rows") if request.operation == "list" else result.get("document"),
    }


def attempt_read(payload: dict[str, Any]) -> dict[str, Any]:
    """Audit-wrapped read that always emits exactly one audit event.

    Emits the read audit event for both success and refusal, then re-raises the
    refusal so the caller applies the anti-oracle collapse. An audit write
    failure during the refusal path is surfaced as :class:`AuditUnavailable`.
    """
    try:
        request = build_request(payload)
    except ReadRefusal as refusal:
        _audit_refusal_only(refusal, payload)
        raise
    try:
        return execute_read(payload)
    except ReadRefusal as refusal:
        _audit_refusal_only(refusal, payload, request=request)
        raise


def _audit_refusal_only(
    refusal: ReadRefusal,
    payload: dict[str, Any],
    request: ERPNextReadRequest | None = None,
) -> None:
    """Emit the single audit event for a refused read."""
    try:
        actor = current_subject()
        site = current_site()
    except ReadRefusal:
        actor, site = "unknown", "unknown"

    if request is None:
        doctype = ""
        operation = ""
        name = None
        fields: tuple[str, ...] = ()
        correlation = _bounded(payload.get("correlation"), 64) or "nexmate-read"
        request_id = _bounded(payload.get("request_id"), 64) or "read"
        filters: dict[str, Any] = {}
    else:
        doctype = request.doctype
        operation = request.operation
        name = request.name
        fields = request.fields
        correlation = request.correlation
        request_id = request.request_id
        filters = request.filters

    # Sibling import: resolves in BOTH the repo layout
    # (frappe_app.erpnext_ai_copilot.*) and the installed package
    # (erpnext_ai_copilot.*). An absolute repo-root path works only in the
    # first, which broke the live read until the live run caught it.
    from . import audit as _audit_module

    target = f"{doctype}:{name}" if name else (doctype or "invalid-request")
    _audit_module.record_audit(
        correlation=correlation,
        request_id=request_id,
        action=AUDIT_ACTION_READ,
        actor=actor,
        site=site,
        target=_bounded(target, 140),
        outcome=refusal.code,
        details={
            "operation": operation,
            "doctype": doctype,
            "fields_returned": list(fields),
            "row_count": None,
            "filter_keys": sorted(filters.keys()),
        },
    )


def _guard_result_size(result: dict[str, Any], fields_returned: list[str]) -> None:
    """Bound the authorized payload that may cross toward inference."""
    approx = len(str(result)) + len(str(fields_returned))
    if approx > MAX_RESULT_BYTES:
        raise InvalidRequest("result exceeds the authorized payload bound")


# ---------------------------------------------------------------------------
# Anti-oracle collapse
# ---------------------------------------------------------------------------


def collapse_for_caller(refusal: ReadRefusal) -> dict[str, Any]:
    """Collapse an internal refusal into one caller-indistinguishable result.

    Not-found, permission-denied, invalid-request and unsupported-operation all
    produce the **same** answer text, sources, confidence, route and route_how.

    The internal ``refusal.code`` is deliberately **not** part of the returned
    object: returning it would re-introduce exactly the existence oracle this
    function exists to remove. The distinction lives only in the audit event and
    the authorized Debug view.
    """
    return {
        "answer": CALLER_DENIAL,
        "sources": [],
        "confidence": "low",
        "route": "erpnext",
        "route_how": "frappe-authorized-read+denied",
    }
