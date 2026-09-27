## MODIFIED Requirements

### Requirement: Correlated lifecycle audit
The system SHALL record a durable audit trail covering AI requests, permitted retrieval provenance, ERPNext business-data reads, tool calls, proposal creation, approvals/rejections/expiry, executions, successes, denials, failures, and security events. Each record SHALL be linked by authenticated actor, site, and correlation/request/action identifiers. The trail SHALL account for failed and denied actions as well as successes, and for audit-persistence failures themselves. Audit records SHALL include the exact immutable proposal target/payload or diff reference, the approver, the permission recheck result, and the execution outcome.

Every ERPNext business-data read SHALL produce exactly one dedicated ERPNext read audit event, whether it succeeded or was denied, and that action SHALL be distinct from the generic knowledge-retrieval action so record access is never conflated with corpus retrieval in the ledger. Read events SHALL record actor, site, timestamp, operation, DocType, a bounded target document or query identifier, outcome, and correlation identifier, and SHALL distinguish not-found, permission-denied, invalid-request, and success outcomes internally. Read events SHALL carry metadata only and SHALL NOT contain raw ERPNext rows, raw database results, full request payloads, document bodies, field values, filter values, or secrets. Audit persistence is mandatory for reads: if the audit record for a read cannot be written, the read SHALL be denied and no authorized data SHALL be returned, and the failure SHALL be surfaced rather than converted into a successful data response. Where the audit record definition does not yet provide a dedicated ERPNext read action or the required read outcomes, adding them SHALL be performed as an explicit schema change with its migration task recorded, rather than by silently reusing unrelated existing audit vocabulary.

#### Scenario: Full lifecycle traceable
- **WHEN** an observer queries the ledger for a correlation identifier that touched a business write
- **THEN** the ledger returns the linked AI request, tool proposal, approval, recheck, execution attempt, and final outcome, each with actor/site/timestamp, with no missing success or failure leg

#### Scenario: Denied attempt audited
- **WHEN** a tool execution is denied for insufficient permission or expired approval
- **THEN** the denial is recorded with the same actor/site/correlation linkage as a successful execution, distinguished as denied

#### Scenario: Audit persistence failure surfaced
- **WHEN** a business write succeeds but the audit record cannot be persisted durably
- **THEN** the system surfaces the audit-persistence failure, does not claim a complete atomic transaction, and records recovery status once restored

#### Scenario: Successful business read audited
- **WHEN** an authorized ERPNext business read succeeds
- **THEN** exactly one dedicated ERPNext read event is recorded with actor, site, timestamp, operation, DocType, bounded target, success outcome, and correlation

#### Scenario: Denied business read audited distinctly
- **WHEN** a business read is refused for permission, not-found, or invalid request
- **THEN** a dedicated ERPNext read event with the matching internal outcome is recorded under the same actor/site/correlation linkage

#### Scenario: Read events separable from retrieval events
- **WHEN** a correlation includes both an ERPNext business read and a knowledge retrieval
- **THEN** the ledger shows them as separate action types and does not conflate record access with corpus retrieval

#### Scenario: Read audit excludes business content
- **WHEN** a read event is inspected
- **THEN** it carries no document body, field value, filter value, or credential, only bounded metadata

#### Scenario: Read denied when audit cannot be written
- **WHEN** the audit write accompanying a business read fails
- **THEN** no authorized ERPNext data is returned and the audit-persistence failure is surfaced
