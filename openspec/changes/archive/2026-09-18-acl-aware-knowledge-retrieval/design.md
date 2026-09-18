# Design: acl-aware-knowledge-retrieval

## Context

See `proposal.md` (Why). Current state: one Chroma collection with
`source_type` provenance tags (not ACLs); two metadata-filtered vector pools
plus a global BM25 snapshot fused by RRF; destructive public rebuilds;
stale lexical state; LiteLLM env-selected generation with no consent gate;
local embeddings; Frappe-derived persona via roles but no per-user corpus
decisions. G3 trust rules stand: Frappe authoritative for identity/site/
ownership; inference validates consistency only; chat-only; no silent
fallbacks.

## Goals / Non-Goals

Goals: pre-retrieval site+ACL enforcement on every retrieval path;
versioned, safely published index generations; deny-by-default egress on
every provider path with a marker-proven harness. Non-goals: selecting
physical tenancy (U1), mediated-vs-direct store placement beyond the
lifecycle contract, full ERPNext permission parity, new search engines,
MCP/Workbench/SQL tools, production provider grants, production readiness.

## Decisions

- **D0 — Minimal ACL metadata: site + visibility + allowed_roles (proposed).**
  Every chunk carries `site` (required string), `visibility` in
  {`public`, `site`, `restricted`}, and `allowed_roles` (required iff
  restricted; ignored otherwise). Corpus defaults: `public_doc`→public;
  company/code/resolutions→site, restrictable per ingestion config.
  This is a coarse-grained knowledge-access layer, NOT ERPNext permission
  parity: it guarantees pre-retrieval enforcement of intentionally stamped
  tiers and fail-closed exclusion of anything unstamped, and guarantees
  nothing about DocType/document/field/permlevel authorization. Retrieval
  success must never be presented as ERPNext permission proof. Rationale:
  smallest schema covering all current corpora and both G4 fixture
  classes; equality/set-membership filters map directly onto
  Chroma `where` clauses and BM25 pre-filtering. Alternative (mirroring
  Frappe DocType permlevels per chunk) rejected: unbounded complexity for
  no additional G4 coverage. Full ERPNext permission parity explicitly
  deferred; the contract names exactly this model.
- **D1 — Enforcement at candidate selection, both pools plus lexical
  (proposed).** Frappe derives the frozen scope `{site, tiers, roles,
  derived_by}` per request into the envelope authz scope; inference
  compiles it to metadata predicates applied inside each vector-pool
  query AND to BM25 candidate selection before fusion/RRF. Browser scope
  is impossible (refused fields); FastAPI validates structure, provenance
  marker, and consistency only and grants nothing. Post-fusion answer
  filtering is forbidden as a boundary. Rationale: G4 requires denied
  content absent from candidates; RRF over pre-filtered pools preserves
  ranking semantics. Alternative (post-retrieval filtering) rejected by
  spec.
- **D2 — Revocation via generations, caches keyed by (generation, scope)
   (proposed).** The active generation's stamped metadata IS the
   authorization state. Frappe-side changes (roles) take effect on the next
   request: scope is re-derived live per request with no cross-request grant
   caching (NexMate adds no grant cache — every `ask()` calls
   `frappe.get_roles(user)` live; normal User-save invalidates Frappe's
   per-user roles cache, but current upstream `Role` DocType deletion does
   not — a deleted Role can leave a stale `frappe.get_roles` result until
   the cache is invalidated; known upstream Frappe limitation, not a
   NexMate-side defect and not fixed in M4 — see spec caveat). Content-side changes (reclassification) require re-stamping under
  a new generation plus retirement of the superseded generation, which must
  never serve affected scope afterwards nor be reactivated while the
  revocation stands; its caches and lexical snapshot are dropped with it.
  Already-delivered answers are historical. Revocation is complete no later
  than republication plus retirement, against an operational republication
  bound set at implementation and enforced by tests; Frappe-side scope
  narrowing is the immediate emergency lever without re-indexing. No TTL
  expiry anywhere on the authorization path. Alternative (TTL expiry)
  rejected: bounded staleness still leaks denied content within the window.
