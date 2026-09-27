# erpnext-authorized-reads Specification

## Purpose
Establishes the Frappe-native authorization enforcement point for ERPNext business-data reads, so that every authenticated read is decided by the requesting user's own Frappe permissions rather than by a shared integration credential, with mandatory field-level enforcement, minimized results, fail-closed audit, and externally indistinguishable denial behavior.

## Requirements

### Requirement: Frappe session identity is the sole authorization subject
An ERPNext business-data read SHALL be authorized only against the authenticated Frappe session user, derived from the real Frappe request session. The read interface SHALL NOT accept `user`, `actor`, `username`, `site`, `mode`, or any equivalent authorization subject as a caller- or requester-supplied parameter, in any position or encoding. A read request that carries or attempts to carry an authorization subject SHALL be rejected without performing any read. Guest and unauthenticated callers SHALL be refused. The requesting service and the language model SHALL NOT be able to select, assert, or influence the authorization subject. Identity SHALL NOT be normalized, repaired, or case-folded to reach a decision.

#### Scenario: Read interface exposes no authorization parameter
- **WHEN** the read interface is inspected for authorization-subject parameters
- **THEN** it exposes none, and any attempt to pass one is refused before a read occurs

#### Scenario: Forged identity in the read request
- **WHEN** a read request contains a user, actor, username, site, or mode field
- **THEN** the request is rejected and no ERPNext record is read

#### Scenario: Guest is refused
- **WHEN** a Guest or unauthenticated caller requests a business-data read
- **THEN** the read is refused with no data returned and no upstream call

#### Scenario: Requester cannot assert an identity
- **WHEN** inference or the language model attempts to state which user the read is for
- **THEN** the assertion has no effect on authorization and the session user remains the subject

### Requirement: Native Frappe permission enforcement is mandatory
ERPNext business-data reads SHALL be executed through Frappe's native permission-aware APIs, which enforce role/DocType permissions, user permissions, document ownership and `if_owner` rules, document sharing, and permission query conditions. List reads SHALL use the permission-checking list API. Single-document reads SHALL perform an explicit permission check and SHALL additionally apply field-level read permissions before any serialization. Permission-bypassing interfaces SHALL NOT be used on the read path, including the non-checking list API, raw SQL, direct value/count helpers, direct query-builder access that is not permission-configured, and any document flags that suppress permission checks. Switching the session to another user to assume a caller's identity SHALL NOT be used. The read path SHALL NOT be permitted to run outside a live Frappe request session, because the session identity is not available to any other process.

#### Scenario: Denied document is not returned
- **WHEN** the session user lacks read permission on a document
- **THEN** no document content is returned and the read is treated as a denial

#### Scenario: List results are permission-filtered
- **WHEN** the session user lacks permission on some records of a listed DocType
- **THEN** only the permitted records are returned and the filtering is performed by the permission engine before the data is serialized

#### Scenario: User permission restricts rows
- **WHEN** a user permission restricts the session user to a subset of records
- **THEN** records outside that subset are absent from the result

#### Scenario: Owner-only permission enforced
- **WHEN** a permission is granted only if the user is the document owner
- **THEN** a non-owner receives no access and an owner receives access

#### Scenario: Sharing respected
- **WHEN** a document is shared with the session user
- **THEN** the shared grant is honored as the permission engine defines it

#### Scenario: Identity is not assumable
- **WHEN** the read path executes
- **THEN** it runs only under the current Frappe session and never switches the session user to impersonate a caller

### Requirement: Strict read-request validation
The read interface SHALL validate every request against an explicit contract before any data access, and SHALL reject rather than silently rewrite, relax, or partially apply an invalid request. The contract SHALL constrain: operation to an explicit supported set; DocType to an explicit approved policy; document name to a bounded, validated value; fields to an explicit, non-wildcard projection validated against the target DocType; filters to a structurally bounded, operator-allowlisted form; and list size to a bounded maximum. Raw SQL, arbitrary field expressions, aggregate or pseudo-column terms, unsupported operators, unbounded filter nesting, wildcard field requests, unknown fields, and unauthorized fields SHALL be rejected. An operation outside the supported set SHALL be rejected, and the interface SHALL NOT implement write, update, delete, arbitrary method invocation, or DocType schema/metadata operations. The interface SHALL be a constrained business-data interface and SHALL NOT be a generic ORM proxy.

#### Scenario: Valid document read
- **WHEN** a supported operation, an approved DocType, a bounded name, and explicit permitted fields are requested
- **THEN** the read proceeds against the permission engine

