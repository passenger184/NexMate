# durable-tool-execution Specification

## Purpose
Durable, Frappe-owned tool execution with immutable human-approved proposals, rechecked permissions, and a separate confined executor, so business writes and code edits are provably authorized, concurrency-safe, and recoverable.

## Requirements

### Requirement: Durable proposal lifecycle with immutable payload
Frappe SHALL own the durable tool proposal lifecycle end-to-end. For every business write and code edit, Frappe SHALL create a persistent, actor/site-bound proposal recording the exact immutable operation, payload or diff, target, reason, expiry, concurrency preconditions, and correlation identifier. The proposal SHALL be visible for explicit human approval or rejection, and Frappe SHALL persist that decision durably. A changed payload, target, or reason SHALL require a new proposal and a new approval. The proposal record SHALL be immutable after creation except for lifecycle state transitions performed by Frappe.

#### Scenario: Exact payload required for approval
- **WHEN** a user reviews a business-write or code-edit proposal
- **THEN** the presented preview contains the exact immutable HTTP method/URL/body or unified diff, target, and reason that will be executed, and any change creates a new proposal requiring new approval

#### Scenario: Approval and rejection are durable
- **WHEN** an authorized actor approves or rejects a proposal
- **THEN** Frappe persists the decision durably with actor/site/timestamp, and the proposal cannot be executed without that persisted approval

#### Scenario: Expiry and revocation enforced
- **WHEN** a proposal exceeds its expiry or its authorization is revoked
- **THEN** subsequent execution is refused even with a prior approval, and the expiry/revocation is persisted

### Requirement: Authorization recheck and concurrency control at execution
Frappe SHALL recheck the actor/site permission, target state, approval validity, and policy immediately before execution, after expiry/revocation checks. Frappe SHALL serialize or reject conflicting concurrent operations on the same target rather than silently overwriting. Frappe SHALL enforce idempotency and retry semantics and SHALL NOT blindly replay a write whose upstream outcome is uncertain; uncertain outcomes SHALL be reconciled explicitly and recorded.

#### Scenario: Permission recheck before execution
- **WHEN** permissions have narrowed between approval and execution attempt
- **THEN** execution is refused and the denial is audited, even though a prior approval exists

#### Scenario: Concurrent conflicting operations serialized
- **WHEN** two approved proposals target the same document or file concurrently
- **THEN** only one executes or the later is rejected as conflicting, with no silent overwrite and with both outcomes correlated

#### Scenario: Uncertain outcome not blindly replayed
- **WHEN** an execution times out with unknown upstream outcome
- **THEN** Frappe does not automatically retry the same write; it reconciles the upstream state and records the uncertain outcome before any further action

### Requirement: Separate confined code executor
Code/Git execution SHALL be performed by a separate confined executor under Frappe authorization, not by inference. The executor SHALL enforce project-root containment, tracked-not-ignored file checks, clean-tree gating per edit, per-edit confirmed atomic-commit, and shall not acquire ambient write authority. Inference SHALL NOT gain code-write capability and SHALL request tools only through Frappe authorization.

#### Scenario: Executor enforces edit gates
- **WHEN** a code-edit proposal reaches execution
- **THEN** the confined executor verifies project-root containment, that the target is tracked and not ignored, that the working tree is clean, and that the diff matches the approved immutable payload before writing and committing as one atomic commit

#### Scenario: Inference cannot bypass executor
- **WHEN** inference requests a code write directly
- **THEN** the request is refused unless it arrives as a Frappe-authorized, approved durable proposal executed by the confined executor

### Requirement: Read operations are authorized, bounded, and not approval-gated
The explicit tool contract set SHALL describe the ERPNext business-read operation as a read with a declared permission requirement, bounded inputs, bounded outputs, typed errors, a timeout, provenance, and an audit event. A business read SHALL NOT require a durable human-approved proposal, SHALL NOT create or execute one, and SHALL NOT share the write approval lifecycle; approval gating SHALL remain exclusive to side-effecting operations. The read contract's permission requirement SHALL be declared rather than absent, and its authorization SHALL be enforced by the Frappe-native boundary against the live session user. The read contract's bounded inputs SHALL cover operation, DocType, document name, explicit fields, bounded filters, and a maximum list size. The adapter-level maximum list size SHALL be stricter than the general contract maximum and SHALL be recorded as an intentional read-adapter bound, without silently changing unrelated contracts or their existing maxima. Existing write and code-edit contract requirements SHALL be unchanged by this addition.

#### Scenario: Read is not approval-gated
- **WHEN** an authorized ERPNext business read is performed
- **THEN** it succeeds without a durable proposal, approval, or execution record, and no proposal is created for it

#### Scenario: Read contract declares a permission requirement
- **WHEN** the read contract is inspected
- **THEN** it declares a permission requirement rather than declaring no permission, and enforcement occurs against the live session user before data is returned

#### Scenario: Read bounded inputs enforced
- **WHEN** a read request exceeds the declared bounded inputs for operation, DocType, name, fields, filters, or list size
- **THEN** it is rejected before any data access

#### Scenario: Adapter list bound is stricter than the general contract bound
- **WHEN** the adapter-level maximum list size and the general contract maximum are compared
- **THEN** the adapter bound is the stricter of the two and is documented, and no unrelated contract maximum is altered

#### Scenario: Write contracts unchanged
- **WHEN** the write and code-edit contracts are inspected after this change
- **THEN** their approval, permission-recheck, and execution requirements are unchanged
