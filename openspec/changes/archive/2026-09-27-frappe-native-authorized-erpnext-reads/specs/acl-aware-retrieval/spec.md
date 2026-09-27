## ADDED Requirements

### Requirement: Knowledge retrieval ACL is distinct from ERPNext business-record authorization
Knowledge-retrieval ACL and ERPNext business-record authorization SHALL remain separate authorization mechanisms, and neither SHALL be evidence for the other. The retrieval ACL SHALL continue to be a deliberately coarse, tier-and-role layer over stamped corpus metadata, and SHALL continue to NOT guarantee, model, or imply full ERPNext/Frappe DocType, document-level, field-level, or permlevel authorization. A successful knowledge retrieval SHALL still never be presented or logged as proof that the user holds full ERPNext permission on the underlying source object. The Frappe-native business-read authorization boundary SHALL NOT be extended to the knowledge corpus, and the retrieval ACL SHALL NOT be extended to model ERPNext permission semantics. Where a single response contains both corpus-derived content and Frappe-authorized ERPNext business data, the two provenance classes SHALL be distinguishable, and only the ERPNext business-data portion SHALL carry Frappe permission assurance.

#### Scenario: Retrieval success is still not permission proof
- **WHEN** a knowledge retrieval succeeds for a user
- **THEN** no response, log, or diagnostic claims the user holds ERPNext permission on that document, and the retrieval tier alone is cited as the permitting condition

#### Scenario: Business reads do not widen retrieval
- **WHEN** a user obtains Frappe-authorized access to an ERPNext business record
- **THEN** that access does not grant or imply any additional corpus retrieval tier, and the retrieval scope is still re-derived per request

#### Scenario: Retrieval does not gain ERPNext permission modeling
- **WHEN** the retrieval ACL is evaluated
- **THEN** it continues to enforce only stamped tiers and roles, and does not attempt DocType, document, field, or permlevel permission modeling

#### Scenario: Mixed-provenance response keeps the classes separable
- **WHEN** one response draws on both corpus retrieval and a Frappe-authorized ERPNext read
- **THEN** the corpus-derived portion is presented as retrieval-scope provenance and only the ERPNext portion is presented as Frappe-permission-authorized
