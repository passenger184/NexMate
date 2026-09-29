"""One administrator-configured Frappe Role conferring NexMate Developer capability.

The row carries a Role reference and nothing else. Existence and exact naming
are enforced by the framework's Link validation. A name that no longer exists
as a Frappe Role simply never matches a live role lookup, so it can never
grant capability. Duplicate rows are harmless under any-match semantics.
"""

import frappe
from frappe.model.document import Document


class NexMateDeveloperRoleRule(Document):
	"""A single developer-role entry: one Role name, nothing else."""
