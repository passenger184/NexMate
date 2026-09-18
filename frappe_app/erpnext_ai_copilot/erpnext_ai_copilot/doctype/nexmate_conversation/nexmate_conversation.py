import frappe
from frappe.model.document import Document


class NexMateConversation(Document):
    """Owned conversation thread (see conversations.py for access rules)."""
