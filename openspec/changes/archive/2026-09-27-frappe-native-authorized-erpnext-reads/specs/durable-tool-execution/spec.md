## ADDED Requirements

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
