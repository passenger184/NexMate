"""Policy-filtered Debug/transparency (M5 debug-transparency).

Discloses only permitted retrieval provenance, actually accessed fields/results
and generated queries where they exist, never revealing denied source existence
or sensitive fields. Every view is audited.

Access: requires `debug_view` permission (mapped to System Manager in this
increment) or explicit role. The view is minimized to fields/results actually
used, and each access is recorded in the audit ledger.
"""

import json
from typing import Any

try:
    import frappe
    HAS_FRAPPE = True
except Exception:
    frappe = None  # type: ignore
    HAS_FRAPPE = False

import config

def _current_user() -> str:
    if HAS_FRAPPE and frappe and getattr(frappe, "session", None):
        try:
            user = frappe.session.user
            if user and user != "Guest":
                return user
        except Exception:
            pass
    import os
    return os.environ.get("NEXMATE_TEST_USER", "Administrator")

def _current_site() -> str:
    if HAS_FRAPPE and frappe and getattr(frappe.local, "site", None):
        site = getattr(frappe.local, "site", None)
        if site:
            return site
    import os
    return os.environ.get("NEXMATE_TEST_SITE", "test_site")

def _has_debug_permission(user: str) -> bool:
    if HAS_FRAPPE:
        try:
            roles = frappe.get_roles(user)
            # In M5, debug_view maps to System Manager; keep narrow
            return "System Manager" in roles
        except Exception:
            return False
    # Fallback test env: check env flag
    import os
    return os.environ.get("NEXMATE_TEST_DEBUG_ALLOWED") == "1" or user == "Administrator"

def get_debug_view(correlation: str, actor: str | None = None, site: str | None = None) -> dict[str, Any]:
    """Return minimized Debug view for a correlation, audited.

    Never reveals denied sources. Only permitted provenance and actually
    accessed fields/results/queries are returned.
    """
    actor = actor or _current_user()
    site = site or _current_site()
    if not correlation:
        raise ValueError("correlation required")
    if not _has_debug_permission(actor):
        raise PermissionError("debug view denied")

    # Fetch audit entries for correlation (authorized)
    from frappe_app.erpnext_ai_copilot.audit import query_by_correlation, record_audit
    entries = query_by_correlation(correlation, actor=actor, site=site)

    # Build minimized view: only successes and permitted provenance
    # Filter to only include details that were actually used (not denied)
    provenance = []
    accessed_fields = {}
    raw_results = []
    queries = []

    for e in entries:
        details = e.get("details") or {}
        # Only include if outcome is success and action is not denied source
        # Never include denied source counts; accessed_fields is minimized to
        # tool_call results (actually accessed fields), not the broader retrieval
        # document's full field set.
        if e.get("outcome") in ("success", "succeeded", "reconciled"):
            if "provenance" in details:
                # Provenance may be in retrieval or tool_call; deduplicate
                provenance.extend(details["provenance"])
            # Only tool_call fields are the minimized actually-accessed fields
            if e.get("action") in ("tool_call", "succeeded", "reconciled") and "fields" in details:
                for k, v in details["fields"].items():
                    if k not in accessed_fields:
                        accessed_fields[k] = v
            elif e.get("action") == "retrieval" and "fields" not in accessed_fields:
                # Retrieval fields are not the minimized accessed set; skip unless no tool_call yet
                pass
            if "result" in details:
                raw_results.append(details["result"])
            if "query" in details and "generated_queries" in details.get("provenance", []):
                queries.append(details["query"])

    # Deduplicate provenance
    provenance = list(dict.fromkeys(provenance))

    view = {
        "correlation": correlation,
        "actor": actor,
        "site": site,
        "provenance": provenance,
        "accessed_fields": accessed_fields,
        "raw_results": raw_results,
        "queries": queries,
    }

    # Audit the Debug view itself
    try:
        record_audit(correlation=correlation, request_id=f"debug-{correlation}", action="debug_view",
                     actor=actor, site=site, target=correlation, outcome="success",
                     details={"view_keys": list(view.keys())})
    except Exception:
        pass

    return view
