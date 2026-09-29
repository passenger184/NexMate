# Tasks — Retire `chat-only`, capability model, Frappe-native schema

Implementation order matters. **Section 5 (legacy retirement) precedes section 6
(metadata grant)** so no interval exists in which the capability and policy model
is bypassable (design D9). **Section 15 (migration) precedes any live
verification in section 16.**

**Hard prohibitions.** `erpnext_read.py` and `audit.py` are not modified by any
task; if a task appears to require changing them, stop and re-read
`erpnext-authorized-reads`. The metadata capability gate SHALL precede any
Frappe permission check consulted for metadata, because Frappe's permission
engine allows `Administrator` unconditionally as its first check. Metadata
requests SHALL NOT be routed through `erpnext_read.attempt_read()`.

All source paths are repository-relative. Note that `capabilities.py` and
`orchestrator.py` live at the repository root, not inside
`frappe_app/erpnext_ai_copilot/`.

## 1. NexMate Settings and policy DocTypes

- [x] 1.1 Create the `NexMate Settings` Single DocType in the `Erpnext AI Copilot` module with a `metadata_access_mode` Select field whose options are exactly `all` and `allowlist`
- [x] 1.2 Create the `NexMate Metadata DocType Rule` child DocType with a single `Link` field pointing at `DocType`; the child table SHALL be the only structure representing the configured allowlist
- [x] 1.3 Grant read and write on both DocTypes to `System Manager` only, matching every existing NexMate DocType; do not create a custom role and do not grant write to any role that can hold Developer capability by default
- [x] 1.4 Set `track_changes: 1` on `NexMate Settings` so Frappe `Version` records configuration changes including child-table row changes
- [x] 1.5 Add a table field on `NexMate Settings` referencing `NexMate Metadata DocType Rule`; the settings record SHALL NOT store DocType names in a text field, SHALL NOT store field names, field values, filter values, credentials or permission rows
- [x] 1.6 Register the two DocTypes so they are created by the normal DocType sync; confirm both appear in the module's DocType list and that the existing four NexMate DocTypes are unaffected
- [x] 1.7 Verify with a unit test that `System Manager` can write `NexMate Settings` and that a user without write permission is refused by Frappe before any NexMate code runs

## 2. Configuration validation

- [x] 2.1 Validate at save time that each configured entry resolves to an existing DocType; the framework link validation SHALL reject a nonexistent name, a wildcard and a partial name, and confirm with a test that each is refused
- [x] 2.2 Validate at save time that no configured entry is `istable`; verify with a test using a known child DocType
- [x] 2.3 Validate at save time that no configured entry is `issingle`; verify with a test using a known Single DocType
- [x] 2.4 Validate at save time that no DocType appears twice; verify with a test that submits a duplicate and confirms the save is refused and no duplicate row is stored
- [x] 2.5 Confirm the configured entries carry DocType references only; verify with a test that the stored child rows contain no field-level data
- [x] 2.6 Confirm validation failures surface as a bounded, sanitized save error and never persist a partial or invalid entry

## 3. Policy read (fail-closed, uncached)

- [x] 3.1 Read `NexMate Settings` for each metadata authorization decision using the Frappe-native Single access mechanism, uncached, so that no stale policy can continue to grant access
- [x] 3.2 Introduce no NexMate-side policy cache; confirm by asserting that two decisions separated by a policy change observe different policies
- [x] 3.3 Fail closed to DENY when the settings document does not exist; verify with a test
- [x] 3.4 Fail closed to DENY when the mode is unset; verify with a test
- [x] 3.5 Fail closed to DENY when the mode is not one of the supported values; verify with a test
- [x] 3.6 Fail closed to DENY when the mode is `allowlist` with zero configured entries; verify with a test
- [x] 3.7 Fail closed to DENY when the settings record cannot be loaded or raises; verify with a test that forces a load failure
- [x] 3.8 Confirm the policy is never defaulted to the permissive mode under any failure path; verify with a test that asserts the permissive outcome is never produced from a failure
- [x] 3.9 Do not read the policy from site configuration and do not extend Frappe core System Settings; verify with a source-level test that the metadata module reads neither

## 4. Capability derivation (Frappe control plane)

