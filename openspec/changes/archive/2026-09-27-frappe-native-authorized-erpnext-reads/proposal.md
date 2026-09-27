## Why

Every authenticated NexMate user's ERPNext business-data reads are currently answered under **one shared integration identity**, not their own. `tools/erpnext.py` holds a single process-global `token key:secret` credential and contains no reference to user, session, site, or tenant, so the LLM-derived read request is executed as `nexmate.integration@example.com` regardless of who asked.

That identity was measured live on the test site: it is a non-Administrator account holding 14 broad roles, permitted to read 35 DocTypes including `Bank Account`, `GL Entry`, `Journal Entry`, `Payment Entry`, `Employee`, `Timesheet`, `User`, `File` and `Communication`, while being denied `DocType`, `Role`, `Salary Slip` and the access/audit logs. **A NexMate user with no ERPNext read right receives that account's data**, and NexMate's existing Frappe-layer authorization never applies to it. This is the U5 gap: authorization for ERPNext business records is decided by a credential, not by the authenticated Frappe user.

## What Changes

**The authenticated Frappe process becomes the authorization enforcement point for ERPNext business-data reads.** The inference service becomes an untrusted requester and consumer of already-authorized context — it does not gain, and must not retain, authority to read ERPNext business records.

- **NEW** a Frappe-native, permission-aware ERPNext business-read adapter living inside the Frappe application boundary, supporting `document` and `list` only, and exposing a narrow validated contract rather than an ORM wrapper.
- **NEW** a read-request seam: inference may *request* a read, but Frappe alone validates, authorizes, executes, minimizes and audits it. Inference can neither choose nor assume the authorization subject.
- **BREAKING (internal, no public API change)** the authenticated user business-read path stops calling `tools/erpnext.py`. `orchestrator`'s ERPNext branch consumes Frappe-produced authorized context instead of a shared credential.
- Authorization subject is fixed to `frappe.session.user`; the adapter accepts no `user`/`actor`/`username`/`site`/`mode` authorization parameter, and Guest is refused.
- Strict request validation replaces today's pass-through: LLM-generated `fields` and `filters` are currently forwarded unvalidated to the ERPNext client and are now rejected unless they satisfy an explicit allowlist, field projection and bounded filter policy.
- Field-level permission enforcement is mandatory before serialization, and results are field-projected, so a user's ability to open a document never implies the whole document is sent to the model.
- Anti-oracle behavior: `NOT_FOUND` and `PERMISSION_DENIED` collapse to one externally indistinguishable response while remaining distinguishable in audit and Debug.
- Every business read emits exactly one metadata-only audit event with a dedicated `erpnext_read` action, and an audit write failure **denies the read** rather than returning data.
- The three legacy `/tools/erpnext/{schema,document,list}` routes are disconnected from the user read path and marked deprecated/quarantined; they are not removed in this change.
- The shared ERPNext credential is removed from the user business-read path only. It is explicitly retained for enumerated temporary legacy/system consumers (version lookup, legacy write helpers) so no unrelated consumer breaks.

### Rejected alternatives (Model B, Model C)

- **Model B — per-user ERPNext API credentials.** Rejected: it expands secret distribution from one integration account to one per human user, and still leaves every read executed outside the Frappe request process by a non-authoritative service. It also re-creates the ContextVar problem identified in the U5 preflight — `frappe.session.user` lives in a `ContextVar` and is genuinely unbound outside a Frappe request, so the inference process could not derive or verify the caller identity and would be trusting an asserted subject.
- **Model C — externally recreated capability/permission envelopes.** Rejected: it requires NexMate to re-implement Frappe's permission semantics outside Frappe, where the preflight identified at least six distinct enforcement footguns (`Query` defaults `ignore_permissions=True`; `get_all` sets it; `flags.ignore_permissions` voids document checks; owner-constraint and User Permission are `if/elif` so they do not compose; sharing is OR-ed on top of all restrictions; and field-level `permlevel` enforcement is a separate explicit step absent from `get_doc`). Field-level `permlevel` behavior was not resolvable without live evidence. Recreating that engine is a larger and more dangerous surface than invoking it in place.

## Capabilities

### New Capabilities
- `erpnext-authorized-reads`: the Frappe-native permission-aware ERPNext business-read boundary — identity source, operation/doctype/field/filter/limit policy, mandatory field-level enforcement, fail-closed audit, and anti-oracle error behavior for authenticated business reads.

### Modified Capabilities
- `frappe-api-gateway`: the gateway envelope gains a Frappe-produced, bounded authorized ERPNext context field and the two-stage read seam; gateway response-field and size bounds are preserved and authorized context is never echoed back.
- `audit-ledger`: dedicated `erpnext_read` action and read outcomes, one metadata-only event per business read, and fail-closed behavior when the audit write fails.
- `endpoint-access-control`: the three legacy `/tools/erpnext/*` read routes are disconnected from the user read path and marked deprecated/quarantined; they remain present and service-authenticated but no longer serve authenticated user business reads.
- `acl-aware-retrieval`: disambiguates the deliberately coarse knowledge-retrieval ACL from the new Frappe-enforced business-record authorization, so retrieval success is still never presented as proof of ERPNext permission.
- `durable-tool-execution`: the `erpnext_read` tool contract gains a real permission requirement and explicit no-approval read semantics, distinct from approval-gated writes.
- `debug-transparency`: Debug discloses authorized ERPNext read provenance as a distinct source class from RAG retrieval provenance.
- `provider-egress-policy`: authorized ERPNext business data is classified as a local-default data class subject to the all-call deny-by-default egress policy when it enters the inference/generation path.

## Impact

**New module (proposed location, not created by this change):**
`frappe_app/erpnext_ai_copilot/erpnext_read.py` — must remain inside the Frappe app boundary; `tests/test_frappe_isolation.py` statically fails if `frappe_app/**/*.py` imports repo-root `tools`/`config`/`service`/`rag`/`orchestrator`, so the adapter cannot reuse `tools/erpnext.py` even partially.

**Modified:**
- `frappe_app/erpnext_ai_copilot/api.py` — envelope construction, authorized-context production, response bounds.
- `frappe_app/erpnext_ai_copilot/erpnext_ai_copilot/doctype/nexmate_audit_entry/` — `action`/`outcome` are closed `Select` fields with no read-specific option, so a dedicated `erpnext_read` action requires a DocType option change and a `bench migrate` (an explicit task, not a silent vocabulary overload onto `retrieval`).
- `service/main.py` — `OrchestrateRequest` is `extra="forbid"` and has no authorized-context field; both producer and consumer must change together or `/orchestrate` rejects the envelope.
- `service/auth.py` — envelope validation for the new field.
- `orchestrator.py` — ERPNext branch cutover away from `tools/erpnext.py`.
- `tools/contracts.py` — `erpnext_read` contract gains a permission requirement.

**Retained deliberately:** `tools/erpnext_write.py` and its `erpnext._credentials()` reuse; the `call_method` version lookup; the global `ERPNEXT_BASE_URL` multi-site problem (U1, deferred).

**Out of scope:** multi-site/U1 routing, schema/metadata authorization redesign, write-path redesign, mode redesign, provider/vector/RAG architecture, production-write authorization, cloud consent, and global credential removal.
