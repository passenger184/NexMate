# Implementation Tasks — U5 Frappe-Native Authorized ERPNext Reads

Ordered by dependency. Each task states its own verification. Do not begin implementation until this change is approved.

## 1. Re-verify the Frappe 16.31.0 read contract before coding

- [x] 1.1 Re-verify against the installed Frappe 16.31.0 source that the permission-checking list API enforces DocType gate, row conditions (owner constraint or user permissions, plus permission-query hooks and server scripts, AND-ed) and shared-document OR, and that it filters the field projection so a wildcard request is re-expanded to the permitted set rather than issuing a raw select — record file/line anchors in the change notes; verification: anchors recorded and consistent with `design.md` Context
- [x] 1.2 Re-verify that a single-document load performs no permission check by default, that the explicit document check is DocType/document-level only, and that field-level read permissions are a separate explicit step invoked by the API/handler layers rather than by the document getter — verification: anchors recorded and the three steps are confirmed distinct
- [x] 1.3 Re-verify that serialized document output takes its key set from the DocType definition and its values from the in-memory document, so a field removed by the field-level step still appears coerced to its type default unless nulls are pruned — verification: demonstrate the type-default emission on a Single-doctype permission-level field and record the observed value
- [x] 1.4 Re-verify that the non-checking list API, raw SQL and direct value/count helpers perform no permission check, that the low-level query-builder engine defaults to permissions disabled, and that session-user switching rebinds the session and that an administrator identity bypasses all checks — verification: anchors recorded for each forbidden entry in the spec
- [x] 1.5 Record any divergence between the re-verified behavior and `design.md` Context as a change-note entry and stop for review if a divergence would change the specified contract — verification: no unreconciled divergence remains, or the change is halted and reported

## 2. Audit vocabulary and migration

- [x] 2.1 Add a dedicated ERPNext-read action option and the required read outcome options to the audit DocType definition rather than reusing the generic retrieval action — verification: the DocType definition contains the new options and the existing retrieval action is unchanged
- [x] 2.2 Confirm the audit write helper accepts the new action and outcome values and records actor, site, correlation, request identifier, operation, DocType, bounded target and outcome — verification: a unit test writes each new action/outcome pair through the existing helper and reads it back
- [x] 2.3 Apply the DocType option change on the approved test site and verify the migration completes and existing audit rows remain readable — verification: migration exits successfully and pre-existing entries are still queryable; requires explicit approval before running
- [x] 2.4 Document the migration and its rollback (revert the option lists; entries remain valid because the values are additive) in the change notes — verification: rollback steps are written down and reviewed

## 3. Read adapter foundation

- [x] 3.1 Create the adapter module inside the Frappe application boundary, importing no repo-root `tools`, `config`, `service`, `rag` or `orchestrator` modules — verification: the Frappe-isolation test that forbids those imports passes with the new module present
- [x] 3.2 Derive the authorization subject solely from the authenticated Frappe session, refusing absent and guest sessions, with no normalization, repair or case folding — verification: a test asserts the subject is the session value verbatim and that a guest call is refused before any read
- [x] 3.3 Define the read request type supporting only operation, DocType, document name, explicit fields, bounded filters and list limit, and confirm the public entry point exposes no user, actor, username, site or mode parameter — verification: signature inspection test plus an assertion that passing any such argument is rejected
- [x] 3.4 Reject any read request that carries an authorization-subject field in its payload, before any data access — verification: a test supplies forged identity fields and asserts rejection with no read performed
- [x] 3.5 Obtain the site solely from the Frappe local site context and record it for audit and cross-site checks — verification: a test asserts the recorded site equals the current site and that a caller-supplied site is ignored and rejected

## 4. Strict request validation

- [x] 4.1 Restrict operation to the supported set and reject schema/metadata, write, update, delete and arbitrary method-invocation operations with a typed unsupported-operation error — verification: a parameterized test asserts each rejected operation and that no read occurs
- [x] 4.2 Enforce an explicit approved-DocType policy and reject a DocType outside it, including child and single DocTypes — verification: a test asserts an unapproved DocType is rejected and an approved one proceeds to validation
- [x] 4.3 Validate the document name as bounded and well-formed for document operations and require it only for that operation — verification: tests assert rejection of an over-long, empty or malformed name and acceptance of a valid one
- [x] 4.4 Reject wildcard field requests, unknown fields, unauthorized fields and non-string field entries, and require an explicit non-empty field projection — verification: parameterized tests assert each rejection occurs before any data access
- [x] 4.5 Enforce a bounded filter grammar with an operator allowlist, bounded key and nesting counts, and rejection of raw expressions, unsupported operators and unsafe field references; never rewrite an invalid request into a different query — verification: parameterized tests assert rejection, and a test asserts an invalid request is refused rather than coerced
- [x] 4.6 Enforce the adapter-level list maximum that is stricter than the general tool-contract maximum, and record both values in the change notes without altering unrelated contract maxima — verification: a test asserts the adapter bound rejects an oversized request and a note confirms the general contract maximum is unchanged
- [x] 4.7 Emit a typed invalid-request error carrying a bounded, non-sensitive reason — verification: a test asserts the typed error and that the reason contains no credential or raw payload

