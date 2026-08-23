"""Manually written reference answers for the EVALUATION.md question set.

Used only by the evaluation harness (context precision needs a reference to
compare retrieved contexts against). Every reference is grounded in pages
that exist in this project's corpus — they describe what a correct answer
must cover, not polished prose.
"""

REFERENCES: dict[str, str] = {
    "How do I create a custom DocType?": (
        "Type 'DocType List' in the awesomebar and click New. Give the DocType "
        "a name (always singular), choose a Module, add fields in the Fields "
        "table (label + type), set naming (e.g. field: or autoincrement), and "
        "Save. Frappe creates the database table and API for it automatically."
    ),
    "How does frappe.whitelist work?": (
        "@frappe.whitelist() is a decorator that marks a Python method as "
        "callable over HTTP. A whitelisted method becomes reachable at "
        "/api/method/dotted.path.to.method (and can be invoked from the "
        "client with frappe.call). Without the decorator, methods are not "
        "exposed via the REST/RPC API."
    ),
    "How do I override a controller in ERPNext?": (
        "Use the override_doctype_class hook in your app's hooks.py to "
        "replace a DocType's standard controller class with your own subclass "
        "(your class must inherit from the original controller). Note: only "
        "the last app's override applies when multiple apps override the "
        "same class."
    ),
    "How do I create a server script?": (
        "As System Manager, type 'New Server Script' in the awesomebar. Set "
        "Script Type (Document Event, API, etc.), for Document Event pick the "
        "DocType and event (e.g. Before Save), write Python in the editor, "
        "and Enable+Save. Server Scripts run server-side without deploying "
        "a custom app."
    ),
    "How do I create a custom app?": (
        "From the frappe-bench directory run `bench new-app <app_name>`, fill "
        "in app title/description/publisher/etc., then install it on the site "
        "with `bench --site <sitename> install-app <app_name>`. The app "
        "skeleton lives under apps/<app_name> with hooks.py for configuration."
    ),
    "What hook should I use to run code after a document is saved?": (
        "Use doc_events in hooks.py mapping the DocType (or '*') to "
        "'on_update', which fires after a document is saved; handler "
        "functions receive the document. (on_update runs on every save after "
        "insert; on_submit additionally exists for submittable docs.)"
    ),
    "How do I safely migrate a customization to a new ERPNext version?": (
        "Keep customizations in a custom app rather than editing core: use "
        "Customize Form's 'Export Customizations' (exports custom fields and "
        "property setters into the app), keep code overrides in hooks.py, "
        "test on a staging/migrated copy before upgrading production, and "
        "follow release-notes breaking changes. Avoid direct core edits so "
        "migrations don't clobber them."
    ),
    "How do I add a custom field to an existing DocType?": (
        "Go to the Custom Field list, click New, select the target DocType "
        "under Document, enter Label and Field Type, optionally set Insert "
        "After / dependencies, then save (Update). Custom fields survive "
        "upgrades and can be exported with Customize Form > Export "
        "Customizations."
    ),
    "What's the difference between a Server Script and a Client Script?": (
        "A Client Script is JavaScript executed in the user's browser to "
        "customize form UX/validation in real time. A Server Script is "
        "Python executed server-side (document events/API), so it also "
        "enforces rules when documents change via API, not just through the "
        "form. Client Script validations alone are not applied on API-driven "
        "changes."
    ),
    "How do I create a REST API endpoint for a custom DocType?": (
        "Standard CRUD comes free: any DocType is exposed at "
        "/api/resource/{doctype} with GET/POST/PUT/DELETE honoring "
        "permissions. For custom logic endpoints, write a Python method "
        "decorated with @frappe.whitelist() and call it at "
        "/api/method/dotted.path.to.method."
    ),
    "How do child tables work in Frappe?": (
        "Create a DocType with Is Child Table checked; in the parent "
        "DocType add a field of type Table with Options set to the child "
        "DocType. Rows are stored per parent record (linked via parent, "
        "parenttype, parentfield columns) and edited inside the parent's "
        "form; in scripts you access them via the parent doc's fieldname."
    ),
    "How do I set up a scheduled/background job in Frappe?": (
        "For scheduled jobs define scheduler_events in hooks.py (e.g. cron, "
        "hourly, daily) mapping to functions in your app — the scheduler "
        "worker triggers them. For one-off background work use "
        "frappe.enqueue(fn, queue=..., timeout=...) which runs the job on a "
        "background worker instead of the web request."
    ),
    "How do permissions work for a custom DocType?": (
        "Permissions are role-based: each DocType has a permission matrix "
        "granting roles read/write/create/delete/submit/cancel/amend at a "
        "permission level (0 default); ifield-level permissions exist too. "
        "Users get permissions from their Roles. Custom logic can hook via "
        "permission_query_conditions and has_permission hooks."
    ),
    "What's the correct way to query the database in a Frappe app (ORM vs raw SQL)?": (
        "Prefer the ORM: frappe.get_doc, frappe.get_all/frappe.get_list "
        "(permission-aware), frappe.db.get_value/set_value, and the "
        "frappe.qb query builder. Use frappe.db.sql only when raw SQL is "
        "genuinely needed, always with parameterized values (%(param)s) to "
        "avoid injection — never string-format values into SQL."
    ),
    "How do I debug a validation error on document submit?": (
        "Read the raised message/traceback: the UI shows the msgprint "
        "message; full tracebacks land in the Error Log. Reproduce outside "
        "the browser with bench --site sitename console (get_doc(...)."
        "submit()) or enable developer mode to inspect hooks/scripts that "
        "run on validate/before_submit/on_submit and find the raising check."
    ),
}