- [x] 4.1 Add a capability derivation function in the Frappe control plane that resolves the live authenticated session user to `developer` or `employee` from real Frappe roles against the server-managed `nexmate_developer_roles` list; verify with a unit test that a user holding a configured role derives `developer` and one holding none derives `employee`
- [x] 4.2 Make derivation fail closed: malformed configuration, a non-list value, non-string entries, or a raising role lookup SHALL all yield `employee` with no elevation; verify with unit tests covering each failure mode
- [x] 4.3 Confirm no implicit elevation: a System Manager or Administrator without a configured role derives `employee`; verify with an explicit unit test
- [x] 4.4 Confirm derivation reads live Frappe state on every call and introduces no NexMate role or capability cache; verify by asserting two calls with a role change between them return different capabilities
- [x] 4.5 Fold the duplicate per-request role lookup: reuse the single derived role set in both capability derivation and authorization-scope construction instead of calling the role lookup twice per request; verify the call count per request is 1 and the resulting scope is unchanged
- [x] 4.6 Carry the derived capability in the existing `mode` envelope field only; add no second capability field, and confirm the existing response-mode equality invariant is preserved

## 5. Legacy route retirement and no-envelope closure (must land with section 6)

- [x] 5.1 Remove the `/tools/erpnext/schema`, `/tools/erpnext/document` and `/tools/erpnext/list` routes and confirm requests to all three are refused as unknown operations
- [x] 5.2 Remove the no-envelope metadata branch so a credentialed `/orchestrate` request without a gateway envelope cannot obtain DocType schema, fields or permissions; verify with a test that such a request is refused before any metadata retrieval
- [x] 5.3 Refuse the presence of an `authorized_context` field on a request without a complete valid gateway envelope, before the existing no-envelope early return; verify with a test that the field is never consumed, forwarded, or treated as Frappe-derived authorization
- [x] 5.4 Refuse the presence of an `authorization_scope` field on a request without a complete valid gateway envelope; verify with a test that a structurally valid but forged scope is refused and cannot reach retrieval
- [x] 5.5 Refuse the presence of a `conversation` block on a request without a complete valid gateway envelope; verify with a test that a block with a null owner is refused and its turns never reach the orchestrator
- [x] 5.6 Record in the change's `verification-notes.md` that the authorization-scope and conversation exposures are pre-existing, share one root cause with the authorized-context exposure, and are closed here for that reason
- [x] 5.7 Confirm legacy no-envelope chat, retrieval and code behavior is otherwise unchanged; verify the existing legacy and chat-boundary suites still pass apart from the assertions enumerated as intentionally retired in section 14
- [x] 5.8 Confirm the shared-credential read client is no longer imported or reachable from any Frappe-attributed business-user path; define that phrase as a request carrying a Frappe-attributed gateway envelope, not every service-credential-authenticated request, since the retained write routes are themselves service-authenticated; verify with a source-level test

## 6. Frappe-native metadata module (control plane)

- [x] 6.1 Add a control-plane metadata module beside `erpnext_read.py` that resolves DocType metadata in-process from live local DocType metadata using no outbound HTTP call and no shared, site-wide or per-user ERPNext API credential, master key, Administrator password or database credential; verify with a test asserting no credential is read or required
- [x] 6.2 Do not import `erpnext_read` from the metadata module and do not modify it; verify with a source-level test that the metadata module does not reference it
- [x] 6.3 Enforce the authorization order exactly: capability first, then DocType existence, then structural exclusion, then policy; verify with a test that a request is refused at each stage in turn
- [x] 6.4 Enforce the capability gate: a `developer`-capability request proceeds to the eligibility and policy checks, an `employee`-capability request is refused before any metadata retrieval, and the refusal is an enforced refusal rather than a conversational decline; verify with one test per capability
- [x] 6.5 Confirm the capability gate is evaluated before any Frappe permission check consulted for metadata, and that an `Administrator` session user without a configured developer role is refused metadata; verify with an explicit test
- [x] 6.6 Enforce the structural exclusions: reject `istable` and reject `issingle` regardless of policy mode, and before the policy decision; verify with four tests covering both exclusions under both policy modes
- [x] 6.7 Confirm the exclusions are not configurable: no settings value can admit a child table or a Single DocType; verify with a test that setting any policy value leaves the exclusions in force
- [x] 6.8 Enforce the `all` policy mode: any eligible existing DocType is permitted after capability and the structural exclusions; verify with a test
- [x] 6.9 Enforce the `allowlist` policy mode: only DocTypes present in the configured child table are permitted, and any other DocType is refused; verify with a listed and an unlisted DocType
- [x] 6.10 Confirm the policy never widens access: a DocType permitted by policy confers no permission to read any record of it; verify with a test that a later business read is still decided by the Frappe-native boundary
- [x] 6.11 Do not use `frappe.has_permission(doctype, "read")` as the metadata authorization mechanism; verify with a source-level test that the metadata gate does not depend on it

