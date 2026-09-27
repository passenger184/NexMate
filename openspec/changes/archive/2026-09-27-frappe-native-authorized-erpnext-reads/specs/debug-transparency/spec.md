## ADDED Requirements

### Requirement: ERPNext read provenance is disclosed separately from retrieval provenance
The Debug/transparency view SHALL disclose authorized ERPNext business-read provenance as a source class distinct from knowledge-retrieval provenance, so an observer can tell record access from corpus access. For a disclosed ERPNext read, the view SHALL report the operation, DocType, the fields actually returned, the row count for list reads, the internal outcome, and the actor/site/correlation linkage, and SHALL NOT reveal a denied record's existence, DocType, name, or any field the requesting user was not authorized to read. A not-found read and a permission-denied read MAY be distinguished from each other inside the authorized Debug view because the view is itself access-controlled, but that distinction SHALL NOT be exposed to the end user through the ordinary response. Disclosure SHALL remain minimized and redacted per the existing Debug policy, and viewing ERPNext read provenance SHALL itself be audited.

#### Scenario: Read provenance is a distinct source class
- **WHEN** an authorized observer opens the Debug view for a correlation containing both an ERPNext business read and a knowledge retrieval
- **THEN** the ERPNext read and the retrieval appear as separate provenance entries rather than one merged source

#### Scenario: Disclosed read provenance is metadata only
- **WHEN** ERPNext read provenance is disclosed
- **THEN** it shows operation, DocType, returned fields, row count where applicable, outcome, and actor/site/correlation, and no returned business values

#### Scenario: Denied read existence stays hidden in Debug
- **WHEN** a read was denied for permission
- **THEN** the Debug view does not reveal that the protected record exists, and does not disclose its name or unauthorized fields

#### Scenario: Not-found and permission-denied separable only in Debug
- **WHEN** a not-found read and a permission-denied read are compared
- **THEN** the authorized Debug view may distinguish them while the end-user response remains identical for both

#### Scenario: Debug view access is audited
- **WHEN** ERPNext read provenance is viewed
- **THEN** the viewing action is recorded in the audit ledger
