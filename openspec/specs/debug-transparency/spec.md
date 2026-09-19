# debug-transparency Specification

## Purpose
Policy-filtered transparency that discloses only authorized retrieval provenance, accessed documents/fields, raw results, and generated queries where they exist, never revealing denied sources or sensitive fields.

## Requirements

### Requirement: Authorized disclosure only
The Debug/transparency view SHALL disclose, only when authorized by role/policy, the permitted retrieval provenance, documents and fields actually accessed, raw tool results, and generated database queries only where such queries exist and disclosure is authorized. It SHALL NOT reveal the existence, content, or count of denied sources, denied fields, or other sensitive fields through diagnostics. The view SHALL NOT imply a new SQL-generation capability and SHALL NOT dump raw prompts or model outputs without minimization, redaction, and audit.

#### Scenario: Denied sources stay hidden
- **WHEN** a corpus contains denied restricted chunks and an authorized user inspects Debug for their own request
- **THEN** the view shows only permitted sources that entered candidates/context/citations and omits any indication that denied sources exist

#### Scenario: Unauthorized Debug request denied
- **WHEN** a user without Debug-view permission requests transparency for a prior execution
- **THEN** the request is refused without disclosing provenance, fields, or results

### Requirement: Minimization and audit of Debug access
Debug disclosures SHALL be minimized, redacted, and audited: only the fields and results actually used for the response, with sensitive fields withheld, and each disclosure SHALL be recorded in the audit ledger with actor/site/correlation and policy basis. Debug content SHALL be subject to the same retention/access controls as audit records.

#### Scenario: Field minimization
- **WHEN** an ERPNext document was read with ten fields but only three were returned through the authorized tool contract
- **THEN** Debug shows exactly the three authorized fields and their provenance, not the other seven

#### Scenario: Debug access is audited
- **WHEN** an authorized user views Debug for a correlation identifier
- **THEN** the audit ledger records who viewed which provenance/results and when