## 7. Projection, bounds, audit and collapse

- [x] 7.1 Enforce the minimized projection: the response SHALL contain only `fieldname`, `fieldtype`, `label`, `reqd` and `read_only`, and SHALL NOT include the DocType `permissions` child table, role or permlevel mappings, Select or Link field `options` values, custom or confidential field markers, field values, rows, or any other DocType document attribute; verify with a test asserting the exact attribute set and the absence of `permissions` and `options` values
- [x] 7.2 Bound the response in shape and serialized size at 100 projected field entries and 65536 serialized bytes, and refuse rather than truncate when either bound is exceeded; verify with a test at the bound and above it
- [x] 7.3 Emit exactly one metadata-only audit event per schema resolution using the dedicated `doctype_schema` action, recording actor, site, operation, DocType and outcome, and containing no returned metadata content or field values; verify by asserting the event carries no schema payload and that exactly one access event is emitted per request
- [x] 7.4 Confirm no second metadata access action exists: `doctype_schema` is the only action emitted for metadata access; verify with a test asserting the action value on both a permitted and a refused request
- [x] 7.5 Make the metadata audit fail closed by inspecting the audit call result: a pending or otherwise unconfirmed durable write SHALL return no metadata; verify with a test that forces both a write exception and a returned pending indicator
- [x] 7.6 Do not modify `audit.py`; verify with a source-level test and record in the change's `verification-notes.md` that the existing business-read path's treatment of a pending audit result is unchanged and remains a pre-existing limitation
- [x] 7.7 Collapse schema refusals in the metadata module's response-construction layer so a caller cannot distinguish capability denial, policy denial, structural exclusion, invalid request, oversize, audit failure, or a nonexistent DocType; verify by asserting every caller-facing response is byte-identical
- [x] 7.8 Use the dedicated collapse shape: the fixed answer `Schema not found or access denied.` and the fixed `route_how` value `frappe-schema+denied`; verify by asserting both exact values and that the business-read collapse is not reused
- [x] 7.9 Confirm the internal refusal reason appears only in the audit event and never in the caller-visible response; verify with a test asserting no internal code leaks into the response

## 8. Round trip and dispatch

- [x] 8.1 Add a metadata request kind to the existing authorized-context round trip, reusing the bounded round loop, so a metadata turn follows the same Browser → Frappe → inference → Frappe → inference shape as a business read; verify with a round-trip test asserting the authorized-context field carries the minimized metadata
- [x] 8.2 Dispatch on request kind in the round loop: metadata to the metadata module, business reads to `erpnext_read`; verify with a test that a metadata request never reaches `erpnext_read.attempt_read()` and a business read never reaches the metadata module
- [x] 8.3 Extend the consumer-side authorized-context contract with a metadata operation, a metadata shape and metadata-specific bounds, leaving the business-read operation set, field bound, row bound and size bound unchanged; verify with tests that the existing business-read bounds still hold and that a metadata result satisfies its own declared shape
- [x] 8.4 Update the assertion that a metadata operation is rejected by the authorized-context consumer contract, which this change makes incorrect by design, and preserve every other assertion in that group unchanged
- [x] 8.5 Confirm metadata requests share the existing round budget rather than receiving a separate one; verify with a test at the budget boundary
- [x] 8.6 Confirm the metadata response passes through the existing response-field allowlist and is not echoed to the browser as an uncontrolled field; verify with a test asserting the browser-facing response contains only allowed fields
- [x] 8.7 Confirm inference cannot request metadata for a DocType the policy forbids and that an invalid or malformed metadata request is refused before any metadata retrieval; verify with negative tests
- [x] 8.8 Confirm the inference process performs no outbound metadata call of its own; verify with a source-level test that the orchestrator's metadata path requests rather than retrieves
- [x] 8.9 Confirm the metadata operation cannot enter the business-read request contract and the business-read operation cannot enter the metadata contract; verify with tests asserting each rejects the other's operation