#### Scenario: Wildcard fields rejected
- **WHEN** a request asks for all fields
- **THEN** it is rejected before any data access and no record content is returned

#### Scenario: Unknown field rejected
- **WHEN** a request names a field that is not in the approved projection for that DocType
- **THEN** it is rejected before any data access

#### Scenario: Unsafe filter rejected
- **WHEN** a request contains a raw expression, an unsupported operator, unbounded nesting, or an unsafe field reference in its filters
- **THEN** it is rejected before any data access and is not rewritten into a different query

#### Scenario: Unsupported operation rejected
- **WHEN** a request asks for an operation outside the supported set, including a schema/metadata or write-shaped operation
- **THEN** it is rejected and no read is performed

#### Scenario: Oversized list refused
- **WHEN** a list request exceeds the adapter's maximum size
- **THEN** it is rejected or clamped to the documented bound, and the bound is smaller than the general tool-contract maximum

### Requirement: Field-level enforcement precedes serialization
Field-level read permission SHALL be enforced before any result is serialized or returned, and results SHALL be returned only for the explicit requested and permitted fields. A user's authorization to open a document SHALL NOT imply that the whole document is returned. Fields the session user may not read SHALL NOT appear in the result, and SHALL NOT be emitted as a plausible-looking type default, empty placeholder, or masked surrogate. Child-table content SHALL be handled so that a permitted parent field does not cause unrestricted child rows or unauthorized child fields to be returned. Enforcing field-level permission only by a serialization helper that ignores document state SHALL NOT be relied on.

#### Scenario: Restricted field absent from result
- **WHEN** a requested field is at a permission level the session user cannot read
- **THEN** it is absent from the returned data and is not replaced by a type-default or placeholder value

#### Scenario: Wildcard does not widen the result
- **WHEN** an authorized user can open a document
- **THEN** only the explicit requested permitted fields are returned, not the full document

#### Scenario: Child tables do not widen the result
- **WHEN** a permitted field links to a child table containing fields the session user cannot read
- **THEN** only the permitted child fields are returned, or the child content is omitted

### Requirement: Results are minimized to what the answer needs
The read path SHALL return only the data required to answer the request, and SHALL NOT return whole documents merely because the session user is permitted to open them. Returned structure SHALL be bounded and SHALL identify the DocType, the operation, the fields actually returned, and the row count for list results. The read path SHALL NOT return a document name that was not itself returned, and SHALL NOT return unrestricted DocType metadata or field definitions.

#### Scenario: Minimized document result
- **WHEN** a document read succeeds
- **THEN** the result contains only the requested permitted fields plus bounded result metadata

#### Scenario: Bounded list result
- **WHEN** a list read succeeds
- **THEN** the result contains only the requested permitted fields per row, within the maximum size, plus a row count

### Requirement: Every business read emits one metadata-only audit event
Every ERPNext business-data read SHALL produce exactly one structured audit event, whether it succeeds or is denied. The event SHALL use a dedicated ERPNext read action and SHALL NOT reuse the generic knowledge-retrieval action, so ERPNext record access remains distinguishable from corpus retrieval in the ledger. The event SHALL record actor, site, timestamp, operation, DocType, target document or query identifier, outcome, and correlation identifier, where the target and query identifier are recorded as bounded identifiers. The event SHALL contain metadata only: it SHALL NOT contain raw ERPNext rows, raw database results, full request payloads, field values, filter values, document bodies, credentials, or secrets. Internal outcomes SHALL distinguish not-found, permission-denied, invalid-request, and success. If the audit record cannot be written, the read SHALL be denied and no authorized data SHALL be returned; an audit failure SHALL NOT be converted into a successful business-data response. Adding a dedicated action or outcome to the audit record definition SHALL be performed as an explicit schema change, not by silently overloading unrelated existing audit vocabulary.

#### Scenario: Successful read audited
- **WHEN** an authorized business read succeeds
- **THEN** exactly one ERPNext read audit event is recorded with actor, site, operation, DocType, target, outcome, and correlation

#### Scenario: Denied read audited
- **WHEN** a read is refused for permission, not-found, or invalid request
- **THEN** the refusal is recorded as an ERPNext read audit event with a distinct internal outcome and the same actor/site/correlation linkage

#### Scenario: Audit contains no business data
- **WHEN** an audit event for a business read is inspected
- **THEN** it contains no document body, field value, filter value, or credential, only bounded metadata

