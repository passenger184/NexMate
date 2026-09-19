import frappe
from frappe.model.document import Document


class NexMateToolProposal(Document):
    """Durable tool proposal — Frappe owns lifecycle, see proposals.py for access rules."""
