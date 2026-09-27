## Context

See `proposal.md` — Why for motivation. This section records only the current-state facts and constraints that shape the implementation approach.

**Verified current read paths.** Two, both outside the supported Desk path:

- The supported Desk path is `chat_only`; `execution_scope="chat-only"` is hardcoded in the gateway and the orchestrator denies the `erpnext` route before entry. The shipped Desk UI therefore performs no ERPNext reads today. It makes only three browser `fetch()` calls: the Frappe gateway `ask()` and the Frappe gateway lifecycle method, plus a preview-only base-URL path used when the document is served from the standalone preview route.
- Legacy/preview traffic reaches ERPNext either through `/orchestrate` without a gateway envelope (legacy direct, `chat_only=False`) or through the three direct `/tools/erpnext/{schema,document,list}` routes. Both are gated only by the inference service credential and never by a Frappe user.

**The intent is LLM-derived, and two of its fields are unvalidated today.** The orchestrator's ERPNext extraction validates only operation membership, a non-empty DocType, and a document name for document operations. Its `fields` and `filters` are forwarded straight into the read client, and the existing read contract does not declare a `fields` bound at all.

**Verified Frappe 16.31.0 read semantics** (installed source; these constrain the design and are re-verified as a task before coding):

| Concern | Verified behavior |
|---|---|
| `get_list` | Enforces three levels: DocType gate, then row conditions (owner constraint *or* user permissions, plus permission-query hooks/server scripts, AND-ed), then shared documents OR-ed on top. Field permissions filter the projection; `*` is re-expanded to the permitted set rather than issuing `SELECT *`. |
| `get_all` | The same list call with permissions disabled. No enforcement and no error. |
| `get_doc` | No permission check unless one is explicitly requested. The document load reads the complete row. |
| Explicit document check | Validates DocType/document-level permission only — no field level. |
| Field-level read permissions | A **separate, explicit** step that deletes unauthorized attributes and then applies field masking. It is called by the API/handler layers, never by `get_doc` itself. |
| `as_dict` | Key set comes from the DocType definition; values come from the in-memory document. A field deleted by the field-level step still appears, coerced to its type default (a boolean renders as `0`). Null-pruning is opt-in. |
| `frappe.db.sql` and direct value/count helpers | No permission parameter and no permission logic. |
| Query-builder entry point | The low-level engine defaults to permissions **disabled**; the permission-aware list path passes them explicitly. |
| `set_user` | Rebinds the session user and clears permission caches. `Administrator` bypasses all checks. |
| Session identity | Held in a context variable and unbound outside a Frappe request. |

**Live evidence already collected** (Step 0, read-only): the shared credential authenticates as a single non-Administrator account holding 14 broad roles, permitted to read 35 DocTypes including `Bank Account`, `GL Entry`, `Employee`, `Timesheet`, `User`, `File` and `Communication`, and denied `DocType`, `Role`, `Salary Slip` and the access/audit logs. It was also established that both of NexMate's *current* HTTP read paths are field-permission-aware, so a naive ORM port would be a **regression** relative to today.

**Hard repository constraints.** A test statically fails if any module under the Frappe app imports repo-root `tools`, `config`, `service`, `rag`, or `orchestrator`. The new adapter must therefore be self-contained inside the Frappe app and cannot reuse the existing read client, not even partially. A second test pins an app-local lifecycle-status mirror to the inference-side contract, so contract edits must be checked for mirror drift.

**Audit record shape.** The durable audit DocType is `NexMate Audit Entry` with `correlation`, `request_id`, `action`, `actor`, `site`, `target`, `outcome`, `details`, `redacted`. `action` and `outcome` are closed `Select` fields. The action list contains retrieval, tool-call and security-event options but **no** ERPNext-read-specific option, and the outcome list has no not-found value.

## Goals / Non-Goals

**Goals:**

- Make the authenticated Frappe request process the sole enforcement point for ERPNext business-record authorization.
- Keep the adapter a constrained business-data interface that can narrow access but never widen it.
- Guarantee that field-level permission enforcement happens before serialization and that a stripped field cannot reappear as a type default.
- Make a business read impossible to complete without an audit record.
- Make not-found and permission-denied externally indistinguishable.
- Leave the system in a state where rollback is a code revert plus a route-policy revert, with no data migration to undo beyond the audit vocabulary addition.

**Non-Goals:**