#### Scenario: Audit failure denies the read
- **WHEN** the audit write for a read fails
- **THEN** no authorized ERPNext data is returned and the failure is surfaced

#### Scenario: Read events are distinguishable from retrieval
- **WHEN** the ledger is queried for a correlation that included both a business read and a knowledge retrieval
- **THEN** the two appear as distinct action types rather than one conflated retrieval event

### Requirement: Denial does not disclose document existence
A read that fails because a document does not exist and a read that fails because the session user is not permitted to read it SHALL be externally indistinguishable. Both SHALL produce the same user-facing outcome, the same HTTP status, the same answer text, the same source list, the same confidence, and the same route metadata. The same anti-oracle rule SHALL apply to related failure paths where a distinguishable outcome would reveal whether a protected record exists. The system MAY distinguish the conditions internally for audit and authorized debugging, and that distinction SHALL NOT be observable by the caller.

#### Scenario: Not found and forbidden are indistinguishable
- **WHEN** a caller requests a document that does not exist, and separately a document that exists but is not permitted
- **THEN** the caller receives the same denial in status, body, sources, confidence, and route metadata

#### Scenario: Internal distinction is not caller-observable
- **WHEN** a denial occurs
- **THEN** the audit record and authorized debug view may distinguish not-found from permission-denied while the caller-observable response does not

### Requirement: NexMate may narrow but never widen access
The NexMate layer SHALL only further restrict what the Frappe permission engine authorizes. Effective ERPNext access SHALL equal Frappe-authorized access intersected with NexMate-allowed access. No NexMate policy, configuration, role mapping, mode, cache, or convenience behavior SHALL expand access beyond what the Frappe permission engine authorizes for the session user. Authorization SHALL be re-derived per read against live Frappe state; NexMate SHALL NOT cache or reuse an authorization grant across requests.

#### Scenario: NexMate policy cannot expand access
- **WHEN** a NexMate policy would permit an operation or field the Frappe permission engine denies
- **THEN** the denial holds and access is not expanded

#### Scenario: Authorization is re-derived per read
- **WHEN** a user's Frappe permissions are narrowed between two reads
- **THEN** the later read reflects the narrowed permissions without requiring a restart or a NexMate-side cache flush

### Requirement: Mode is not ERPNext authorization
The existing developer and employee personas SHALL be retained and SHALL continue to control prompt, knowledge-retrieval scope, code-tool availability, and other existing NexMate capabilities. Mode SHALL NOT determine ERPNext record authorization. Both modes SHALL read ERPNext business data exclusively through the same Frappe-native authorization boundary, and the same session user SHALL receive the same authorized ERPNext result in either mode. This change SHALL NOT redesign the mode engine or the role mapping that derives it.

#### Scenario: Mode does not change row authorization
- **WHEN** the same session user performs the same business read in developer mode and in employee mode
- **THEN** the authorized ERPNext result is identical in both modes

#### Scenario: Mode capabilities unchanged
- **WHEN** a read is requested in either mode
- **THEN** existing per-mode restrictions on prompts, retrieval scope, and code tools are unchanged

### Requirement: Inference holds no ERPNext business-read authority
The inference service SHALL NOT query ERPNext business records for authenticated user reads, SHALL NOT hold the shared ERPNext credential for that purpose, and SHALL NOT impersonate a Frappe user. Inference MAY request a read and MAY consume the authorized, minimized result that Frappe produces, but it SHALL NOT authorize, execute, or expand a read. A read request originating from inference or from a language model SHALL be treated as untrusted input subject to the same validation as any other requester. Inference SHALL NOT receive unrestricted ERPNext documents, ERPNext credentials, or an authorization-subject override through the authorized-context channel.

#### Scenario: Inference read request is untrusted
- **WHEN** inference emits a structured ERPNext read request
- **THEN** it is validated against the read contract and executed only by Frappe under the session user

#### Scenario: Inference operates without the read credential
- **WHEN** the inference service runs with the shared ERPNext credential absent
- **THEN** an authorized ERPNext answer can still be produced through the Frappe read boundary

#### Scenario: Authorized context carries no credentials
- **WHEN** the authorized context is inspected
- **THEN** it contains only bounded authorized data and result metadata, with no credential and no authorization-subject override

#### Scenario: Language model cannot expand access
- **WHEN** a user asks the model to ignore its rules, read all records, call ERPNext directly, or obtain hidden fields
- **THEN** the request is constrained to the validated read contract, authorized by Frappe, and limited to the explicit permitted projection
