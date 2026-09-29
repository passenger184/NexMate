"""Audit hook for administrator changes to the NexMate metadata access policy.

Frappe's ``Version`` (via ``track_changes``) captures the field and child-row
diff of the settings record. This hook additionally records a NexMate audit
event so a policy change is queryable through the same ledger as metadata
access itself, and so an operator can answer "who widened metadata access, when,
and from which mode to which".

Only security-relevant configuration facts are recorded: the mode transition
and the count of configured DocTypes. DocType names are structural rather than
business data, and the full list is already durably captured by ``Version``, so
the event does not duplicate it.
"""

import logging

try:  # pragma: no cover - exercised only inside a real Frappe process
	import frappe
except Exception:  # pragma: no cover - offline import guard
	frappe = None  # type: ignore[assignment]

logger = logging.getLogger("nexmate.settings_audit")

SETTINGS_DOCTYPE = "NexMate Settings"
AUDIT_ACTION_POLICY_CHANGE = "security_event"
OUTCOME_SUCCESS = "success"

MODE_KEY = "metadata_access_mode"
RULES_FIELD = "metadata_doctype_rules"


def _rule_names(doc) -> list[str]:
	try:
		rows = doc.get(RULES_FIELD) or []
	except Exception:
		return []
	names = []
	for row in rows:
		name = getattr(row, "target_doctype", None)
		if isinstance(name, str) and name.strip():
			names.append(name.strip())
	return sorted(set(names))


def _previous_state(doc):
	"""Best-effort previous mode from the pre-save snapshot.

	``get_doc_before_save()`` is the document as it stood before this save,
	so its mode is exactly the previous mode. Reading the latest ``Version``
	row instead would be off by one: at ``on_update`` time the current save's
	version row does not exist yet, so the latest row belongs to the previous
	save.
	"""
	try:
		before = doc.get_doc_before_save()
	except Exception:
		return None
	if before is None:
		return None
	try:
		return (before.get(MODE_KEY) or "").strip() or None
	except Exception:
		return None


def log_settings_change(doc=None, method=None) -> None:
	"""Record a NexMate audit event for a settings save.

	Wired through ``doc_events`` in ``hooks.py``. Never raises: an audit hook
	must not block the administrator's save, and the failure is surfaced by
	logging rather than silently swallowed.
	"""
	if frappe is None:  # pragma: no cover - offline guard
		return
	try:
		if doc is None or getattr(doc, "doctype", None) != SETTINGS_DOCTYPE:
			return

		from . import audit as _audit_module

		mode = (getattr(doc, MODE_KEY, None) or "").strip()
		names = _rule_names(doc)
		previous_mode = _previous_state(doc)

		details = {
			"operation": "metadata_policy_change",
			"previous_mode": previous_mode or "",
			"new_mode": mode,
			"configured_doctype_count": len(names),
		}

		_audit_module.record_audit(
			correlation="nexmate-settings",
			request_id=str(getattr(doc, "name", "settings"))[:40],
			action=AUDIT_ACTION_POLICY_CHANGE,
			actor=frappe.session.user,
			site=getattr(frappe.local, "site", ""),
			target=SETTINGS_DOCTYPE,
			outcome=OUTCOME_SUCCESS,
			details=details,
		)
	except Exception:
		logger.warning("settings_policy_audit_failed")
