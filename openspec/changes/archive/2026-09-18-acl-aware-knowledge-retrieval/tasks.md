# Tasks: acl-aware-knowledge-retrieval

Planning only — no implementation started. Verification for each task is stated inline. Implementation and evaluation work are separated (sections 2–5 build, section 6 proves).

## 1. Contracts and fixtures first

- [x] 1.1 Freeze the ACL metadata schema (`site`, visibility tier, `allowed_roles`) and the normative envelope authorization-scope fields (`site`, `tiers`, `roles`, `derived_by` marker, per-request re-derivation), and verify both are recorded identically in design and specs with no drift.
- [x] 1.2 Build cross-site, intra-site-unauthorized, and authorized fixture corpora (synthetic, no real private data) and verify each fixture's expected visibility by direct metadata inspection before any code uses it.
- [x] 1.3 Define the index-generation record format and fingerprint fields, and verify a sample generation record validates against the schema.

## 2. Retrieval enforcement (implementation)

- [x] 2.1 Stamp ACL metadata at ingestion for all pipelines (public/company/code/resolutions) with corpus defaults, and verify every emitted chunk carries valid metadata or is rejected at build time.
- [x] 2.2 Derive the authorization scope in the Frappe gateway live per request from authenticated user/site/roles (no cross-request grant caching), carry the frozen fields in the envelope, and verify forged scope fields and missing/invalid markers are refused and conversation ownership never substitutes for it.
- [x] 2.3 Apply scope predicates inside both vector-pool queries and BM25 candidate selection before fusion, and verify denied chunks never enter candidate lists (unit probes with fixtures).
- [x] 2.4 Carry source/version/model/generation/site/ACL provenance into passages and citations, and verify each cited result traces to its provenance without leaking denied sources.
- [x] 2.5 Keep employee retrieval public-tier (no access expansion) and verify persona restrictions behave exactly as before for both personas.

## 3. Index lifecycle (implementation)

- [x] 3.1 Implement staged generation builds (vectors + lexical from one snapshot) with per-corpus count verification, and verify a staged build never affects live retrieval.
- [x] 3.2 Implement atomic pointer-swap activation with prior-generation retention, and verify rollback restores exact prior state (counts + probes).
- [x] 3.3 Implement update/delete via new generations only, and verify deleted content is unreachable on vector, lexical, cache, and citation paths after publication.
- [x] 3.4 Enforce the embedding fingerprint gate on load and at build, and verify model/revision/dimension/metric mismatches refuse loudly and prohibit mixed vectors.
- [x] 3.5 Replace the destructive public rebuild with corpus-scoped rebuilds, and verify unrelated corpora are bit-for-bit preserved with counts checked before activation.

## 4. Egress enforcement (implementation)

- [x] 4.1 Route every provider call (generation, retries, NLU, condensation, embeddings, evaluation judges) through one policy boundary, and verify a lint/test guard fails any direct provider call added elsewhere.
- [x] 4.2 Implement the grant table (data class × provider × purpose, default deny, mixed-request strictness, revocation honored without restart) with permanent secret exclusion, and verify ungranted transmissions are refused with safe codes.
- [x] 4.3 Prohibit silent provider switching/fallback, and verify an unavailable granted provider fails safely instead of rerouting.

## 5. Topology-agnosticism guard (implementation)

- [x] 5.1 Verify the full implementation references only logical scopes (site, visibility, roles, generations) with no per-site/shared deployment selection, and record the compatibility constraints either topology must satisfy.

## 6. Evaluation and verification (no new behavior)

- [x] 6.1 Run cross-site and intra-site negative suites proving denied content absent from candidates, context, caches, citations, model input, and diagnostics, and verify post-retrieval filtering is not what passes them.
- [x] 6.2 Run revocation/invalidation tests (role narrowing effective on next request without re-index; reclassification republished with old generation retired and refused rollback; republication measured against the documented operational bound; emergency scope-narrowing immediate) and verify no stale cache, snapshot, or context serves revoked content.
- [x] 6.3 Run rebuild tests (scoped rebuild preservation, deletion handling, counts, rollback) and lexical/vector agreement checks, and verify all pass.
- [x] 6.4 Run embedding-compatibility tests (changed model/rev/dims/metric → loud refusal + controlled rebuild) and held-out retrieval/grounding checks after the change, and verify confidence behavior is recalibrated or explicitly unchanged with evidence.
- [x] 6.5 Run the synthetic-marker egress harness across every provider path (deny/grant/revoke per path, secret exclusion with ordinary approval) and per-provider conformance checks, and verify no marker reaches a real provider and no paid call is authorized by testing.
- [x] 6.6 Re-run the G3 boundary checks (auth, chat-only, owned conversations, health, no-direct-DI) against the new build and verify no regression.

## 7. Docs and handoff

- [x] 7.1 Document the cutover (controlled re-index to generation 1, rollback path, marker-harness use, no production grants changed) in README/DEVELOPMENT scope and verify the archived G3 change is left untouched.
- [x] 7.2 Record dated evidence, valid-row counts, and remaining gates in progress files, explicitly listing what was deferred (U1 topology, mediated-vs-direct placement, full permission parity, new engines).