## 9. Inference-side boundary

- [x] 9.1 Remove the inference-side employee schema short-circuit so the orchestrator no longer declines schema on capability grounds; verify with a test that an employee schema request is emitted as a request and reaches the control plane
- [x] 9.2 Do not replace the removed short-circuit with any other inference-side authorization check; verify with a source-level test that the orchestrator performs no capability or policy decision for metadata
- [x] 9.3 Confirm the metadata branch precedence is explicit and tested, so a supplied authorized context can never be consumed for a metadata request; verify with a test that supplies a forged context alongside a schema request and asserts the context is ignored

## 10. Execution scope retirement

- [x] 10.1 Replace the fixed execution scope literal on the gateway producer with the single generic authenticated value; verify the envelope value in a unit test
- [x] 10.2 Replace the accepted literal in the inference envelope validator in the same change, and require an exact match with no coercion; verify that any other value is refused and that a partial envelope does not fall back to legacy behavior
- [x] 10.3 Add a test asserting the producer's emitted scope value and the consumer's accepted value cannot drift apart
- [x] 10.4 Refuse a browser-supplied mode or capability form field instead of accepting and ignoring it; remove it from the allowed form fields and verify that Desk still works, since the Desk selector is already disabled client-side
- [x] 10.5 Split the execution gate from the capability-advertising flag so the route-denial gate is named for what it is and the capability replies, smalltalk handling and version-preamble suppression remain driven by the requester's capability; verify the code, write, proposal, apply, approval and reset paths are still denied on the gateway path for both capabilities
- [x] 10.6 Confirm the execution scope alone grants nothing: verify that a request carrying a valid scope still cannot obtain business records, metadata, write access, code execution or tool execution
- [x] 10.7 Confirm incidental live version lookups remain suppressed on the gateway path and the response uses unavailable-version semantics without fabricated versions; verify with a test asserting no live call occurs

## 11. Capability registry

- [x] 11.1 Split the registry entry covering documents, lists and counts from the one covering schema and metadata, so a business-record live-data capability and a metadata capability are described separately
- [x] 11.2 Make the metadata capability Developer-only and the record-lookup capability available to both capabilities
- [x] 11.3 Do not implement this with runtime description special-casing; the registry SHALL remain static descriptive data and SHALL NOT become an authorization mechanism
- [x] 11.4 Verify an employee capability reply does not advertise metadata access, and a developer capability reply accurately describes both available operations
- [x] 11.5 Confirm a capability reply never states an operation the requester will be refused, given the site policy; because the refusal is collapsed, the reply describes capability availability only and SHALL NOT imply per-DocType authorization

## 12. Tests — capability and policy matrix

- [x] 12.1 Developer plus `all` plus an eligible DocType succeeds and returns only the five projected attributes
- [x] 12.2 Employee plus `all` is denied with no metadata retrieved
- [x] 12.3 Developer plus `allowlist` plus a listed DocType succeeds
- [x] 12.4 Developer plus `allowlist` plus an unlisted DocType is denied
- [x] 12.5 `allowlist` with an empty list is denied
- [x] 12.6 Missing settings document is denied
- [x] 12.7 Invalid settings, including an unset mode and an unsupported mode, is denied
- [x] 12.8 A settings read failure is denied
- [x] 12.9 A child-table DocType under `all` is denied
- [x] 12.10 A Single DocType under `all` is denied
- [x] 12.11 A child-table DocType under `allowlist`, including when listed, is denied
- [x] 12.12 A Single DocType under `allowlist`, including when listed, is denied
- [x] 12.13 A nonexistent DocType produces the collapsed denial and is indistinguishable from a refused existing DocType
- [x] 12.14 Duplicate allowlist rows are rejected at save
- [x] 12.15 A wildcard or partial DocType entry is rejected at save
- [x] 12.16 An invalid DocType entry is rejected at save
- [x] 12.17 A committed policy change affects the very next metadata decision with no restart and no cache flush
- [x] 12.18 Site A's policy does not affect Site B's decisions, covering `all` on one site and a restricted list on another
- [x] 12.19 A Developer-capability user without write permission on `NexMate Settings` cannot modify the policy
- [x] 12.20 A user with write permission on `NexMate Settings` but no configured developer role derives `employee` and is refused metadata
- [x] 12.21 A metadata request generates exactly one `doctype_schema` access audit event
- [x] 12.22 A metadata request never reaches `erpnext_read.attempt_read()`
- [x] 12.23 No policy mode, configured DocType list, or configuration-authority signal appears in browser boot information
- [x] 12.24 No policy mode, configured DocType list, or configuration-authority signal appears in the inference envelope

