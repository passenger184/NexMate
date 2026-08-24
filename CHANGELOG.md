# CHANGELOG.md

Format: [Keep a Changelog](https://keepachangelog.com/). Update this as
part of completing meaningful units of work — not just at phase end.

## [Unreleased]

### Added
- Phase 2 code tools, Tier 1 (complete): `tools/pathsafe.py`
  (project-root scoping — resolve-then-verify, symlink-aware, loud
  rejections), `tools/files.py` (`read_project_file`, size-capped, strict
  UTF-8), `tools/search.py` (gitignore-aware grep-equivalent with honest
  truncation counters), `tools/explain.py` (locate code behind an error,
  explain grounded in excerpts via the single litellm call site).
  Service endpoints: `POST /tools/read_file|search|explain`. Unittest
  suite under `tests/` (30 cases) covering traversal/absolute/symlink
  escapes, gitignore exclusion, decoy-file ranking, excerpt spans.
- `PROJECT_ROOT` and `MAX_READ_FILE_BYTES` configuration.

### Changed
- Doc-set audit: AGENTS.md read-order numbering + phase-agnostic phase
  references + ADR location; EVALUATION.md Phase-1 DoD ticked to verified
  reality; UI_SPEC.md dead reference fixed; SECURITY.md current-phase
  section refreshed for Phase 2; CHANGELOG.md maintained from now on;
  opencode.json instructions include CHANGELOG.md.

### Fixed
- README bench-install path typo (`erpnot_ai_copilot`).

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