## 5. Permission-aware execution, field enforcement and minimization

- [x] 5.1 Implement the list read through the permission-checking list API only, with the validated explicit field projection and bounded limit — verification: a test asserts the permission-checking list call is used and the non-checking list call is never invoked
- [x] 5.2 Implement the document read as explicit permission check followed by explicit field-level read-permission application — verification: a test asserts both steps run in order and that omitting either causes a failure
- [x] 5.3 Build the returned document data from the explicit requested-and-permitted field list with nulls pruned, so a field removed by the field-level step can never be emitted as a type default or placeholder — verification: a test on a permission-level field asserts the field is absent from the result rather than present with a default value
- [x] 5.4 Handle child-table content so a permitted parent field does not expose unauthorized child fields or unrestricted child rows — verification: a test asserts child content is projected to permitted fields or omitted
- [x] 5.5 Return a bounded result carrying DocType, operation, the fields actually returned, row count for list reads, and no document name that was not itself returned, and no DocType metadata or field definitions — verification: a test asserts the exact result key set and that requesting metadata yields no metadata
- [x] 5.6 Assert in code and in tests that the forbidden permission-bypassing APIs are unreachable from the adapter, including the non-checking list call, raw SQL, direct value and count helpers, unconfigured query-builder access, permission-suppressing document flags, and session-user switching — verification: a static or behavioral test asserts each is not used and that no session-user switch occurs during a read
- [x] 5.7 Re-derive authorization on every read with no NexMate-side authorization or grant cache, so a permission narrowing between reads takes effect on the next read without restart — verification: a test narrows a stubbed permission between two reads and asserts the second reflects it

## 6. Audit wiring and fail-closed behavior

- [x] 6.1 Emit exactly one dedicated ERPNext-read audit event per read attempt, successful or denied, carrying actor, site, timestamp, operation, DocType, bounded target or query identifier, outcome and correlation — verification: a test counts exactly one event for a successful read and exactly one for each denial kind
- [x] 6.2 Keep read events metadata-only, excluding document bodies, field values, filter values, raw database results, full request payloads and credentials, and set the redaction marker appropriately — verification: a test seeds a marker value in the data and asserts it appears nowhere in the event
- [x] 6.3 Distinguish not-found, permission-denied, invalid-request and success as distinct internal outcomes, and assert read events remain distinguishable from retrieval events for the same correlation — verification: a test writes both a read and a retrieval event under one correlation and asserts distinct action types
- [x] 6.4 Deny the read and return no authorized data when the audit write fails, and surface the failure rather than reporting success — verification: a test forces the audit write to raise and asserts no data is returned and the failure is surfaced
- [x] 6.5 Confirm the existing audit access control still scopes read-event queries to the owning actor and site — verification: a test asserts a foreign actor or site cannot read the correlation's read events

## 7. Bounded authorized context across the gateway

- [x] 7.1 Add one Frappe-produced authorized-context field to the gateway request it builds for a turn that requires business data, populated only from the adapter's authorized, minimized, bounded result — verification: a test asserts the field is Frappe-produced, contains no credential and no authorization-subject override, and is absent when no business read occurred
- [x] 7.2 Bound the authorized-context field's structure and size, and validate it on the inference side using the existing envelope-validation pattern — verification: tests assert an over-large, malformed or wrongly typed field is refused before any use
- [x] 7.3 Extend the inference request model to accept the authorized-context field, since the model forbids extra fields and would otherwise reject the envelope — verification: a test asserting a valid envelope is accepted and an unknown field is still refused
- [x] 7.4 Preserve the existing browser-facing response-field allowlist and upstream response size bound unchanged, and confirm authorized context is never relayed back in the browser-facing result — verification: a test asserts the response key set is exactly the pre-existing allowlist
- [x] 7.5 Assert a browser cannot supply the authorized-context field or an ERPNext read field, and that such an attempt is refused with no read performed — verification: a test supplies the field from the browser side and asserts refusal

## 8. Orchestrator cutover and disconnect from the shared-credential read client

