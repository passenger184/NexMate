## Purpose

Denied content — cross-site or intra-site unauthorized — never becomes a retrieval candidate, grounded context, citation, or model input; authorization is enforced before retrieval, never by filtering answers afterwards.

## ADDED Requirements

### Requirement: Coarse-grained authorization boundary
NexMate retrieval ACL is a coarse-grained knowledge-access control layer. It SHALL guarantee: pre-retrieval enforcement of intentionally stamped tiers for the requesting scope, and fail-closed exclusion of anything unstamped or out-of-scope. It SHALL NOT guarantee, model, or imply full ERPNext/Frappe DocType, document-level, field-level, or permlevel authorization. Indexed content MUST be intentionally classified and stamped for NexMate retrieval; absence of required ACL metadata is fail-closed (unreachable). A successful NexMate retrieval SHALL NEVER be presented or logged as proof that the user holds full ERPNext permission on the underlying source object.

#### Scenario: Retrieval is not permission proof
- **WHEN** a user receives an answer citing a company document
- **THEN** no response, log, or diagnostic claims the user holds ERPNext permission on that document — only that the stamped tier permitted retrieval

#### Scenario: Unclassified content unreachable
- **WHEN** content exists without intentional ACL classification
- **THEN** it is excluded from every retrieval path even for privileged users

### Requirement: Site authorization before retrieval
Inference SHALL constrain every retrieval path (vector pools and lexical candidates) by the envelope's authorized site before candidate selection. Content from any other site SHALL NOT enter candidates, grounded context, caches, citations, model input, or diagnostics.

#### Scenario: Cross-site content excluded
- **WHEN** the index contains content from another site and an authorized request runs
- **THEN** no other-site content appears in candidates, context, caches, citations, or model input

#### Scenario: Cross-site scope forgery refused
- **WHEN** a request asserts a site that does not match the trusted site binding
- **THEN** the request is refused before any retrieval work

### Requirement: Intra-site authorization before retrieval
Inference SHALL further constrain candidates by the envelope's permitted visibility/roles before selection, using chunk ACL metadata. Site isolation alone SHALL NOT grant intra-site access. Post-retrieval answer filtering SHALL NOT satisfy this requirement; enforcement MUST happen at candidate-selection time on every retrieval path.

#### Scenario: Unauthorized intra-site content excluded
- **WHEN** an authenticated user lacks the required role for restricted content on their own site
- **THEN** that content never enters candidates, context, caches, citations, or model input, while authorized content still retrieves

#### Scenario: Public content remains retrievable
- **WHEN** an authorized user requests public-tier content
- **THEN** it retrieves normally subject to existing confidence and grounding gates

### Requirement: Minimal ACL metadata representation
Every indexed chunk SHALL carry `site` (required), a visibility tier (`public`, `site`, or `restricted`), and, for restricted chunks, an `allowed_roles` list. Ingestion SHALL stamp this metadata; chunks missing valid ACL metadata SHALL NOT be retrievable. The supported model covers exactly these tiers; full ERPNext permission-model parity is deferred and SHALL NOT be implied.

#### Scenario: Unstamped chunks unreachable
- **WHEN** a chunk lacks valid site/visibility metadata
- **THEN** no retrieval path returns it

#### Scenario: Role-gated chunk matches roles
- **WHEN** a restricted chunk allows roles the user holds (per the envelope scope)
- **THEN** it is a candidate; when the user lacks them, it is not