## 13. Tests — security, legacy and credential

- [x] 13.1 A forged developer capability or mode in the request is refused and ignored
- [x] 13.2 A forged execution scope is refused
- [x] 13.3 An invalid execution scope value is refused and not coerced
- [x] 13.4 A missing or Guest Frappe session is refused before any upstream call
- [x] 13.5 A developer-capability user attempting a business record Frappe denies is refused
- [x] 13.6 A partial gateway envelope is refused and does not degrade to legacy behavior
- [x] 13.7 A site mismatch is refused
- [x] 13.8 All three no-envelope injection channels remain closed, with a test per channel
- [x] 13.9 Inference attempting to obtain metadata directly is not possible: verify no inference-side metadata retrieval path exists and that an inference-originated metadata request is authorized only in the control plane
- [x] 13.10 Fail-closed audit: a metadata audit-write failure and a returned pending audit result both return no schema
- [x] 13.11 Fail-closed derivation: a role-lookup failure yields no elevation
- [x] 13.12 The Administrator permission bypass does not reach metadata: a session user the Frappe permission engine would allow unconditionally is still refused metadata without a configured developer role
- [x] 13.13 No secret, credential or transport header appears in telemetry, logs, prompts or model inputs on the new paths
- [x] 13.14 The new READ and metadata paths do not depend on the legacy routes: verify no Frappe-attributed user path references the removed routes or the shared-credential read client
- [x] 13.15 The removed routes are absent from the route inventory and requests to them are refused
- [x] 13.16 Shared credential usage is reduced to the enumerated remaining consumers — write propose validation, write propose and apply routes, and the version lookup — verified by a source-level test that no other consumer exists
- [x] 13.17 Assert explicitly that the shared credential is still required by the out-of-scope write path, so the remaining dependency is recorded rather than implied absent
- [x] 13.18 Assert that no shared ERPNext credential is used on the Frappe-attributed business-read or metadata path; do not assert that the credential is absent from the inference process environment, because the retained consumers make that untrue

## 14. Regression floor and intentional test changes

- [x] 14.1 The 40 `tests/test_erpnext_read_adapter.py` tests pass unchanged
- [x] 14.2 The 20 boundary tests in `tests/test_u5_read_boundary.py` that do not assert retired behavior or the intentionally extended metadata operation contract pass unchanged, including the read interface exposing no authorization parameter, forged identity rejection, Guest refusal, minimization, anti-oracle collapse and audit-failure denial
- [x] 14.3 Five assertions must change: four legacy-group assertions and one authorized-context consumer-contract assertion. Each SHALL be rewritten to assert the post-change outcome, not deleted, and no assertion may be weakened to make it pass. The four legacy-group assertions are `test_12_1_routes_retained_in_inventory`, `test_12_1_routes_marked_deprecated`, `test_12_2_deprecation_policy_is_stated` and `test_12_3_read_client_retained_for_legacy_consumers`. The fifth is `test_7_2_operation_must_be_supported`, which currently asserts that a metadata operation is rejected by the authorized-context consumer contract; task 8.3 deliberately extends that contract to accept it, so the assertion is obsolete by design. The remaining three Group 12 assertions — `test_12_4_version_lookup_still_resolves_credential`, `test_12_4_write_path_still_uses_retained_client` and `test_12_4_credential_consumer_set_unchanged_apart_from_reads` — stay valid and unchanged, because the version lookup and the write-path credential consumers are intentionally retained out of scope
- [x] 14.4 Update the closed route-inventory assertion in `tests/test_chat_boundary.py` to the post-change inventory
- [x] 14.5 Update the assertion that the role lookup is called twice per request to the single-call outcome
- [x] 14.6 Update the assertion that a browser mode field is accepted without warning to the refused outcome
- [x] 14.7 Update the assertion that the employee schema denial is conversational and that the metadata branch is not entered, to the request-and-refuse outcome
- [x] 14.8 Update the affected schema-path mocks in `tests/test_orchestrator.py`, `tests/test_routing_eval.py`, `tests/test_routing_precision.py`, `tests/test_post_live_regressions.py` and `tests/test_conversation.py`
- [x] 14.9 Do not weaken any assertion to make it pass; every update SHALL assert the new required behavior
- [x] 14.10 Frappe gateway authentication still refuses forged identity fields and cross-site mismatch
- [x] 14.11 Inference service authentication still fails closed with an absent or invalid service credential, and `/health` remains minimal and unauthenticated
- [x] 14.12 Normal chat, code routing, conversational replies, clarification and out-of-scope behavior are unchanged apart from the capability-driven wording intended by this change
- [x] 14.13 The write path and code-edit contract requirements are unchanged, verified by asserting their approval, permission-recheck and execution requirements still hold