- [x] 8.1 Change the orchestrator's ERPNext branch to request business reads as untrusted read requests and to consume only the authorized context returned by Frappe, never authorizing or executing a read itself — verification: a test asserts the branch performs no read client call and no permission decision
- [x] 8.2 Remove the authenticated user business-read path's calls to the shared-credential read client so the user read path no longer uses it — verification: a test poisons the shared-credential read client and asserts a business read still succeeds through the authorized context
- [x] 8.3 Remove the per-mode schema capability from the business-read adapter path and leave schema behavior under its existing per-mode policy — verification: a test asserts the adapter rejects a schema operation in both modes and that existing mode behavior is unchanged
- [x] 8.4 Confirm mode remains orthogonal to ERPNext authorization: the same session user receives the same authorized result in developer and employee mode — verification: a test runs the identical read in both modes and asserts identical authorized output
- [x] 8.5 Update the read tool contract to declare a permission requirement, bounded field and filter inputs, and explicit no-approval read semantics distinct from approval-gated writes, leaving write and code-edit contracts unchanged — verification: contract tests assert the read contract's new declaration and that write contract requirements are unchanged
- [x] 8.6 Re-check the app-local lifecycle-status mirror against the inference-side contract after the contract edit — verification: the mirror-drift test passes

## 9. Anti-oracle external error behavior

- [x] 9.1 Collapse not-found and permission-denied to one caller-indistinguishable outcome at the response-construction layer, so status, body, answer text, sources, confidence and route metadata are all derived from the collapsed result — verification: a parameterized test asserts every one of those response facets is byte-identical for a missing document and a forbidden document
- [x] 9.2 Assert field-level denial is also not distinguishable from field absence at the top level, since a denied field is omitted rather than blanked — verification: a test asserts a denied field and an absent field produce the same observable result
- [x] 9.3 Confirm the internal distinction remains available to the audit event and the authorized Debug view while remaining unobservable to the caller — verification: a test asserts audit and Debug distinguish the two cases and the caller-facing response does not
- [x] 9.4 Assert unrelated read failure paths do not introduce a caller-observable existence signal, including validation failures that name a DocType or document — verification: a test asserts validation and read failures are not distinguishable in a way that reveals record existence

## 10. Test suite: unit, integration and security

Cover the full approved acceptance matrix; each item names its test.

- [x] 10.1 Identity: assert the read interface exposes no authorization-subject parameter, and that forged identity fields are rejected and cannot change the subject — verification: L-1 and L-2 pass
- [x] 10.2 Role authorization: assert two users with different effective Frappe permissions receive different authorized row sets for the same read request — verification: L-3 passes
- [x] 10.3 User permissions: assert a user-permission restriction removes out-of-scope records from the result — verification: L-4 passes
- [x] 10.4 Ownership: assert an owner-only permission grants the owner and denies a non-owner — verification: L-5 passes
- [x] 10.5 Sharing: assert a shared document is honored as the permission engine defines it — verification: L-6 passes
- [x] 10.6 Field permissions: assert wildcard and unauthorized permission-level fields cannot reach inference and are absent rather than defaulted — verification: L-7 passes
- [x] 10.7 Not-found versus forbidden: assert both produce the same external response — verification: L-8 passes
- [x] 10.8 Mode independence: assert developer and employee mode do not change underlying row authorization — verification: L-9 passes
- [x] 10.9 Inference isolation: assert the inference service operates with the ERPNext read credential absent and that the read path never calls the shared-credential read client — verification: L-10 passes
- [x] 10.10 Malicious request rejection: assert hostile model-generated doctypes, wildcard fields, raw filter expressions and unknown fields are rejected before ORM execution — verification: L-11 passes
- [x] 10.11 Audit: assert every business read produces exactly one metadata-only event, permitted and denied alike — verification: L-12 passes
- [x] 10.12 Site binding: assert read audit records the authenticated Frappe site and that caller-supplied site assumptions are not trusted — verification: L-13 passes
- [x] 10.13 Legacy endpoints after quarantine: assert the deprecated user-read endpoints refuse the old shared-credential user read path and that no user read path reaches the shared-credential read client — verification: L-14 passes
- [x] 10.14 Isolation: assert the Frappe application isolation test still passes with the adapter present and importing no repo-root modules — verification: L-15 passes
- [x] 10.15 Boundary bounds: assert authorized-context structure and size bounds and the existing response bounds remain enforced — verification: L-16 passes
- [x] 10.16 Update the existing suites that mock the shared-credential read client, the boundary suite that poisons those calls, the routing evaluation fixtures, the mode tests, and the read-client unit tests, retaining the client tests needed for the retained legacy write path — verification: the full existing suite passes with no test deleted solely to make the change pass
- [x] 10.17 Run the full existing test suite and the Node harness, and confirm no test now asserts behavior that contradicts the new contract — verification: full suite green, with any behavioral assertion change individually justified in the change notes

