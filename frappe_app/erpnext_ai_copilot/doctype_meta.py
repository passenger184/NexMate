"""Frappe-native, capability-gated, policy-governed DocType metadata access.

This is the control-plane enforcement point for DocType schema/metadata
requests made by an authenticated Desk user. It sits beside
``erpnext_read.py`` and is deliberately a **separate surface** from the
business-record read adapter:

* the sole authorization subject is ``frappe.session.user``;
* the **capability gate is evaluated first**, before any Frappe permission
  consultation, because Frappe's permission engine returns an unconditional
  allow for ``Administrator`` as its first check (``frappe/permissions.py``);
* ``frappe.has_permission(doctype, "read")`` is **not** part of this gate.
  Business-record authorization and metadata capability are different
  surfaces, and this module does not share the former's authorization;
* ``istable`` and ``issingle`` are immutable exclusions under every policy
  mode and are evaluated before the policy decision;
* the administrator-controlled **metadata access policy** is read uncached
  from ``NexMate Settings`` and fails closed;
* the projection is exactly five structural attributes and nothing else.

Security contract: see ``openspec/specs/doctype-schema-access`` and the
change's design decisions D4-D7, D12, D13.
"""

import json

try:  # pragma: no cover - exercised only inside a real Frappe process
	import frappe
except Exception:  # pragma: no cover - offline import guard
	frappe = None  # type: ignore[assignment]

SETTINGS_DOCTYPE = "NexMate Settings"


def _limits():
	"""The central limits module.

	Resolved late (like the ``api`` import below) so the single source of
	truth for administrator settings and immutable ceilings is shared rather
	than duplicated here. Offline harnesses register the real module under
	its full name; Frappe resolves the installed package.
	"""
	from erpnext_ai_copilot import policy_limits
	return policy_limits

#: Policy values. An unset/unsupported mode is not a third mode; it denies.
MODE_ALL = "all"
MODE_ALLOWLIST = "allowlist"
SUPPORTED_MODES = (MODE_ALL, MODE_ALLOWLIST)

#: The complete, closed projection. Nothing outside this tuple is returned,
#: so the response cannot drift into disclosing `options`, `permissions`, or
#: any other DocType document attribute.
PROJECTION_FIELDS = ("fieldname", "fieldtype", "label", "reqd", "read_only")

#: Bounds are administrator-configured within immutable ceilings; see
#: :mod:`policy_limits`. There are no fixed numeric bounds in this module:
#: every bound below resolves per decision from `NexMate Settings`.

#: Audit vocabulary. A dedicated action keeps metadata access distinguishable
#: from business-record access in the ledger. Outcomes reuse existing values.
AUDIT_ACTION_METADATA = "doctype_schema"
OUTCOME_SUCCESS = "success"
OUTCOME_NOT_FOUND = "not_found"
OUTCOME_PERMISSION_DENIED = "permission_denied"
OUTCOME_INVALID_REQUEST = "invalid_request"
OUTCOME_AUDIT_UNAVAILABLE = "audit_pending"

#: Internal refusal reasons. These exist for the audit event and authorized
#: debugging only. None of them may reach the caller (see
#: :func:`collapse_for_caller`).
CAPABILITY_DENIED = "capability_denied"
POLICY_DENIED = "policy_denied"
POLICY_UNAVAILABLE = "policy_unavailable"
ISTABLE = "istable"
ISSINGLE = "issingle"
NOT_FOUND = "not_found"
INVALID_REQUEST = "invalid_request"
OVERSIZED = "oversized"
AUDIT_UNAVAILABLE = "audit_unavailable"

#: The single caller-visible denial. Byte-identical for every refusal reason.
CALLER_DENIAL = "Schema not found or access denied."
CALLER_ROUTE_HOW = "frappe-schema+denied"

#: Detail keys permitted in a metadata audit event. Anything else is dropped.
AUDIT_DETAIL_KEYS = ("operation", "doctype", "field_count", "policy_mode")


class MetadataRefusal(Exception):
	"""Base for every metadata refusal.

	``code`` is the **internal** outcome. It is recorded in the audit event
	and never surfaced to the caller.
	"""

	code = OUTCOME_INVALID_REQUEST

	def __init__(self, reason: str = ""):
		self.reason = (reason or "")[:200]
		super().__init__(self.reason or self.code)


class CapabilityDenied(MetadataRefusal):
	code = CAPABILITY_DENIED


class PolicyDenied(MetadataRefusal):
	code = POLICY_DENIED