## 15. Migration (approval-gated; do not run without recorded approval)

- [x] 15.1 Add `doctype_schema` to the `action` options on `NexMate Audit Entry`; the change SHALL be purely additive and SHALL preserve every existing option
- [x] 15.2 Confirm no new audit `outcome` value is required; `success`, `denied`, `not_found`, `permission_denied` and `invalid_request` all exist
- [x] 15.3 Record the migration requirement in `design.md` and this task list as three additive DocType schema synchronizations with no data migration
- [x] 15.4 Obtain explicit migration approval and record approver, date and environment in `DECISIONS.md` before running anything
- [x] 15.5 Verify the app registration and installed-app state before migrating, keeping these two distinct checks separate. First, verify `sites/apps.txt` lists `erpnext_ai_copilot`, because that list feeds the module map; the U5 run recorded that its absence, together with the Redis-cached module map, caused all four NexMate DocTypes to be deleted by the DocType sync. Second, verify the target site's `site_config.json` `installed_apps` lists `erpnext_ai_copilot` consistently with the intended installed-app state. These two files do not serve an identical purpose — the module map governs controller resolution during the DocType sync, while `installed_apps` records per-site installed application state — and the two can disagree, as they already do on the test site, where `sites/apps.txt` lists the app and `frontend/site_config.json` does not. Treat any inconsistency as a blocker: resolve and document it, with the intended state and the chosen resolution recorded, and obtain explicit approval before migration proceeds. Do not apply an automatic fix
- [x] 15.6 Verify the app and module cache state, and that a controller resolves for every existing NexMate DocType, before migrating
- [x] 15.7 Back up the NexMate DocType definitions and the NexMate DocType data before migrating
- [x] 15.8 Run `bench --site <site> migrate` only after the approval gate in 15.4 through 15.7 are satisfied
- [x] 15.9 Verify after migration: exit status, no orphan-deletion output, all four pre-existing NexMate DocTypes still present, both new DocTypes present, and the audit `action` and `outcome` option lists correct with every prior option preserved
- [x] 15.10 Record the migration outcome, including the rollback ordering constraint that reverting an option list after events using it have been written leaves those values orphaned, in the change's `verification-notes.md`

## 16. Verification

- [x] 16.1 Run `openspec validate --strict` and confirm it passes
- [x] 16.2 Run the full test suite and confirm no previously passing test regressed
- [ ] 16.3 Live Desk verification for each row of the capability and policy matrix, using a genuine Frappe-authenticated session per user and recording the audit delta for every authorized read and metadata resolution
- [x] 16.4 Live negative verification for the security cases: unauthorized read as a developer, metadata as an employee, metadata outside the policy, a structural exclusion, a nonexistent DocType, a forged scope, and each unattributed authorization field
- [x] 16.5 Live verification that a committed policy change takes effect on the next request with no restart
- [x] 16.6 Confirm the audit ledger records exactly one `doctype_schema` event per metadata resolution and one `erpnext_read` event per read, with actor, site, operation and outcome
- [x] 16.7 Confirm the audit ledger records policy changes with actor, site, previous mode and new mode, and that `Version` records the child-table row changes
- [x] 16.8 Confirm no ERPNext credential is present on the Frappe-attributed business-read or metadata path, and that the enumerated remaining consumers are the only ones requiring one
- [x] 16.9 Record evidence in `EVALUATION.md`-conformant form: test type, date, environment, limitations and the next gate

## 17. Documentation and decision ledger