## 11. Approved live verification

- [x] 11.1 Obtain explicit approval before creating or modifying any test user, user permission, or document share on the test site, and record the approval and its scope — verification: approval recorded; no test data is created without it
- [x] 11.2 With approval, provision a second authenticated test user with deliberately different effective ERPNext permissions, plus a user-permission restriction, an owner-only case, and a share case — verification: fixtures exist and their permission state is recorded; skipped and recorded as a limitation if approval is withheld
- [x] 11.3 Run the allowed/denied matrix across at least two authenticated users for both document and list reads, and record date, environment, artifact, result and limitations — verification: a dated evidence record exists and is reproducible
- [x] 11.4 Run the same read in both modes for the same user and record that authorized rows are identical — verification: recorded in the evidence
- [x] 11.5 Verify field-level enforcement on a permission-level field for a user lacking that permission level, and record that the field is absent rather than defaulted — verification: recorded in the evidence
- [x] 11.6 Verify audit events exist for permitted and denied reads, that the failure case denies the read, and that events contain no business data — verification: recorded in the evidence
- [x] 11.7 Verify the inference service answers an authorized business read with the ERPNext read credential absent from its environment, and that the user read path makes no shared-credential read call — verification: recorded in the evidence
- [x] 11.8 Record any evidence that could not be obtained, and state plainly which acceptance items rest on source and stub verification only — verification: the limitations section names every such item; no unit or stub result is reported as live authorization acceptance

## 12. Legacy endpoint deprecation and quarantine

- [x] 12.1 Mark the three legacy ERPNext read routes deprecated and quarantined for authenticated user business reads, retaining them in the route inventory behind the existing service-authentication gate — verification: route inventory comparison shows all pre-existing routes still present
- [x] 12.2 State their remaining access policy explicitly as service access without authenticated user attribution, and ensure they are not presented as a user-authorized interface — verification: documentation and behavior agree
- [x] 12.3 Confirm the underlying shared-credential read client is retained because enumerated temporary consumers still depend on it, and that the user read path remains disconnected from it — verification: a test asserts the client is still present and still unreferenced by the user read path
- [x] 12.4 Confirm the version-lookup utility and the legacy write path still resolve their credential through the retained client, and that no new credential consumer was introduced — verification: a test asserts both consumers still function and the credential consumer set is unchanged apart from the read path removal
- [x] 12.5 Sequence removal as separate follow-on work, gated on the version lookup obtaining a credential-free in-process source and the write path obtaining its own identity story — verification: the follow-on precondition is written down and no removal is performed in this change

## 13. Documentation reconciliation

- [x] 13.1 Update the architecture document to record that ERPNext business-read authorization is now enforced in the Frappe request process, with the evidence state and the residual gaps, without implying production readiness or a resolved multi-site position — verification: the entry states evidence and limitations, not capability claims
- [x] 13.2 Update the roadmap and progress state to record this change's closure status while keeping prior milestones closed, and to state explicitly that this change does not reopen the production-readiness decision — verification: prior milestone statuses are unchanged
- [x] 13.3 Update the blockers record so the intra-site authorization item reflects delivered business-read authorization while retrieval-ACL parity and multi-site tenancy remain open — verification: the item reflects the delivered scope and the still-open items
- [x] 13.4 Record the U5 architectural decision, the rejected alternatives and their reasons, and the audit vocabulary migration in the decisions ledger with approval provenance — verification: the ledger entry names the decision, alternatives, reasons and provenance
- [x] 13.5 Update the security policy to distinguish this delivered boundary from the still-unenforced targets, without certifying current enforcement beyond what is evidenced — verification: policy text does not claim enforcement that lacks evidence

## 14. Final validation and evidence review

- [x] 14.1 Run strict OpenSpec validation for this change and for the spec set, and confirm it passes — verification: strict validation passes
- [x] 14.2 Run the repository whitespace and diff check, and confirm no unintended changes — verification: the check is clean
- [x] 14.3 Review the complete diff to confirm the change is confined to the Frappe application, the inference contract boundary, the audit vocabulary, the read contract, tests, and documentation — verification: no unrelated area is modified
- [x] 14.4 Confirm no forbidden repository was accessed and no dependency, configuration, provider, vector store, mode-engine or write-path change was introduced — verification: explicit confirmation recorded
- [x] 14.5 Assemble the evidence record covering test types, dates, environment, artifacts, results, limitations and the next gate, and confirm no production, release, write or cloud-consent approval is claimed or implied — verification: evidence record complete and free of over-claiming
- [x] 14.6 Archive the change only after every task above is complete and the evidence record is accepted — verification: archive occurs last, and only on explicit instruction
