## Why

Retrieval today is single-project with `source_type` tags as provenance labels — explicitly not ACLs. Any caller reaching inference can retrieve company documents, code, and resolutions; public rebuilds destroy unrelated corpora; the lexical snapshot drifts; and provider calls have no enforced data-consent boundary. M4 must turn this into a production-oriented contract where denied content never reaches candidates, context, or models.

## What Changes

- Frappe derives a per-request authorization scope (site + permitted visibility/roles) from the authenticated user and passes it in the gateway envelope; inference enforces it as pre-retrieval metadata filters on vector and lexical candidates — never as post-answer filtering.
- Minimal ACL metadata (`site`, visibility tier, allowed roles) attached at ingestion to every chunk; cross-site and intra-site negatives proven by fixtures. This is a coarse-grained knowledge-access layer, not ERPNext permission parity: retrieval success is never permission proof, and unstamped content is fail-closed.
- Index generations with source/version/model/ACL provenance, atomic staging→active publication, rollback, deletion/update semantics, and lexical/vector coupling by construction; embedding-compat fingerprint enforced on load with controlled rebuilds only.
- Deny-by-default egress enforcement at a single provider-call boundary covering generation, retries, NLU, condensation, embeddings, and evaluation/judge paths, with synthetic-marker tests and permanent secret exclusion.
- **BREAKING (bounded):** retrieval inputs now require authorization scope; unscopable legacy direct calls lose company-corpus access (public-only) rather than failing silently.

## Capabilities

### New Capabilities

- `acl-aware-retrieval`: site/ACL pre-retrieval enforcement, minimal metadata, fixtures, provenance in results.
- `index-lifecycle`: generations, publication/activation, update/delete, lexical coupling, rollback, corpora preservation, embedding compatibility.
- `provider-egress-policy`: deny-by-default enforcement, data classes, marker harness, per-path coverage, no silent switching, secret exclusion.

### Modified Capabilities

- `frappe-api-gateway`: envelope gains the Frappe-derived authorization scope, validated like other envelope fields; conversation ownership remains distinct from knowledge authorization.

## Impact

- Inference: retriever (vector + BM25 pools), ingestion pipelines (metadata stamping), index lifecycle manager (new), provider-call boundary (new), envelope validation, fixture suites.
- Frappe app: authorization-scope derivation from authenticated user/roles, envelope construction; no new DocTypes required.
- Operators: one controlled re-index to stamp metadata and establish generation 1; rollback path via prior generations.
- Out of scope: physical index tenancy selection (U1, topology-agnostic by design), mediated-vs-direct store placement beyond the lifecycle contract, full ERPNext permission-model parity, MCP, Workbench, SQL tools, multi-workspace, production-write approval, production provider/data-sharing grants, production-readiness claims. Qdrant/pgvector/reranking stay unselected options.
