app_name = "erpnext_ai_copilot"
app_title = "ERPNext AI Copilot"

# Include the sidebar chat panel in the Desk shell. The bundle is built by
# `bench build --app erpnext_ai_copilot` from public/js/copilot.bundle.js.
app_include_js = "copilot.bundle.js"
app_include_css = "copilot.css"

# Expose the FastAPI service address to the client via frappe.boot —
# the value comes from site_config.json key `copilot_api_base`.
extend_bootinfo = "erpnext_ai_copilot.boot.boot_session"
