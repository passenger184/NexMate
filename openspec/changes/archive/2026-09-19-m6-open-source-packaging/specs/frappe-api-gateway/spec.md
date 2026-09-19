## ADDED Requirements

### Requirement: Installation does not regress gateway authentication and proposal flows
The `bench get-app`/`install-app`/`migrate` packaging change SHALL NOT regress `frappe-api-gateway` authentication, site binding, or durable proposal flows. After a fresh installation, `frappe-api-gateway` SHALL still enforce `Frappe` session `non-Guest`, `frappe.local.site` validated, `X-NexMate-Key` service authentication on `POST /api/method/erpnext_ai_copilot.api.create_tool_proposal` etc., and `actor/site` derived from `Frappe` (never browser `actor`/`site` fields).

#### Scenario: Gateway still enforced after fresh install
- **WHEN** a fresh-installed site handles `POST /api/method/erpnext_ai_copilot.api.create_tool_proposal` with `Guest` or with browser-supplied `actor` field
- **THEN** it is refused with `unsupported_gateway_fields` or `Authentication required` before any proposal is created, and no `tabNexMate Tool Proposal` row is created

### Requirement: Gateway scope remains Frappe-derived after packaging
After installation, retrieval `scope` (`site`, `tiers`, `roles`, `derived_by`) SHALL still be derived from `frappe.get_roles(user)` via `frappe_app/erpnext_ai_copilot/api.py:_authz_scope`, not from client `mode` or `scope` fields, and shall be validated before `retriever.retrieve`.

#### Scenario: Scope still server-derived after fresh install
- **WHEN** a fresh-installed site's `Administrator` with `System Manager` role calls `ask` via `Frappe` (`bench --site <site> execute` is not the gateway, but `POST /api/method/...` with session cookie is)
- **THEN** the `scope` envelope contains `tiers` `["public","site","restricted"]` and `roles` including `System Manager`, not just `["public"]`