### Requirement: Authorization context source and enforcement boundary
Frappe SHALL derive the authorization scope from the authenticated user on every request (no cross-request caching of grants — NexMate maintains no grant cache of its own; each derivation calls `frappe.get_roles(user)` live, whose result is subject to Frappe's own per-user roles cache; see Revocation caveat) and pass it in the gateway envelope with these normative fields: `site` (required string, equal to the trusted site binding), `tiers` (required non-empty subset of {`public`, `site`, `restricted`}), `roles` (required list of held authorization claims, possibly empty), and `derived_by` (required fixed marker proving Frappe derivation). The scope is per-request and SHALL be re-derived on follow-up turns. Inference SHALL validate its structure, provenance marker, and consistency and enforce it pre-retrieval. Browser-supplied scope is impossible: any client-supplied scope fields SHALL be refused, and FastAPI SHALL NOT independently grant authorization — it validates only structural and provenance consistency. Frappe remains authoritative. Conversation ownership SHALL NOT substitute for knowledge authorization, and knowledge authorization SHALL NOT grant conversation access; the two are independent checks.

#### Scenario: Scope derived server-side only
- **WHEN** a browser supplies its own visibility, roles, or scope overrides
- **THEN** they are refused and only the Frappe-derived scope is used

#### Scenario: Scope shape frozen and validated
- **WHEN** a scope is missing a required field, carries an unknown tier, or lacks the Frappe-derivation marker
- **THEN** the request is refused before history, routing, retrieval, or execution

#### Scenario: Scope re-derived per request
- **WHEN** a user's roles change between two turns of one conversation
- **THEN** the later turn is authorized under the new roles with no stale grant applied

#### Scenario: Ownership is not authorization
- **WHEN** a user owns a conversation but lacks the role for restricted content
- **THEN** chat works but the restricted content never enters retrieval

### Requirement: Revocation and invalidation
While a generation is active, its stamped metadata IS the authorization state. Frappe-side changes (user roles) take effect on the next request because scope is re-derived live per request with no cross-request grant caching (NexMate adds no authorization/grant cache of its own — every `ask()` calls `frappe.get_roles(user)` live; normal User-save role assignment/removal invalidates Frappe's per-user roles cache, but current upstream `Role` DocType deletion does not invalidate that cache). Content-side changes (reclassification) take effect only through re-stamping under a new generation plus retirement of the superseded generation: the old generation MUST NOT serve affected scope after republication, its caches and lexical snapshots SHALL be dropped with it, and it SHALL NOT be reactivated while the revocation stands. Already-delivered answers are historical and cannot be retracted; future requests SHALL never cite retired content. Revocation is complete no later than republication plus retirement; the operational republication bound is set at implementation and enforced by acceptance tests. As an emergency lever independent of re-indexing, Frappe-side scope narrowing (roles/tiers) takes effect immediately on the next request subject to the upstream cache caveat above — deleting a `Role` can leave a stale `frappe.get_roles` result until the underlying cache is invalidated (e.g., User save or explicit cache clear/`hdel`); this is a known upstream Frappe cache-invalidation limitation, not a NexMate-side grant-cache defect, exposed by the M4 live revocation test which used `Role` deletion and is not fixed in M4. Caches and lexical snapshots SHALL be keyed by index generation plus authorization scope. The design SHALL NOT rely on TTL expiration: any TTL would leak denied content within its window.

#### Scenario: Role change effective immediately
- **WHEN** a user's roles are narrowed between two requests
- **THEN** the later request is authorized under the new roles with no stale NexMate grant applied and no re-index required (normal User-save narrowing is immediate; `Role` DocType deletion inherits the upstream Frappe per-user roles-cache caveat noted above)

#### Scenario: Revoked content disappears
- **WHEN** a chunk's allowed roles are narrowed and the generation republishes with the old generation retired
- **THEN** subsequent requests from now-unauthorized users never see it in candidates, context, caches, or citations

#### Scenario: Retired generation stays retired
- **WHEN** a generation is superseded after a revocation
- **THEN** rollback to it is refused while the revocation stands, and its derived caches and snapshots are dropped

#### Scenario: Republication bound enforced
- **WHEN** revocation republication is measured by acceptance tests
- **THEN** it completes within the documented operational bound, and scope-narrowing without re-indexing is immediate subject to the same upstream `Role` deletion cache caveat

### Requirement: Retrieval provenance in results
Retrieved passages and citations SHALL carry source, version, embedding-model, generation, site, and ACL provenance sufficient to explain and validate each result. Diagnostics and transparency outputs SHALL NOT reveal the existence or content of denied sources.

#### Scenario: Provenance explains results
- **WHEN** an answer cites passages
- **THEN** each citation traces to its source, version, generation, and the scope that permitted it

#### Scenario: Denied sources stay invisible in diagnostics
- **WHEN** diagnostics are inspected for a request with denied content in the corpus
- **THEN** they reveal neither the denied content nor its existence