class PolicyUnavailable(MetadataRefusal):
	"""Policy absent, unset, unsupported, or unreadable. Fails closed."""

	code = POLICY_UNAVAILABLE


class NotStructurallyInspectable(MetadataRefusal):
	"""istable or issingle. An immutable exclusion under every policy mode."""

	code = OUTCOME_INVALID_REQUEST


class DocTypeNotFound(MetadataRefusal):
	code = OUTCOME_NOT_FOUND


class InvalidRequest(MetadataRefusal):
	code = OUTCOME_INVALID_REQUEST


class OversizedProjection(MetadataRefusal):
	code = OUTCOME_INVALID_REQUEST


class AuditUnavailable(MetadataRefusal):
	"""Audit write failed or was not confirmed durable. Fail closed."""

	code = OUTCOME_AUDIT_UNAVAILABLE


# ---------------------------------------------------------------------------
# Identity and capability
# ---------------------------------------------------------------------------


def current_subject() -> str:
	"""Return the sole authorization subject: the live Frappe session user.

	Never accepts an override, refuses absent and Guest sessions, and performs
	no normalization, repair, or case folding.
	"""
	if frappe is None:  # pragma: no cover - offline guard
		raise CapabilityDenied("no Frappe session")
	user = getattr(getattr(frappe, "session", None), "user", None)
	if not user or not isinstance(user, str) or user == "Guest":
		raise CapabilityDenied("authentication required")
	return user


def current_site() -> str:
	if frappe is None:  # pragma: no cover - offline guard
		raise CapabilityDenied("no Frappe session")
	site = getattr(getattr(frappe, "local", None), "site", None)
	if not site or not isinstance(site, str):
		raise InvalidRequest("no authoritative site")
	return site


def capability_for(user: str) -> str:
	"""Derive the live NexMate capability for ``user``.

	Fails closed to ``employee`` on malformed configuration or a role-lookup
	failure. This is the first authorization decision in the metadata path and
	is evaluated before any Frappe permission check, so the ``Administrator``
	bypass in the permission engine cannot short-circuit it.
	"""
	from . import api as _api

	return _api.capability_for_user(user)


# ---------------------------------------------------------------------------
# Administrator-controlled policy — uncached, fail-closed
# ---------------------------------------------------------------------------


def load_policy(doc=None):
	"""Read the site's metadata access policy, uncached.

	Returns ``{"mode": <supported mode>, "allowed": frozenset(...)}``. Raises
	:class:`PolicyUnavailable` for every ambiguous or unreadable state so the
	caller denies rather than guessing. There is no permissive default
	(design D7): a Single DocType that has never been saved is indistinguishable
	from one saved empty, so both must deny.

	Pass an already-loaded Settings record to avoid a second store read;
	``None`` (the default) reads it uncached here.
	"""
	if frappe is None:  # pragma: no cover - offline guard
		raise PolicyUnavailable("no Frappe session")

	if doc is None:
		try:
			# Uncached on purpose: a committed policy change must affect the very
			# next decision, and no stale policy may continue to grant access.
			doc = frappe.get_doc(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)
		except Exception:
			raise PolicyUnavailable("settings unavailable")

	mode = getattr(doc, "metadata_access_mode", None)
	if not isinstance(mode, str):
		raise PolicyUnavailable("mode is not a string")
	mode = mode.strip()
	if mode not in SUPPORTED_MODES:
		raise PolicyUnavailable("mode unset or unsupported")

	if mode == MODE_ALL:
		return {"mode": MODE_ALL, "allowed": frozenset()}

	try:
		rows = doc.get("metadata_doctype_rules") or []
	except Exception:
		raise PolicyUnavailable("rules unavailable")

	allowed = set()
	for row in rows:
		name = getattr(row, "target_doctype", None)
		if isinstance(name, str) and name.strip():
			allowed.add(name.strip())

	if not allowed:
		# allowlist with zero entries is an ambiguous configuration, not an
		# implicit "all". Deny.
		raise PolicyUnavailable("allowlist is empty")

	return {"mode": MODE_ALLOWLIST, "allowed": frozenset(allowed)}


def policy_permits(policy: dict, doctype: str) -> None:
	"""Raise :class:`PolicyDenied` unless the policy permits ``doctype``."""
	if policy.get("mode") == MODE_ALL:
		return
	if doctype in policy.get("allowed", frozenset()):
		return
	raise PolicyDenied("doctype is not permitted by the metadata access policy")


