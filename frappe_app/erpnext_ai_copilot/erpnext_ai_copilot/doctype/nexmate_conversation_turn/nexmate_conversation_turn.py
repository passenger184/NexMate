import frappe
from frappe.model.document import Document


class NexMateConversationTurn(Document):
    """One chat turn inside a NexMate conversation."""
