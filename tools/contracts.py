"""Explicit authorized tool contracts (M5 durable-tool-execution).

Every tool entry point has a validated, bounded contract. The contract is the
single source of truth for the proposal record fields, the durable lifecycle,
and the audit ledger. See design.md D0-D7 and specs/durable-tool-execution.

Tool contract schema (frozen for M5):
  operation         — one of the keys in CONTRACTS (e.g., code_edit, business_write)
  validated inputs  — bounded JSON schema for the operation
  permission        — required Frappe permission check (e.g., System Manager, or DocType write)
  context           — required scope/authorization (site, actor, scope)
  side_effect       — read | write | code_write
  approval_required — bool (writes require durable approval)
  typed_errors      — mapping of refusal categories
  timeout           — seconds (bounded)
  provenance        — what is recorded in audit
  audit_event       — audit action name

Proposal record fields (frozen, must match design.md D0 and specs):
  operation, target, payload|diff, reason, actor, site, correlation,
  expiry, preconditions, status, plus immutable payload_hash.
  See PROPOSAL_FIELDS and PROPOSAL_STATUSES below.
"""

from typing import Any

# Proposal record fields (frozen). Any change here is a new proposal, not an edit.
PROPOSAL_FIELDS = (
    "operation",
    "target",
    "payload",
    "diff_preview",
    "reason",
    "actor",
    "site",
    "correlation",
    "expiry",
    "preconditions",
    "payload_hash",
    "status",
    "approver",
    "executed_at",
)

PROPOSAL_STATUSES = (
    "pending",
    "approved",
    "rejected",
    "executing",
    "succeeded",
    "failed",
    "denied",
    "uncertain",
    "reconciled",
    "audit_pending",
    "conflicting",
    "expired",
)

# Locking: advisory key is the target string (DocType:Name or file path)
# plus site, to make it site-isolated.
def advisory_lock_key(site: str, target: str) -> str:
    return f"{site}:{target}"

# Explicit tool contracts — bounded, no SQL tool.
CONTRACTS: dict[str, dict[str, Any]] = {
    "code_edit": {
        "operation": "code_edit",
        "side_effect": "code_write",
        "approval_required": True,
        "permission": "System Manager",
        "context": ("actor", "site", "scope"),
        "bounded_inputs": {
            "path": {"type": "string", "maxLength": 1024},
            "find": {"type": "string", "minLength": 1},
            "replace": {"type": "string"},
            "message": {"type": "string", "minLength": 10},
            "context": {"type": "string", "maxLength": 2000},
        },
        "bounded_outputs": {
            "proposal_id": {"type": "string"},
            "path": {"type": "string"},
            "diff": {"type": "string"},
        },
        "typed_errors": (
            "outside_root",
            "untracked_file",
            "ignored_file",
            "dirty_tree",
            "ambiguous_match",
            "bad_message",
            "unknown_proposal",
            "expired_proposal",
            "stale_proposal",
            "not_owned",
            "site_mismatch",
            "permission_denied",
            "conflicting",
            "uncertain",
        ),
        "timeout_seconds": 30,
        "provenance": ("proposal", "approval", "commit_hash"),
        "audit_event": "tool_call",
    },
    "business_write": {
        "operation": "business_write",
        "side_effect": "write",
        "approval_required": True,
        "permission": "System Manager",
        "context": ("actor", "site", "scope"),
        "bounded_inputs": {
            "doctype": {"type": "string", "maxLength": 255},
            "action": {"type": "string", "enum": ["create", "update"]},
            "name": {"type": "string", "maxLength": 255},
            "fields": {"type": "object"},
            "reason": {"type": "string", "minLength": 5},
        },
        "bounded_outputs": {
            "proposal_id": {"type": "string"},
            "doctype": {"type": "string"},
            "payload_preview": {"type": "object"},
        },
        "typed_errors": (
            "invalid_doctype",
            "invalid_fields",
            "permission_denied",
            "not_owned",
            "site_mismatch",
            "unknown_proposal",
            "expired_proposal",
            "stale_target",
            "conflicting",
            "uncertain",
        ),
        "timeout_seconds": 30,
        "provenance": ("proposal", "approval", "docname"),
        "audit_event": "tool_call",
    },
    "read_file": {
        "operation": "read_file",
        "side_effect": "read",
        "approval_required": False,
        "permission": None,
        "context": ("actor", "site"),
        "bounded_inputs": {
            "path": {"type": "string", "maxLength": 1024},
        },
        "bounded_outputs": {"content": {"type": "string"}},
        "typed_errors": ("outside_root", "not_found", "binary_file"),
        "timeout_seconds": 10,
        "provenance": ("path",),
        "audit_event": "retrieval",
    },
    "search": {
        "operation": "search",
        "side_effect": "read",
        "approval_required": False,
        "permission": None,
        "context": ("actor", "site"),
        "bounded_inputs": {"pattern": {"type": "string"}},
        "bounded_outputs": {"results": {"type": "array"}},
        "typed_errors": ("bad_pattern",),
        "timeout_seconds": 10,
        "provenance": ("pattern",),
        "audit_event": "retrieval",
    },
    "erpnext_read": {
        "operation": "erpnext_read",
        "side_effect": "read",
        "approval_required": False,
        "permission": None,
        "context": ("actor", "site", "scope"),
        "bounded_inputs": {
            "doctype": {"type": "string"},
            "name": {"type": "string"},
            "filters": {"type": "object"},
            "limit": {"type": "integer", "maximum": 100},
        },
        "bounded_outputs": {"data": {"type": "object"}},
        "typed_errors": ("not_found", "permission_denied"),
        "timeout_seconds": 15,
        "provenance": ("doctype", "filters"),
        "audit_event": "retrieval",
    },
}

def contract_for(operation: str) -> dict[str, Any]:
    if operation not in CONTRACTS:
        raise ValueError(f"Unknown tool operation {operation!r}")
    return CONTRACTS[operation]

def validate_bounded_inputs(operation: str, payload: dict[str, Any]) -> None:
    contract = contract_for(operation)
    for key, rule in contract["bounded_inputs"].items():
        if key not in payload:
            if rule.get("required", False):
                raise ValueError(f"Missing bounded input {key!r}")
            continue
        val = payload[key]
        if rule.get("type") == "string":
            if not isinstance(val, str):
                raise ValueError(f"Input {key!r} must be string")
            if "maxLength" in rule and len(val) > rule["maxLength"]:
                raise ValueError(f"Input {key!r} exceeds maxLength")
            if "minLength" in rule and len(val) < rule["minLength"]:
                raise ValueError(f"Input {key!r} below minLength")
            if "enum" in rule and val not in rule["enum"]:
                raise ValueError(f"Input {key!r} must be one of {rule['enum']}")
        elif rule.get("type") == "integer":
            if not isinstance(val, int):
                raise ValueError(f"Input {key!r} must be integer")
            if "maximum" in rule and val > rule["maximum"]:
                raise ValueError(f"Input {key!r} exceeds maximum")
        elif rule.get("type") == "object":
            if not isinstance(val, dict):
                raise ValueError(f"Input {key!r} must be object")
        elif rule.get("type") == "array":
            if not isinstance(val, list):
                raise ValueError(f"Input {key!r} must be array")