# ---------------------------------------------------------------------------
# Eligibility — immutable structural exclusions
# ---------------------------------------------------------------------------


def _eligible_meta(doctype: object) -> object:
	"""Resolve and structurally screen a DocType.

	Existence, ``istable`` and ``issingle`` are evaluated **before** the
	policy decision, so no policy value and no administrator mistake can admit
	a child table or a Single DocType.
	"""
	if not isinstance(doctype, str) or not doctype or len(doctype) > 140:
		raise InvalidRequest("doctype is required")
	doctype = doctype.strip()
	try:
		meta = frappe.get_meta(doctype)
	except Exception:
		# A nonexistent DocType collapses into the same external denial as
		# every other refusal, so the capability cannot be used to discover
		# which DocTypes a site defines.
		raise DocTypeNotFound("doctype does not exist")
	if getattr(meta, "istable", False):
		raise NotStructurallyInspectable("child doctypes are not inspectable")
	if getattr(meta, "issingle", False):
		raise NotStructurallyInspectable("single doctypes are not inspectable")
	return meta


# ---------------------------------------------------------------------------
# Projection — exactly five structural attributes
# ---------------------------------------------------------------------------


def project_meta(meta: object, max_fields=None) -> dict:
	"""Project DocType metadata to the fixed five-attribute shape.

	``options`` is deliberately absent: Select and Link field options are where
	a DocType document carries business vocabulary.

	``max_fields`` is the resolved effective field bound; when omitted it is
	resolved here from ``NexMate Settings`` within the immutable ceiling.
	"""
	if max_fields is None:
		max_fields, _max_bytes = _limits().effective_metadata_bounds()
	fields = []
	rows = getattr(meta, "fields", None) or []
	for field in rows:
		entry = {}
		for key in PROJECTION_FIELDS:
			if key == "fieldname":
				value = getattr(field, "fieldname", None)
			else:
				value = getattr(field, key, None)
			# Normalize only the flag types, never any business value.
			if key in ("reqd", "read_only") and isinstance(value, int):
				value = bool(value)
			elif value is None and key in ("reqd", "read_only"):
				value = False
			elif value is not None and key not in ("reqd", "read_only"):
				value = str(value)
			entry[key] = value
		fields.append(entry)

	if len(fields) > max_fields:
		raise OversizedProjection("projection exceeds the resolved field bound")

	return {"doctype": str(getattr(meta, "name", "") or ""), "fields": fields}


def guard_projection_size(payload: dict, max_bytes=None) -> None:
	"""Bound the payload that may cross toward inference. Refuse, never truncate.

	``max_bytes`` is the resolved effective byte bound; when omitted it is
	resolved here from ``NexMate Settings`` within the immutable ceiling.
	"""
	if max_bytes is None:
		_max_fields, max_bytes = _limits().effective_metadata_bounds()
	approx = len(json.dumps(payload, default=str))
	if approx > max_bytes:
		raise OversizedProjection("result exceeds the resolved payload bound")


# ---------------------------------------------------------------------------
# Audit — one metadata-only event, fail closed on the returned result
# ---------------------------------------------------------------------------


def _audit(actor: str, site: str, doctype: str, outcome: str, details: dict) -> None:
	"""Write exactly one metadata-only audit event.

	Fails closed. ``record_audit`` can return normally with
	``audit_pending=True`` when the Frappe insert fails and it falls back to a
	local file, so the **returned value** is inspected rather than trusting an
	exception. ``audit.py`` is deliberately not modified.
	"""
	from . import audit as _audit_module

	safe = {k: details[k] for k in AUDIT_DETAIL_KEYS if k in details}
	safe.setdefault("operation", "schema")
	safe.setdefault("doctype", doctype)

	entry = _audit_module.record_audit(
		correlation="nexmate-schema",
		request_id="schema",
		action=AUDIT_ACTION_METADATA,
		actor=actor,
		site=site,
		target=str(doctype or "")[:140],
		outcome=_audit_outcome(outcome),
		details=safe,
	)

	if not isinstance(entry, dict):
		raise AuditUnavailable("audit did not confirm a durable write")
	if entry.get("audit_pending"):
		raise AuditUnavailable("audit write is not durable")