- Multi-site or tenant routing, and the global shared-ERPNext-base-URL problem (U1, deferred).
- DocType schema/metadata authorization redesign; the adapter supports `document` and `list` only, and existing per-mode schema behavior is untouched.
- Any write-path, code-edit, proposal-lifecycle, mode-engine, provider, vector-store, or RAG architecture change.
- Production-write authorization, cloud/provider consent, and global removal of all ERPNext credentials.
- Recreating Frappe's permission engine, or a NexMate-side authorization/grant cache.

## Decisions

### D1. Reuse the existing authenticated gateway as the read boundary; add no new transport

The read boundary is the whitelisted `ask()` method, extended with a second upstream leg. Inference returns a structured, untrusted read request; Frappe validates, authorizes, executes, minimizes and audits it, then returns authorized context; inference produces the final answer.

Rationale: the gateway already owns authenticated identity, the authoritative site, role-derived mode, the server-derived authorization scope, response-field allowlisting, upstream size bounds, sanitized errors, and the service credential. A new transport would duplicate all of that and create a second, less-hardened entry point.

Alternative considered: a separate authenticated Frappe read endpoint called by inference over HTTP. Rejected — it would require inference to mint, carry and validate a Frappe-originated credential, reintroducing a bearer-secret trust hop for a request that should never leave the trusted process.

### D2. The read request is untrusted input and is validated as such

Inference's read request is validated against the same contract regardless of who proposed it, exactly as the gateway already treats a browser payload. The LLM's role is reduced to suggesting an intent; it is never an authority.

Consequence, and it is a deliberate tightening: today's unvalidated pass-through of LLM-supplied `fields` and `filters` is a live weakness that this change removes. Rejection is loud and typed; the request is never silently rewritten into a different query.

### D3. Enforce the security contract, and re-verify the Frappe 16.31.0 implementation before coding it

The read contract is specified as behavior — "permission-checked read, field-level enforcement before serialization, no unauthorized field in the result" — rather than as a fixed call sequence. The verified three-step sequence plus explicit field projection is the current evidence for how Frappe 16.31.0 satisfies that contract, and it is recorded here so the implementer knows what was actually observed. It is re-verified as a task because two behaviors are easy to get wrong: the field-level step is not part of `get_doc`, and it does not remove stripped keys from serialized output.

Implementation constraint: the adapter must build its own explicit field list and prune nulls, so a stripped field can never be emitted as a type default even if the underlying serialization behavior changes.

### D4. Explicitly forbid the permission-bypassing APIs, with the verified reason for each

The forbidden list is part of the contract, not a code-review convention, because each entry is a real footgun rather than a theoretical one: the non-checking list call, raw SQL and direct value/count helpers, direct query-builder access that is not permission-configured, permission-suppressing document flags, and session-user switching. Each is enumerated in the `erpnext-authorized-reads` spec with its observed consequence.

`set_user` is called out separately: it is the only construct that could make the adapter appear to act for a different caller, and `Administrator` bypasses every check, so it is never used on the read path.

### D5. Narrow by allowlist; DocType and field policy are explicit configuration, not inference

The adapter narrows access using an explicit DocType policy, an explicit per-doctype field projection, a bounded filter grammar, and a stricter list maximum than the general tool contract.

Trade-off accepted: an allowlist is operationally narrower than arbitrary DocTypes. That is the point — the adapter is an authorization boundary, not a convenience proxy — but it means DocType coverage is a deliberate, reviewable configuration decision rather than an emergent one. The policy is versioned alongside the adapter so a later expansion is a reviewed change, not a silent widening. The stricter adapter list bound is recorded as an intentional read boundary and does not alter the general contract's own maximum.

### D6. Dedicated audit action, and the schema change is an explicit task

Business reads get their own audit action rather than reusing the retrieval action, because conflating record access with corpus access would make the ledger unable to answer a question the G4/G5 evidence methods require. Since `action` and `outcome` are closed `Select` fields with no read-specific values, this requires a DocType option change and a migration.

Trade-off accepted: U5 becomes the first change in this project to require a live migration, which slightly weakens the "no environment change beyond evidence collection" property. The alternative — overloading the retrieval action — was rejected because it degrades audit specificity silently, and a silent overload is harder to detect and undo than a declared migration.

Audit is mandatory for reads: a read whose audit write fails is denied. This mirrors the existing write-path posture where an unauditable outcome is not reported as success.

### D7. Collapse the denial at the response-construction layer, not in the adapter

The adapter distinguishes not-found, permission-denied, invalid-request and unsupported-operation internally, because audit and Debug need the distinction. The collapse to one caller-indistinguishable outcome happens where the response is built, so status, body, answer text, sources, confidence and route metadata are all derived from the collapsed result and cannot drift apart.