- [x] 17.1 Add a `DECISIONS.md` ADR superseding the `chat-only` decision at `:422`, recording the generic authenticated scope, the capability model, the Frappe-native metadata path, the configurable administrator metadata policy, and the legacy retirement, with approval provenance
- [x] 17.2 Update `ARCHITECTURE.md`: correct the stale wiring references (`api.py:236`→289, `orchestrator.py:1038`→1141, `service/auth.py:164`→215) and every other stale reference to the retired scope, the Developer Mode claims, the route inventory, and the authorization row
- [x] 17.3 Update `SECURITY.md` so the retained shared-credential consumer list matches the reduced reality, state that total removal is blocked by the out-of-scope write path, and record that an absent or invalid metadata policy denies rather than permits
- [x] 17.4 Update `README.md` and `DEVELOPMENT.md` to describe the authenticated execution scope, the Employee/Developer capability model, the `Developer` Frappe Role configuration, the Frappe-native metadata path, and `NexMate Settings` as the one Desk-editable administrator surface, distinguishing it from the site-configuration keys
- [x] 17.5 Document the metadata policy explicitly: development and testing posture is `all`; an administrator may choose `allowlist` for production; `all` permits metadata inspection across all eligible DocTypes and therefore exposes structural information from custom applications installed on the site; `all` SHALL NOT be described as automatically appropriate for production
- [x] 17.6 Update `ROADMAP.md` and `progress/CURRENT.md`, `progress/JOURNAL.md`, `progress/BLOCKERS.md` to record the change, the credential dependency map, the configurable policy, and the pre-existing exposures closed in section 5
- [x] 17.7 Record the resolved open questions from `design.md` and their answers

## 18. Configurable operational limits (specified, not yet implemented)

The requirements in this section are normative as of the configuration-design
update, but no implementation task above covers them: every task in sections
1–17 is checked against the pre-limits implementation. Do NOT treat checked
tasks as covering this section. The `max_schema_fields` default of 300 differs
from the previously hardcoded 100, so tests asserting refusal above 100 entries
will need updating when this section is implemented; list those updates
explicitly rather than weakening them.

**Hard prohibitions for this section.** The immutable service ceilings SHALL
NOT be made configurable. `erpnext_read.py` and `audit.py` remain unmodified.
Request/inference timeouts, secrets, endpoints, provider configuration,
infrastructure settings and deployment flags SHALL NOT be moved into
`NexMate Settings`.

- [x] 18.1 Add the numeric settings fields to `NexMate Settings` (`max_schema_fields`, `max_schema_bytes`, `max_read_rows`, `max_read_fields`, `max_read_bytes`, `max_read_rounds`) with the defaults, minima and administrator maxima from design D16; add the `developer_roles` role-selection field per D19; keep the fields additive under the existing migration gate
- [x] 18.2 Validate each numeric setting at save time against its supported range and refuse out-of-range values; verify with a test per setting at, above and below its range
- [x] 18.3 Enforce `effective_limit = min(admin_configured_value, immutable_service_ceiling)` at every runtime enforcement point, re-checking the ceiling independently of Settings validation; verify with a test that forces an above-ceiling value past validation and asserts clamping
- [x] 18.4 Resolve `developer_roles` with the locked precedence (Settings names roles → Settings wins; absent → `site_config` fallback; explicitly empty → no roles granted; malformed → fail closed; deleted roles → never match), keeping resolution live and per-request with no cache; verify each row with a test
- [x] 18.5 Raise the inference-side metadata contract to the 500-field / 131072-byte ceilings with metadata-only constants separate from the business-read constants; verify the two constant sets are declared independently
- [x] 18.6 Enforce the resolved field-count bound in `api.py:_authorized_metadata` alongside the existing serialized-size check, so an over-ceiling projection cannot pass the control plane only to be rejected downstream; verify with a test
- [x] 18.7 Apply the resolved read bounds (`max_read_rows`, `max_read_fields`, `max_read_bytes`) in the business-read path without touching authorization, allowlists, collapse or audit; verify defaults preserve current behavior and narrowing takes effect on the next read
- [x] 18.8 Apply the resolved round budget (`max_read_rounds`) in the gateway loop with the ceiling enforced; verify the default of 3, clamping above 5, and refusal of values below 1
- [x] 18.9 Update the tests that assert the old hardcoded bounds (including refusal above 100 projected entries) to the new defaults and ceilings; assert the new default, ceiling and clamp behavior explicitly and do not weaken unrelated assertions
- [x] 18.10 Add boundary, fallback, immediacy and dynamic-setting tests for every new setting per the audit's test-impact table, including an end-to-end check that a Frappe-accepted payload is never rejected by the inference contract
- [x] 18.11 Record the settings additions in `verification-notes.md` with their migration evidence when implemented; the fields ride the existing additive synchronization and require no separate migration step beyond it

