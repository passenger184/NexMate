## Why

Tool execution today is process-local, post-execution, and unbound: proposals live in memory with no durable actor/site binding, no immutable approved payload, no recheck at execution, no expiry/rejection/idempotency, and no correlated audit across AI, retrieval, tool, proposal, approval, execution, and failure paths. This leaves production business writes and code edits without provable human approval, concurrency safety, or recovery from uncertain outcomes. M5 must make durable execution and complete audit the production contract.

## What Changes

- Frappe owns the durable tool proposal lifecycle end-to-end: create immutable proposal (actor, site, operation, exact payload/diff, target, reason, expiry, concurrency preconditions), persist approval/rejection by an authorized actor, enforce ownership, expiry, revocation, and permission recheck immediately before execution, serialize conflicting operations, and correlate attempts/outcomes with idempotency/retry semantics and uncertain-outcome reconciliation.
- Explicit authorized tool contracts for every entry point (read, retrieval, code search, code edit, business write): validated bounded inputs/outputs, required permission/context, side-effect class, approval requirement, typed errors, timeout/cancellation, provenance, and audit events. No new general SQL-generation tool.
- Separate confined code/Git executor under Frappe authorization (placement/transport still unresolved but bounded by root-scoping, tracked-not-ignored, clean-tree, per-edit confirmed atomic-commit, and executor isolation). Inference never acquires ambient write authority.
- Complete correlated audit ledger (Frappe-owned, durable, tamper-resistant access controls): AI requests, permitted retrieval provenance, tool calls, proposal creation, approvals/rejections/expiry, executions, successes/denials/failures, security events — linked by actor/site/correlation identifiers, with redaction, retention/deletion, and recovery guarantees. Existing Git/JSONL/local telemetry is partial evidence, not this lifecycle.
- Policy-filtered Debug/transparency view (role/policy-gated) disclosing permitted retrieval provenance, documents/fields accessed, raw results, and generated queries only where queries exist and disclosure is authorized — minimized, redacted, audited, never revealing denied source existence or sensitive fields.
- **BREAKING (bounded):** business writes and code edits require durable Frappe-approved proposals; direct inference tool calls and process-local apply paths are replaced by gateway-validated, envelope-authorized flows.

## Capabilities

### New Capabilities

- `durable-tool-execution`: durable, actor/site-bound proposal lifecycle, immutable payload/diff, expiry/rejection, permission recheck at execution, concurrency and idempotency, uncertain-outcome reconciliation, and separate confined code executor.
- `audit-ledger`: correlated durable audit of AI requests, retrieval, tool calls, proposals, approvals/rejections/expiry, executions, successes/denials/failures, and security events with actor/site/correlation, redaction, access, retention, and recovery.
- `debug-transparency`: policy-filtered provenance/results/field/query disclosure only where authorized, minimized and audited, never leaking denied sources.

### Modified Capabilities

- `frappe-api-gateway`: envelope and methods gain durable tool proposal/approval flows via Frappe only, validated like chat; browser never calls inference directly for tools, proposals, or approvals.
- `endpoint-access-control`: authorization before retrieval/execution enforced on every entry point including legacy/direct tool replacements, using Frappe-derived identity/scope, never client-supplied mode, LLM output, or post-filtering.

## Impact

- Inference: tool dispatch replaced by gateway-validated, scope-checked, durable proposal execution; executor and audit boundaries added; provider/egress and retrieval ACL contracts unchanged but now audited.
- Frappe app: durable `NexMate Tool Proposal` records, proposal/approval/expiry/recheck, confined executor integration, audit ownership, and Debug disclosure gating; migration/compatibility for legacy RAM proposals.
- Operators: durable storage, retention, backup/restore, and recovery verification for proposals and audit; no new infrastructure or production-write authorization implied.
- Out of scope: production-write approval for a specific environment, private-data cloud consent, MCP, Developer Workbench, search-engine changes, and multi-workspace routing — all remain deferred.