Anti-oracle reasoning applied beyond the two named cases: field-level denial must also not be distinguishable at the top level. Because a denied field is omitted rather than blanked, the caller must not learn that a document "has no such field" versus "has a field you may not read" — both present as simply absent.

### D8. Authorized context is a typed, bounded, inbound-only field

The gateway adds one Frappe-produced field carrying the authorized result. It is structurally bounded, size-capped, credential-free, and carries no authorization-subject override, so it cannot become a general context-injection channel. It is inbound-only: the existing response-field allowlist is left untouched so authorized context is never relayed back out through the browser-facing result, and no separate response-field design is introduced.

### D9. Disconnect the read path, then deprecate — do not delete the legacy routes in this change

The orchestrator's ERPNext branch stops calling the shared-credential read client. The three direct routes are marked deprecated/quarantined and remain present, service-authenticated, with their non-authorizing access policy stated explicitly.

Trade-off accepted: between the cutover and the later quarantine there is a window in which a service-credential holder could still reach ERPNext through the legacy routes. The window is accepted because deleting routes in the same change removes the cheap rollback. The mitigation is ordering: the cutover lands and is verified well before quarantine, and the residual exposure is recorded rather than glossed.

### D10. Retain the shared credential, scoped and enumerated

The credential stays in the inference environment for the version-lookup utility and the legacy write helpers, which still call the shared credential loader. U5 removes it from the user business-read path only.

Consequence, stated plainly so it is not overclaimed: this change substantially reduces inference-side ERPNext authority and blast radius for business reads; it does **not** reduce inference-side ERPNext risk to zero, and the credential is not removed. No new credential consumer is introduced. Full removal is follow-on work that first has to give the version lookup a credential-free in-process source and give the write path its own identity story.

### D11. Mode is orthogonal to ERPNext authorization

Both personas read business data through the same boundary and the same session user, so the authorized result is mode-independent. Mode keeps its existing meaning for prompts, retrieval scope, code tools and schema capability. No mode-engine change.

### D12. Evidence before cutover, and two-user evidence is required, not optional

The M5 precedent is explicit in the repository: its permission-recheck test asserts actor ownership rather than Frappe permission narrowing, and its permission recheck was never proven live. U5 therefore treats "the test passes" as insufficient.

The negative authorization cases (differing roles, user permission restriction, owner-only restriction, document sharing) can only be demonstrated with a second authenticated user and, for some cases, a user permission and a share row on the test site. Creating those is a test-data change and needs explicit approval. If approval is withheld, the delivered evidence degrades to source plus stub verification — which is precisely the gap M5 left open — and that degradation must be recorded as a limitation rather than reported as acceptance.

## Risks / Trade-offs

- **Field-level regression.** Both current HTTP read paths are field-permission-aware; a naive ORM port would be strictly less safe. → Mitigated by mandatory field-level enforcement plus explicit projection and null-pruning, with a dedicated test asserting a restricted field is absent rather than defaulted.
- **Allowlist too narrow for real use.** An explicit DocType policy may exclude doctypes users legitimately need. → Treat the policy as reviewed configuration with a documented expansion path; do not widen it implicitly from inference output.
- **Bypass window between cutover and quarantine.** Legacy routes still reachable by a service-credential holder. → Ordered delivery, explicit residual-risk record, quarantine as a distinct later step.
- **Migration introduced into a previously migration-free change.** Audit vocabulary addition requires a live DocType option change and migrate. → Declared as an explicit task with rollback, rather than avoided through a silent vocabulary overload.
- **Two-stage flow adds latency and a failure surface.** An extra upstream leg per business read. → Bound the leg, fail closed on its failure, and confirm no impact on turns that need no business read.
- **Two-user evidence may be withheld.** → Record the evidence gap explicitly as a limitation; do not report unit/stub results as live authorization acceptance.
- **Contract mirror drift.** A test pins an app-local mirror to the inference-side contract. → Re-check mirror parity as part of the contract task.
- **Legacy write path still depends on the read module's credential loader.** Blocks deletion of the read client. → Out of scope by decision; enumerated so it is not mistaken for an oversight.

## Migration Plan

Single forward migration, limited to the audit DocType's `action`/`outcome` option lists. Rollback reverts the option lists; historical entries remain valid because the added values are additive. No business data is written or altered.

Deployment order mirrors the task order: adapter and validation first, then audit vocabulary, then audit wiring, then the envelope field, then the orchestrator cutover, then error-collapse behavior, then tests, then evidence, then legacy deprecation, then quarantine, then documentation. Rollback before the cutover is a plain code revert. After the cutover, rollback restores the orchestrator path and the route policy together, so the two are never out of step.
