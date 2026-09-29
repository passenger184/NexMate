"""Administrator-controlled NexMate configuration (Single DocType).

This record holds the **metadata access policy**: which DocTypes a
Developer-capability user may inspect. It is deliberately the only
Desk-editable NexMate configuration surface.

Two boundaries are enforced here, and both matter:

* **Configuration authority is not capability.** Holding the Developer
  capability grants no write access to this record; holding write access
  grants no metadata access. Authorization is the metadata module's job.
* **The policy fails closed.** An unset, unsupported, or unreadable value
  denies metadata access. This module never supplies a permissive default;
  the authorization decision lives in ``doctype_meta``, which resolves the
  mode itself and denies when it cannot.
"""

import frappe
from frappe.model.document import Document
from frappe import _

#: Supported policy values. ``None``/empty is deliberately absent: it is an
#: invalid configuration that must deny, not a third mode.
SUPPORTED_METADATA_ACCESS_MODES = ("all", "allowlist")


class NexMateSettings(Document):
	"""Site-wide NexMate administrator configuration."""

	def validate(self):
		self._validate_metadata_access_mode()
		self._validate_no_duplicate_rules()
		self._validate_rules_are_inspectable()
		self._validate_numeric_limits()

	def _validate_metadata_access_mode(self):
		mode = (self.metadata_access_mode or "").strip()
		if mode and mode not in SUPPORTED_METADATA_ACCESS_MODES:
			frappe.throw(
				_("Unsupported metadata access mode {0}.").format(mode),
				title=_("Invalid NexMate Settings"),
			)

	def _validate_numeric_limits(self):
		"""Persist the documented default for every unset numeric limit, then
		refuse anything an administrator configured outside its range.

		Two boundaries, in this order. First, an unset field is filled with its
		documented default: Frappe materialises an untouched ``Int`` on a
		Single as ``0`` on the write path, so leaving it unset would store a
		value the ranges reject on the next save and that the runtime would
		mistake for configured. Second, whatever the administrator actually
		configured must be an integer inside the field's supported range; an
		explicit ``0`` or ``501`` is refused.

		Unset and blank values are never treated as invalid input — only as
		unconfigured. The ranges live in ``policy_limits`` as the single source
		of truth; this controller only wires them into save-time validation and
		normalisation. The import is local so module load stays side-effect
		free; in Frappe runtime the package is always importable.
		"""
		from erpnext_ai_copilot.policy_limits import (
			normalise_numeric_settings,
			validate_numeric_settings,
		)
		normalise_numeric_settings(
			lambda name: getattr(self, name, None),
			lambda name, value: self.set(name, value),
		)
		validate_numeric_settings(
			lambda name: getattr(self, name, None),
			lambda message: frappe.throw(
				message, title=_("Invalid NexMate Settings")),
		)

	def _validate_no_duplicate_rules(self):
		seen = set()
		duplicates = []
		for row in self.metadata_doctype_rules or []:
			name = (row.target_doctype or "").strip()
			if not name:
				continue
			if name in seen:
				duplicates.append(name)
			seen.add(name)
		if duplicates:
			frappe.throw(
				_("Duplicate permitted DocTypes: {0}").format(
					", ".join(sorted(set(duplicates)))
				),
				title=_("Invalid NexMate Settings"),
			)

	def _validate_rules_are_inspectable(self):
		"""Refuse child-table and Single DocTypes at the parent level.

		The child controller carries the same check, but Frappe does not
		invoke a child row's ``validate()`` when the parent Single is saved,
		so the parent must enforce it. Either way the authorization-time
		exclusion in ``doctype_meta`` would still refuse the DocType; this
		keeps an unhonourable entry from ever being stored.
		"""
		for row in self.metadata_doctype_rules or []:
			name = (row.target_doctype or "").strip()
			if not name:
				continue
			try:
				meta = frappe.get_meta(name)
			except Exception:
				# Link validation already requires existence; a DocType that
				# vanished mid-save is refused rather than stored.
				frappe.throw(
					_("{0} is not a resolvable DocType.").format(name),
					title=_("Invalid NexMate Settings"),
				)
			if getattr(meta, "istable", False):
				frappe.throw(
					_("Child table {0} cannot be inspected by NexMate metadata.").format(
						name
					),
					title=_("Invalid NexMate Settings"),
				)
			if getattr(meta, "issingle", False):
				frappe.throw(
					_("Single DocType {0} cannot be inspected by NexMate metadata.").format(
						name
					),
					title=_("Invalid NexMate Settings"),
				)
