# Tasks: durable-tool-execution-audit

Planning only — no implementation started. Verification for each task is stated inline. Implementation and evaluation work are separated (sections 2–5 build, section 6 proves).

## 1. Contracts and durable model first

- [x] 1.1 Freeze the explicit tool contract schema (operation, validated bounded inputs/outputs, permission/context, side-effect class, approval flag, typed errors, timeout/cancellation, provenance, audit event) and the durable proposal record fields (`operation`, `target`, `payload|diff`, `reason`, `actor`, `site`, `correlation`, `expiry`, `preconditions`, `status`), and verify they are recorded identically in design and specs with no drift.
- [x] 1.2 Define the DocType/ledger schema and advisory-lock keying for `NexMate Tool Proposal` and the correlated audit record (indexes, states `pending`/`approved`/`rejected`/`executing`/`succeeded`/`failed`/`denied`/`uncertain`, transition rules), and verify a sample proposal and sample audit entry validate against the schema.

## 2. Durable execution enforcement (implementation)

- [x] 2.1 Implement durable proposal creation (Frappe-owned, actor/site-bound, immutable exact payload/diff + hash, correlation, expiry, preconditions) and verify forged actor/site or mutated payload is refused and a new proposal is required for any change.
- [x] 2.2 Implement approval/rejection/expiry/revocation persistence (explicit, durable, actor-bound, expiry enforced) and verify changed payload/target after approval requires new approval and expired/revoked proposals are never executable.
- [x] 2.3 Implement permission/target recheck and concurrency control at execution (re-derive identity/site, revalidate permission/target state and approval validity, advisory/row lock on target key, serialize/reject conflicts, enforce idempotency via idempotency key) and verify concurrent conflicting operations are serialized or rejected with correlated audit and no silent overwrite.
- [x] 2.4 Implement uncertain-outcome handling (typed `uncertain` transport outcome, explicit read-back reconciliation, no blind replay, retry with same idempotency key only after reconciliation) and verify a timed-out write transitions to `uncertain` and reconciles to `succeeded` or `failed` without duplicate application.
- [x] 2.5 Implement the separate confined code/Git executor integration (Frappe-authorized invocation, root-containment, tracked-not-ignored, clean-tree, per-edit atomic-commit for exactly the approved diff) and verify inference cannot execute code directly and the executor refuses mismatched diffs or dirty-tree states.

## 3. Gateway and legacy replacement (implementation)

- [x] 3.1 Replace direct inference tool/proposal/apply paths with gateway-validated, durable-approved-only execution (Frappe-derived identity/scope, envelope validation, `frappe-api-gateway` flows), and verify direct browser→inference tool/proposal/approval calls are impossible and legacy RAM apply paths are removed or refused.
- [x] 3.2 Keep read-only, retrieval, and egress contracts unchanged except for audit/Debug provenance gating, and verify existing M4 ACL and egress negative suites still pass when viewed through the durable path.

## 4. Audit ledger and Debug (implementation)

- [x] 4.1 Implement the correlated durable audit ledger (Frappe-owned, actor/site/correlation/request/action linkage across AI request, retrieval provenance, tool call, proposal, approval/rejection/expiry, execution, success/denied/failed/uncertain/reconciled) and verify every leg is queryable by correlation with no missing success or failure branch.
- [x] 4.2 Implement redaction, access, retention, and tamper controls (sensitive-field minimization, `debug_view`/audit-read permission, retention/deletion per policy, audit-persist failure surfacing as `audit_pending` with repair) and verify secrets never appear in audit or Debug and unauthorized access is refused.
- [x] 4.3 Implement policy-filtered Debug/transparency (role/policy-gated, minimized to actually accessed fields/results/queries where they exist, never revealing denied source existence or sensitive fields, each view audited) and verify denied sources stay invisible and field minimization is exact.

## 5. Topology-agnosticism and deferred-scope guard (implementation)

- [x] 5.1 Verify the implementation references only logical scopes and durable-record contracts with no per-site/shared deployment selection, no production-write authorization, and no MCP/Workbench/SQL-generation selection, and record the compatibility constraints either topology must satisfy.

## 6. Evaluation and verification (no new behavior)

- [x] 6.1 Run the full durable-execution suite proving immutable approval, expiry/rejection enforcement, permission recheck at execution, concurrent conflicting serialization, idempotency, uncertain-outcome reconciliation without blind replay, and typed error/timeout/cancellation behavior, and verify no stale or forged proposal executes.
- [x] 6.2 Run the audit-suite proving correlated success/denied/failed/uncertain/reconciled lifecycle, actor/site linkage, failure-of-audit-persistence handling, redaction, access, retention/deletion, and recovery, and verify no missing or duplicate audit leg and no secret leakage.
- [x] 6.3 Run the Debug-suite proving authorized disclosure shows only permitted provenance/fields/results/queries, denied sources/fields stay invisible, unauthorized access is refused, minimization is exact, and each view is audited.
- [x] 6.4 Run the legacy-replacement negative suite proving direct inference tool/proposal/apply paths are refused before execution and the confined executor boundary is not bypassable, and verify G3/G4 boundary regressions still pass.
- [x] 6.5 Run the contract suite proving explicit tool schemas (bounded inputs/outputs, permission/context, side-effect class, approval flag, typed errors, timeout/cancellation, provenance) are enforced on every entry point and every tool call is validated against its contract.

## 7. Docs and handoff

- [x] 7.1 Document the cutover (legacy RAM proposal migration to durably expired, audit ledger seeding, retention/repair jobs, confinement boundary, no production grants changed) in README/DEVELOPMENT scope and verify the archived M4 change is left untouched.
- [x] 7.2 Record dated evidence, valid-row counts where applicable, and remaining gates in progress files, explicitly listing what was deferred (U1 tenancy, U2 ingestion ownership, U5 permission parity beyond tiers, U8 versioning/packaging, U9 budgets, MCP/Workbench).
