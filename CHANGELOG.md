# CHANGELOG.md

Format: [Keep a Changelog](https://keepachangelog.com/). Update this as
part of completing meaningful units of work — not just at phase end.

Entries record historical changes, not a production-readiness certificate.
Test totals and live checks retain their original scope; see `progress/`
for evidence and `ARCHITECTURE.md` for the sole canonical current/target HLD.

## [Unreleased]

### Added
- NexMate conversational orchestration (historically called "NexPilot";
  recorded as committed in `a7676ec`, live NLU acceptance incomplete):
  Layer-1 exact fast-path for canonical greetings/acks/help (zero model
  calls) + Layer-2 NLU understanding (conversational/capability/troubleshoot/
  clarify/out_of_scope/task) on the orchestrated path; descriptive
  capability registry (`capabilities.py`) behind "what can you do?"
  (not dispatch or authorization; direct tools remain separate);
  targeted clarification for ambiguous input; polite out-of-scope
  boundary; troubleshoot reuses error-text→code path or asks for the
  traceback; thin follow-ups ("why?") retrieve anchored on the NLU
  topic; NLU failure degrades to heuristic-only routing or safe
  clarification (never blind RAG); NLU calls run on a short fail-fast
  budget (`NLU_TIMEOUT_SECONDS`, default 20s, no transport retry).
  Evaluation: 29-case routing dataset (`evaluation/routing_cases.json`)
  + mocked wiring harness; session 18 recorded 133 Python tests + 26
  stub-DOM node checks green. Full live NLU verification was blocked by
  provider reachability then; no current connectivity measurement or full
  live-matrix acceptance is implied. Troubleshoot is an NLU kind mapping
  to code/clarify, not an eighth response route.
- Historical sidebar restyle to docs/UI_VISUAL_SPEC.md (amber direction,
  superseded by docs/UI_VISUAL_SPEC_updated.md): ink-navy instrument-panel
  surfaces with hairline borders, amber single accent, teal reserved for
  trust and rust for caution, status-LED confidence signals, terminal
  diff with colored gutters, muted monospace citation paths, approve
  color-sweep, and prefers-reduced-motion support.
- Sidebar rebuilt to docs/UI_SPEC.md as a dependency-free vanilla-JS
  bundle: slide-out resizable panel, markdown+code rendering with copy
  buttons, citation pills, confidence callouts, sessions + start-fresh,
  developer/employee mode switch, route/version chips, typing & error &
  empty states, and inline diff/write APPROVAL CARDS (/edit /newdoc
  /editdoc) plus /read /search /explain. Standalone preview at GET
  /ui/preview.html enables standalone browser checks, not real Bench/Desk
  installation verification. Browser transcript restoration and streaming
  remain target work.
- Phase 8 Write-capable ERPNext Agent: `tools/erpnext_write.py` +
  `POST /tools/erpnext_write/propose|apply` — flag-gated
  (ERPNEXT_WRITE_ENABLED), Tier-2 confirm flow with exact previews,
  pre-flight schema validation, create/update only (no delete), and an
  append-only audit log. Verified live on staging (localhost:8081).
- Phase 7 Employee/User mode: `POST /orchestrate` accepts
  mode=developer|employee; employees get a plain-language desk-user
  persona over public docs only, the code agent and DocType-schema
  lookups are denied with actionable messages, live document/list
  lookups stay available; developer mode provably unchanged.
- Phase 6 Orchestrator: `POST /orchestrate` routes between RAG, the code
  agent, and the live ERPNext tool (deterministic hints -> LLM classifier
  -> rag default); live instance versions (Frappe 16.31.0 / ERPNext
  16.32.3) cached read-only and injected into prompts for version
  authority; ERPNext branch extracts strict-JSON requests and answers
  only from real payloads; scope-aware retrieval keeps generic how-tos on
  public docs while project questions keep the boosted company pool.
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
- Product renamed to NexMate ("Your ERPNext AI Companion") on the listed
  surfaces: sidebar header, greeting text, preview page title, README, and
  service title. Historical "NexPilot" labels and technical identifiers
  remain; this is not a guarantee that every runtime string was renamed.
  Blue styling below follows canonical `docs/UI_VISUAL_SPEC_updated.md`.
  `#2E6FF2` accent (user bubble, send arrow icon, focus rings), neutral
  toggle/header/dropdown, `[n] path` citation pills with monospace paths,
  quiet inline confidence row below the pills (callout banners removed),
  terminal diff with colored gutters, white-fill Approve + ghost Reject,
  muted "Proposed fix" card headers. Removed: orange Send button, blue
  dropdown fill, shadows, uppercase-tracked labels, middle-dot joins.
- Fixed `/newdoc` parsing its JSON from the wrong regex group (every
  /newdoc failed with "Payload is not valid JSON").
- Doc-set audit: AGENTS.md read-order numbering + phase-agnostic phase
  references + ADR location; EVALUATION.md Phase-1 DoD ticked to verified
  reality; UI_SPEC.md dead reference fixed; SECURITY.md current-phase
  section refreshed for Phase 2; CHANGELOG.md maintained from now on;
  opencode.json instructions include CHANGELOG.md.

### Fixed
- Live-testing round, five bugs: (1) nested markdown lists flattened into
  one numbered list with blank fillers — replaced regex substitution with
  an indent-aware block parser; (2) citations rendered as raw malformed
  markdown (`[[1]text](url)`) — prompt rule plus deterministic rewrite net
  enforce bare `[n]` markers, pills render from the structured sources
  array; (3) short-input validation note firing repeatedly — consecutive
  identical system notes now collapse; (4) greeting "hey" routed to the
  live ERPNext tool — deterministic smalltalk path answers greetings with
  no retrieval/tools/LLM, and document extraction requires a name;
  (5) session condensation carried the previous topic onto greetings and
  topic changes — condensation now gated on anaphoric references.
- Code-route fabrication: non-error project questions were force-fit into
  the error-explanation template (invented "Likely Cause"/"Recommendations"
  sections, quoted developer statements existing nowhere). The code path
  now classifies error-reports vs general questions
  (`looks_like_error`), uses a dedicated non-error prompt that forbids
  invented error sections and non-verbatim quotations, labels planning
  docs as intent-not-reality, and answers directory questions with a
  deterministic live listing from the git index.
- Sidebar error banner contradicted the server: every failure was wrapped
  in "Can't reach the assistant", even correct application refusals (404
  missing file, 400 outside-root, 409 dirty tree). HTTP responses now
  render only the server's message in an amber banner; the connectivity
  wording is reserved for actual transport failures.
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
