# CHANGELOG.md

Format: [Keep a Changelog](https://keepachangelog.com/). Update this as
part of completing meaningful units of work — not just at phase end.

## [Unreleased]

### Added
- Phase 5 Read-only ERPNext API tool: `tools/erpnext.py` (GET-only by
  construction, percent-encoded path segments, capped payloads, loud
  timeouts) + `POST /tools/erpnext/schema|document|list` endpoints;
  credentials live only in `.env`. Verified against the live instance at
  localhost:8081 (schema 87-field Customer, filtered Role list, full User
  document; clean 403/404 passthrough).
- Phase 4 Project Memory: optional `session_id` on `/ask` (server-side
  threads in `data/sessions/`, budgeted at read time), follow-up
  condensation against conversation history before retrieval, `POST
  /tools/session/reset`. Applied edits auto-index as `resolved_issue`
  chunks (`tools/memory.py`, motive+message+diff) with
  `--backfill-commit`; resolutions ride the boosted company pool and are
  labeled "past fix" in prompts.
- Phase 3 Company Knowledge: `ingestion/ingest_project.py` indexes this
  repo into the same Chroma collection (`our_code` via stdlib-ast boundary
  chunking, `company_doc` via heading splits; idempotent re-sync). Index:
  7,410 public + 321 project chunks.
- Two-pool vector retrieval (public vs project) fused with RRF under
  `FUSION_COMPANY_BOOST`; generator passages labeled
  project-code/project-docs/framework-docs with an authority rule.
- Rare-term rescue guard in the confidence gate for self-referential corpus.

### Changed
- Phase 2 code tools, Tier 1 (complete): `tools/pathsafe.py`
  (project-root scoping — resolve-then-verify, symlink-aware, loud
  rejections), `tools/files.py` (`read_project_file`, size-capped, strict
  UTF-8), `tools/search.py` (gitignore-aware grep-equivalent with honest
  truncation counters), `tools/explain.py` (locate code behind an error,
  explain grounded in excerpts via the single litellm call site).
  Service endpoints: `POST /tools/read_file|search|explain`. Unittest
  suite under `tests/` (30 cases) covering traversal/absolute/symlink
  escapes, gitignore exclusion, decoy-file ranking, excerpt spans.
- Phase 2 Tier 2 (edit flow): `tools/edit.py` +
  `POST /tools/propose_edit|apply_edit` — clean-tree gate with
  target-aware refusals, tracked-not-ignored checks, exactly-once match,
  unified-diff proposals (TTL'd, one-shot), explicit `confirmed:true`
  required at apply, one atomic single-file commit per edit. 14 edit-flow
  tests against a real throwaway git repo; proven live with three real
  isolated doc-fix commits (`8a520b3`, `9552c00`, `c986988`).
- `PROJECT_ROOT`, `MAX_READ_FILE_BYTES`, and proposal-TTL configuration.

### Changed
- Doc-set audit: AGENTS.md read-order numbering + phase-agnostic phase
  references + ADR location; EVALUATION.md Phase-1 DoD ticked to verified
  reality; UI_SPEC.md dead reference fixed; SECURITY.md current-phase
  section refreshed for Phase 2; CHANGELOG.md maintained from now on;
  opencode.json instructions include CHANGELOG.md.

### Fixed
- README bench-install path typo (`erpnot_ai_copilot`).
- Module-docstring chunks starving real symbol chunks in per-document
  dedupe (P1 declined despite correct sources); rare-term gate now blocks
  coverage-rescue for df<=4 tokens, keeping documented negative probes
  (`frappe.auto_sync_with_jupiter`) in honest-decline territory after the
  journals entered the corpus.

## [2026-08-24] — Phase 1

### Added
- Phase 1 RAG pipeline: docs.frappe.io crawler (canonical-URL dedupe,
  scope filter), heading-based chunking + bge-small embeddings into a
  persistent cosine-space Chroma store.
- Hybrid retrieval: in-house Okapi BM25 (`rag/keyword_index.py`) fused
  with vector retrieval via Reciprocal Rank Fusion; per-document dedupe
  with a near-tie second-chunk rule for multi-section pages.
- FastAPI service: `POST /ask` (answer + sources + confidence contract),
  `GET /health`, localhost-only bind, CORS middleware.
- Grounded-only generator via litellm: provider-agnostic through `.env`,
  citation-marker escalation loop, deterministic backticked-identifier
  grounding net against retrieved context.
- Confidence gates calibrated on measured distributions (high / low /
  no_match) including a corpus-absent-term veto for fabricated-feature
  questions.
- Evaluation tooling: RAGAS two-phase harness (main venv generates,
  `.venv-eval` Python 3.12 scores), reference answers, retrieval probe
  (`evaluation/retrieval_probe.py`).
- Minimal Frappe sidebar app (`frappe_app/`): floating AI button, chat
  panel, sources list, confidence badges, distinct no_match styling.

### Changed
- Retrieval switched from pure-vector top-k to hybrid BM25+vector fusion;
  confidence gating moved from single-similarity bands to a two-signal
  policy (cosine corroborated by keyword coverage).

### Fixed
- Fabrication on weak retrieval ("override a controller"): now answered
  from the real corpus mechanism or declined honestly; negatives return
  the exact no_match shape (empty sources, no LLM call).
- Naive `/erpnext/v` substring exclusion that would skip legitimate pages
  like `valuation-*`; replaced by segment-aware
  `config.is_excluded_doc_path()` shared by crawler and loader.
- Stale `/erpnext/v13/` page purged from the index (7,410 chunks).

## [2026-08-23] — Phase 1 baseline

### Added
- Project scaffolding and documentation set; RAGAS baseline recorded
  (faithfulness 0.992 / relevancy 0.941 / context precision 0.562).
