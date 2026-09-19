## Purpose

A correlated, durable audit ledger linking every AI request, tool decision, proposal, approval, execution, and failure by actor, site, and correlation identifier, with redaction, access control, and recovery guarantees.

## ADDED Requirements

### Requirement: Correlated lifecycle audit
The system SHALL record a durable audit trail covering AI requests, permitted retrieval provenance, tool calls, proposal creation, approvals/rejections/expiry, executions, successes, denials, failures, and security events. Each record SHALL be linked by authenticated actor, site, and correlation/request/action identifiers. The trail SHALL account for failed and denied actions as well as successes, and for audit-persistence failures themselves. Audit records SHALL include the exact immutable proposal target/payload or diff reference, the approver, the permission recheck result, and the execution outcome.

#### Scenario: Full lifecycle traceable
- **WHEN** an observer queries the ledger for a correlation identifier that touched a business write
- **THEN** the ledger returns the linked AI request, tool proposal, approval, recheck, execution attempt, and final outcome, each with actor/site/timestamp, with no missing success or failure leg

#### Scenario: Denied attempt audited
- **WHEN** a tool execution is denied for insufficient permission or expired approval
- **THEN** the denial is recorded with the same actor/site/correlation linkage as a successful execution, distinguished as denied

#### Scenario: Audit persistence failure surfaced
- **WHEN** a business write succeeds but the audit record cannot be persisted durably
- **THEN** the system surfaces the audit-persistence failure, does not claim a complete atomic transaction, and records recovery status once restored

### Requirement: Redaction, access, retention, and tamper resistance
Audit storage SHALL enforce redaction of sensitive fields, role/policy-based access control, tamper-resistance, retention and deletion policy, and restore objectives. Complete lifecycle audit SHALL NOT mean retention of every raw prompt or raw result; content SHALL be minimized and redacted per policy. Secrets and credentials SHALL be excluded from audit records regardless of ordinary content approval.

#### Scenario: Redacted content
- **WHEN** an audit record containing a prompt with a contained secret is inspected
- **THEN** the secret field is redacted while actor/site/action/outcome metadata remains queryable

#### Scenario: Access restricted
- **WHEN** a user without audit-read permission queries the ledger
- **THEN** the request is refused without leaking audit content

#### Scenario: Retention and deletion honored
- **WHEN** retention/deletion policy requires expiry of an audit slice
- **THEN** the slice is deleted or archived per policy and remains inaccessible through the API after deletion