## 19. Corrective review follow-ups (fallback semantics and adapter ceiling)

Corrective pass over §18. `erpnext_read.py` and `audit.py` remain unmodified
throughout; request/inference timeouts stay out of `NexMate Settings`.

- [x] 19.1 Distinguish unreadable Settings from absent Settings in developer-role resolution: proven-never-saved falls back to `site_config`; proven-saved-but-unreadable, unreadable role rows, and unreadable store fail closed with no fallback; verify each row with a unit test
- [x] 19.2 Log role-source read failures distinctly from malformed mappings (`developer_role_source_unavailable` vs `invalid_developer_roles_config`); verify each log line fires exactly in its case
- [x] 19.3 Update test doubles that modeled Settings absence with a truthy store to model genuine absence (empty tabSingles), and add explicit fail-closed tests for every unreadable variant at both unit and gateway level
- [x] 19.4 Document the frozen-adapter residual (effective additionally capped by the unmodifiable 20/20/65536 adapter bounds) in design D17 and the durable-tool-execution spec, with a scenario pinning the backstop behavior
- [x] 19.5 Add honest bound tests: effective-never-exceeds-adapter for every admin input including above-ceiling values, plus a test documenting that the frozen adapter refuses beyond 20 rows/fields independent of settings
- [x] 19.6 Re-run the full suite, OpenSpec validation, and `git diff --check`; record the residual and the exact scoped unfreeze (adapter bound constants only) required to honor ceilings end to end

## 20. Live-verification defect fixes (consumer alignment and untouched save)

Two blocking defects found by the controlled migration and live verification.
`erpnext_read.py` and `audit.py` remain unmodified; no authorization, identity,
allowlist, projection, collapse, audit, timeout or protocol change.

- [x] 20.1 Diagnose the self-lock empirically on site `frontend`: establish that Frappe's `get_valid_dict()` materialises an unset Single `Int` as `"0"` while the Desk client posts `null` (`ControlInt.parse` → `cint(value, null)`), and that `coerce_limit` then mapped `0` to the *minimum* rather than the default
- [x] 20.2 Make `coerce_limit` resolve a below-minimum value to the **default**, matching its own documented contract, so a corrupt or residual value can never tighten a setting to its minimum
- [x] 20.3 Add `policy_limits.normalise_numeric_settings` and call it from the `NexMate Settings` controller before validation, writing the documented default into every unset/blank bound so an untouched save is a genuine no-op
- [x] 20.4 Leave validation strict: explicit below-minimum (including `0`) and above-administrator-maximum values are still refused, administrator maximums still accepted, runtime ceiling still enforced independently; verify every case on the live site
- [x] 20.5 Raise the business-read consumer bounds in `service/auth.py` to the producer's approved immutable ceilings as named constants (100 rows / 50 fields / 131072 bytes), replacing the hardcoded `>20` field literal; leave the metadata contract at 500 / 131072 and the two contracts unmerged
- [x] 20.6 Align the orchestrator's read-request proposal cap with the approved ceiling (`DEFAULT_READ_LIMIT = 20`, `MAX_READ_LIMIT = 100`) so an administrator's configured bound is reachable end to end, keeping the default behaviour when a request names no limit
- [x] 20.7 Update the tests that pinned the stale contracts and add focused tests for both defects: the untouched-save lifecycle, retained rejection of explicit invalid input, the full consumer acceptance matrix, narrowing, and consumer/adapter ceiling agreement
- [x] 20.8 Verify both fixes live on `frontend`: Defect 1 through the real DocType lifecycle including a Desk-shaped client payload; Defect 2 by feeding a context the live site actually produced into the real inference consumer across the process boundary
- [x] 20.9 Re-run the full suite, OpenSpec validation and `git diff --check`; record the fixes, the live evidence and the one recorded residual (a site that stored zeros before this fix needs one explicit re-entry to save again)
