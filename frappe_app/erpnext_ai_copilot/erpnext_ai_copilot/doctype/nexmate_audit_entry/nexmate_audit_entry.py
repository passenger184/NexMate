import frappe
from frappe.model.document import Document


class NexMateAuditEntry(Document):
    """Correlated audit ledger entry — see audit.py for access and redaction."""