- **D3 — Generations with atomic pointer swap (proposed).** Build staged
  (vectors + lexical from the same snapshot) → verify (counts per corpus,
  fingerprint, probe queries) → swap active pointer → retain prior for
  rollback. Deletions/updates only land via new generations. Rationale:
  fixes destructive rebuilds and lexical drift by construction.
  Alternative (in-place upserts on live index) rejected: cannot give
  atomicity or rollback.
- **D4 — Embedding fingerprint gate (proposed).** Generation records
  model/revision/dimensions/metric; the loader refuses mismatches and
  demands a controlled rebuild. Mixed-dimension vectors are rejected at
  build validation. Rationale: silent incompatibility corrupts ranking
  without errors.
- **D5 — Single egress choke point (proposed).** All provider calls
  (generation, corrective retries, NLU, condensation, embeddings,
  evaluation judges) route through one policy check: grant table keyed by
  (data class, provider, purpose), default deny, synthetic-marker tests
  per path, permanent secret scrub, no silent provider switching.
  Rationale: today's scattered call sites cannot be audited; one boundary
  makes deny-by-default provable. Production grants themselves remain user
  approvals, not part of this change. Development/preview grant rows
  (explicit local-only) are defined at implementation so the dual-opt-in
  preview keeps working — deny-by-default must not silently break the
  standalone workflow that endpoint-access-control explicitly permits.
- **D6 — Frappe derives scope live per request (proposed).** The
   gateway extends the existing role lookup: site from `frappe.local.site`,
   roles from the authenticated user (`frappe.get_roles(user)` on every
   `ask()`; see D2/spec caveat for upstream `Role` DocType deletion cache
   timing — NexMate itself caches no grants), frozen shape
   `{site, tiers, roles, derived_by}` with a fixed Frappe-derivation marker
   — no cross-request caching of grants, so normal User-save role changes
   take effect on the next request (Role deletion inherits the upstream
   cache caveat).
  Persona restrictions are unchanged by this design — employee retrieval
  stays public-tier; the ACL tiers additionally constrain
  already-permitted corpora (site/restricted). Expanding employee access
  needs separate policy approval, not part of M4. Conversation ownership
  stays a separate, independent check. Rationale: reuses the proven G3
  identity pattern; no access expansion hides inside a security change.
- **D7 — Topology-agnostic contract (proposed).** All of the above is
  stated against logical scopes, never physical placement; the same
  fixtures pass whether the index is per-site or shared-with-filters.
  Rationale: U1 stays undecided per explicit direction.

## Risks / Trade-offs

- [Risk] Per-request scope derivation adds Frappe overhead → Mitigation: lookup is a single `frappe.get_roles(user)` read on an already-authenticated session; no NexMate-side grant caching means no NexMate revocation window (upstream `Role` DocType deletion cache caveat still applies — see D2/spec).
- [Risk] Generation retention doubles storage during transitions → Mitigation: retain exactly one prior generation; older ones purged after verification.
- [Risk] Strict fingerprinting blocks startup after any embedding upgrade → Mitigation: fail-loud with the exact mismatch and the controlled-rebuild runbook; never auto-migrate.
- [Risk] Single egress choke point becomes a bypass temptation (direct litellm imports) → Mitigation: lint/test guard asserting all provider calls route through it; review checklist item.

## Migration Plan

1. Land metadata schema + scope derivation behind a permissive-but-logging mode (violations logged, not yet enforced) to measure blast radius on existing corpora.
2. Controlled re-index stamping metadata as generation 1 (staged); verify counts per corpus; swap active; retain legacy generation for rollback.
3. Flip enforcement on (pre-retrieval filters active); run cross-site/intra-site fixture suites and marker harness.
4. Egress choke point with deny-by-default; per-path marker evidence; no production grant changes.
5. Rollback at any step: reactivate the prior generation pointer; Frappe scope derivation is additive to the envelope.

## Open Questions

None that change specs, approach, or tasks. Exact budget numbers, fingerprint hash format, and marker vocabularies are set during implementation within the bounds above.
