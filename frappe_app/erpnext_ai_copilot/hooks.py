app_name = "erpnext_ai_copilot"
app_title = "ERPNext AI Copilot"
app_publisher = "ERPNext AI Copilot contributors"
app_description = "Sidebar AI assistant for ERPNext/Frappe developer questions with durable tool execution and audit"
app_email = "nexmate@example.invalid"
app_license = "MIT"

# Include the sidebar chat panel in the Desk shell. The bundle is built by
# `bench build --app erpnext_ai_copilot` from public/js/copilot.bundle.js.
app_include_js = "copilot.bundle.js"
app_include_css = "copilot.css"

# Configuration-change auditing for the administrator-controlled metadata
# access policy. Frappe's `Version` (track_changes on the DocType) captures
# the field and child-row diff; this hook adds a NexMate audit event so a
# policy change is queryable in the same ledger as metadata access itself.
#
# Permission Log is deliberately NOT relied upon: it is opt-in per DocType via
# `get_permission_log_options`, and its diff excludes child-table content, so
# it cannot record allowlist row changes.
doc_events = {
    "NexMate Settings": {
        "on_update": [
            "erpnext_ai_copilot.settings_audit.log_settings_change",
        ],
    },
}

# Expose the FastAPI service address to the client via frappe.boot —
# the value comes from site_config.json key `copilot_api_base`.
extend_bootinfo = "erpnext_ai_copilot.boot.boot_session"
