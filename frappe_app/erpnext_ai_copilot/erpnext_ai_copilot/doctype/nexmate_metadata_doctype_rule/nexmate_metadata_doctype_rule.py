"""One administrator-configured DocType permitted for NexMate metadata access.

The row carries a DocType reference and nothing else. Existence and exact
naming are enforced by the framework's Link validation; the structural
exclusions and duplicates are enforced here (design D4, tasks 2.1-2.4).

``istable``/``issingle`` are immutable exclusions for the metadata capability
(design D6) and are therefore refused at configuration time as well as at
authorization time, so no administrator can save an entry that can never be
honoured.
"""

import frappe
from frappe.model.document import Document
from frappe import _


class NexMateMetadataDocTypeRule(Document):
	"""A single allowlist entry: one DocType name, no field-level data."""

	def validate(self):
		self._validate_not_child_table()
		self._validate_not_single()

	def _validate_not_child_table(self):
		try:
			meta = frappe.get_meta(self.target_doctype)
		except Exception:
			# Link validation already requires the DocType to exist. Reaching
			# here means it vanished between validation and this hook; refuse
			# rather than store an unresolvable entry.
			frappe.throw(
				_("{0} is not a resolvable DocType.").format(self.target_doctype),
				title=_("Invalid metadata rule"),
			)
		if getattr(meta, "istable", False):
			frappe.throw(
				_("Child table {0} cannot be inspected by NexMate metadata.").format(
					self.target_doctype
				),
				title=_("Invalid metadata rule"),
			)

	def _validate_not_single(self):
		try:
			meta = frappe.get_meta(self.target_doctype)
		except Exception:
			return  # already reported by _validate_not_child_table
		if getattr(meta, "issingle", False):
			frappe.throw(
				_("Single DocType {0} cannot be inspected by NexMate metadata.").format(
					self.target_doctype
				),
				title=_("Invalid metadata rule"),
			)