def _audit_outcome(code: str) -> str:
	"""Map an internal reason onto the existing audit outcome vocabulary."""
	return {
		CAPABILITY_DENIED: OUTCOME_PERMISSION_DENIED,
		POLICY_DENIED: OUTCOME_PERMISSION_DENIED,
		POLICY_UNAVAILABLE: OUTCOME_INVALID_REQUEST,
		ISTABLE: OUTCOME_INVALID_REQUEST,
		ISSINGLE: OUTCOME_INVALID_REQUEST,
		NOT_FOUND: OUTCOME_NOT_FOUND,
		OVERSIZED: OUTCOME_INVALID_REQUEST,
		AUDIT_UNAVAILABLE: OUTCOME_AUDIT_UNAVAILABLE,
		OUTCOME_SUCCESS: OUTCOME_SUCCESS,
	}.get(code, OUTCOME_INVALID_REQUEST)


# ---------------------------------------------------------------------------
# Anti-oracle collapse
# ---------------------------------------------------------------------------


def collapse_for_caller(refusal: MetadataRefusal) -> dict:
	"""Collapse any metadata refusal into one caller-indistinguishable result.

	Mirrors the ``erpnext_read`` discipline, with its own wording and its own
	route marker so a metadata refusal is never labelled a business-record
	refusal. The internal ``refusal.code`` is deliberately absent from the
	returned object; it lives only in the audit event.
	"""
	return {
		"answer": CALLER_DENIAL,
		"sources": [],
		"confidence": "low",
		"route": "erpnext",
		"route_how": CALLER_ROUTE_HOW,
	}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def attempt_metadata(payload: dict) -> dict:
	"""Authorize and serve one metadata request for the session user.

	Authorization order, exactly: capability -> existence -> structural
	exclusion -> policy. On any refusal, exactly one audit event is written and
	the caller receives a single collapsed denial.

	Returns the minimized projection. Raises :class:`MetadataRefusal` on any
	refusal; callers must use :func:`collapse_for_caller`.
	"""
	if not isinstance(payload, dict):
		raise InvalidRequest("request must be an object")

	actor = current_subject()
	site = current_site()
	doctype = payload.get("doctype")

	try:
		# 1. Capability FIRST, before any Frappe permission consultation, so
		#    the Administrator bypass cannot short-circuit the gate.
		if capability_for(actor) != "developer":
			raise CapabilityDenied("developer capability is required")

		# 2. Existence, then 3. immutable structural exclusions.
		meta = _eligible_meta(doctype)
		doctype = str(getattr(meta, "name", doctype) or doctype)

		# One uncached settings read serves both the policy and the numeric
		# bounds below, so a single decision observes a single stored state.
		settings_doc = _limits().read_settings_doc()

		# 4. Administrator-controlled policy, uncached, fail-closed.
		policy = load_policy(settings_doc)
		policy_permits(policy, doctype)

		# 5. Projection and resolved effective bounds.
		max_fields, max_bytes = _limits().effective_metadata_bounds(settings_doc)
		projection = project_meta(meta, max_fields)
		guard_projection_size(projection, max_bytes)
	except MetadataRefusal as refusal:
		# Exactly one audit event per resolution, refusals included. Auditing is
		# not retrieval: no metadata was produced to reach this point.
		_audit_actor_or_unknown(actor, site, doctype, refusal.code)
		raise

	_audit(
		actor,
		site,
		doctype,
		OUTCOME_SUCCESS,
		{"operation": "schema", "doctype": doctype,
		 "field_count": len(projection["fields"]), "policy_mode": policy["mode"]},
	)
	return projection


def _audit_actor_or_unknown(actor: str, site: str, doctype, code: str) -> None:
	"""Emit the single audit event for a refused metadata request."""
	try:
		_audit(actor, site, doctype if isinstance(doctype, str) else "", code,
			   {"operation": "schema",
				"doctype": doctype if isinstance(doctype, str) else ""})
	except MetadataRefusal:
		# An audit failure on the refusal path must not change the
		# caller-visible outcome; it is surfaced internally by the caller.
		pass


def metadata_context(request_id: str = "0") -> dict:
	"""Shape a permitted projection for the authorized-context channel.

	Mirrors the business-read context shape but declares its own operation, so
	the consumer can accept it without weakening the business-read bounds.
	"""
	request = dict(request_id=str(request_id))
	payload = dict(request)
	try:
		projection = attempt_metadata(payload)
	except MetadataRefusal as refusal:
		return {"_denied": collapse_for_caller(refusal)}
	return {
		"_context": {
			"doctype": projection["doctype"],
			"operation": "schema",
			"field_count": len(projection["fields"]),
			"fields": projection["fields"],
		}
	}
