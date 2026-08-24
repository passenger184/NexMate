# progress/CURRENT.md — Current State

**Last updated:** 2026-08-24 (session 7: Phase 3 — Company Knowledge — built and verified; project corpus live in the index, DoD met)
**Current phase:** Phase 3 — Company Knowledge (`docs/PHASE_3_SPEC.md`) — functionally complete, awaiting user acceptance
**Current task:** None in flight. Proposed next: Phase 4 — Project Memory (`docs/PHASE_4_SPEC.md`), which builds directly on Phase 2's edit commits.

## Phase 2 closure note (2026-08-24)

Phase 2 accepted via user instruction to proceed. All six DoD items in
`docs/PHASE_2_SPEC.md` verified (see the Phase 2 progress section below);
the only bench-dependent leftover is the sidebar's diff/approve UI
(`docs/UI_SPEC.md`), same conscious-deferral pattern as Phase 1.

## Phase 3 — Company Knowledge: what changed

- **`ingestion/ingest_project.py`** — indexes this repo into the SAME
  Chroma collection: .py files as `our_code` (stdlib-ast function/class-
  boundary chunks; oversized classes split at methods; module preamble
  merged into the first symbol chunk after a standalone-docstring chunk
  lost per-document dedupe to real code), repo markdown as `company_doc`
  (MarkdownNodeParser headings). Idempotent: deletes stale project chunks,
  never touches public docs. Live index: **7,410 public + 321 project =
  7,731 chunks**.
- **`rag/retriever.py`** — vector retrieval now runs as TWO metadata-
  filtered pools (public_doc vs our_code/company_doc) fused with RRF under
  `FUSION_COMPANY_BOOST=1.25`, so specific company answers beat generic
  framework pages without letting either corpus dominate by size.
- **`rag/generator.py`** — passages labeled "project code"/"project docs"/
  "framework docs"; prompt states project material is authoritative for
  questions about this repository's own behavior.
- **Gate hardening for self-referential corpus**: indexing our own journals
  put past negative probes (`auto_sync_with_jupiter` df=4) into the corpus,
  defeating the df=0 veto. New rule: terms with df ≤
  `CONFIDENCE_RARE_TERM_DF_MAX` cannot be RESCUED into high — such
  questions decline deterministically instead (N2 → low + sources, honest).

## Phase 3 verification (live POST /ask, `data/phase3_sweep.json`)

| Probe | Verdict |
|---|---|
| P1 project-root scoping location | PASS — walks PROJECT_ROOT config + `tools.pathsafe` resolve/verify + `PathOutsideRootError`, all verbatim (initially declined due to docstring-chunk dedupe bug; fixed + re-verified) |
| P2 dirty-tree refusal | PASS — names `_refuse_if_dirty`, quotes the actual refusal message |
| P3 hybrid RRF fusion | PASS — real constants (`RRF_K`, `BM25_K1/B`, fusion weights) with correct module attributions |
| P4 boot.py ↔ sidebar | PASS — `extend_bootinfo` → `boot_session` → `copilot_api_base` → `frappe.boot.copilot_settings` |
| P5 base64 scrub rationale | PASS — `BASE64_DATA_URI_RE`, `[image]` placeholder, gibberish-chunk history grounded |
| P6 chunking pipeline | PASS — two-stage parser/resplit with exact config values from project code |
| D2 preference case | PASS — "convert Chroma distances to similarity" cites `rag/retriever.py:_vector_pool` exp(-distance) FIRST; generic framework doc ranked last |
| Negatives | N1/N3 no_match empty-sources; N2 low + sources (honest decline, no fabrication — see gate note above) |

## Phase 3 DoD status (`docs/PHASE_3_SPEC.md`)

- [x] Custom app source code ingested and retrievable
- [x] ≥5 project-specific questions answered correctly, company code vs
      public docs distinguished (P1–P6 above)
- [x] Dual-answerable question prefers/cites company code (D2)
- [x] `progress/CURRENT.md` + `DECISIONS.md` updated (ADR [2026-08-24]
      Phase 3: corpus mixing + code chunking)

## Phase 1 closure note (2026-08-24, user decision)

Phase 1 is accepted as functionally complete. Two verification items were
consciously deferred, NOT silently skipped:
- **Real-bench sidebar install** — impossible on this box; app code complete
  and untested against a live bench.
- **RAGAS re-score post-hybrid-retrieval** — generation phase DID complete
  against the new pipeline (`data/ragas_samples_2026-08-24T11:32:30Z.json`,
  15/15 answered at high confidence); the scoring phase was aborted mid-run
  by user order. A future session can score that file directly with
  `.venv-eval/bin/python -m evaluation.ragas_eval score <file>` (~40 min)
  without regenerating. The 2026-08-23 baseline below remains the recorded
  baseline.

## RAGAS baseline (EVALUATION.md requirement)

Scored 2026-08-23 (pre-hybrid-retrieval), judge = same local
qwen2.5-coder:7b that generates (self-judging approximation), embeddings =
bge-small. Samples: `data/ragas_samples_2026-08-23T09:04:28Z.json`; results:
`data/ragas_baseline_2026-08-23T09:04:28Z_094756.json`.

| Metric | Score | Notes |
|---|---|---|
| Faithfulness | **0.992** | 12/15 rows valid; 3 NaN = judge JSON-parse failures (all on weak-retrieval rows), not low scores. Answers are supported by context. |
| Answer relevancy | **0.941** | 15/15 valid. |
| Context precision | **0.562** | Weak on the OLD retriever (override-controller 0.12). Hybrid retrieval should raise this — NOT yet re-scored; treat as stale pending a rerun. |

Harness lives in `evaluation/` (two-phase: generate in main venv, score in
`.venv-eval` Python 3.12 — ragas 0.2.x is incompatible with this machine's
Python 3.14 asyncio). Setup commands in README "Evaluate".

## Hybrid retrieval (2026-08-24) — what changed and why

Root fix for the verification-run regressions (see DECISIONS.md
[2026-08-24]):

- **`rag/keyword_index.py`** — in-house Okapi BM25 over the same Chroma
  collection (no new dependency); lazy rebuild per process so it can never
  drift from the vector store. Tokenizer folds plural/-ing/-ed/final-e
  suffixes identically on queries and corpus.
- **`rag/retriever.py`** — Reciprocal Rank Fusion of both candidate lists
  (keyword weight 1.5), then best-chunk-per-document dedupe with one
  exception: a page's second chunk joins top-k when its BM25 is >=0.9 of the
  page's best (huge multi-section pages like hooks.md were losing the exact
  answering section to lexically-tied siblings).
- **Confidence gates recalibrated on measured distributions**
  (`config.py`, probed via `evaluation/retrieval_probe.py`):
  - `high`: cosine >=0.80, or cosine >=0.74 rescued by IDF-weighted query-term
    coverage >=0.45 in the top chunks.
  - `no_match`: coverage veto (<=0.05), OR any query term absent from the
    entire corpus (df=0 — the fabrication-feature signal) unless cosine alone
    clears the high bar, OR plain cosine <0.72.
  - `low`: everything between → deterministic refusal, sources shown.
- **Generator grounding net** (`rag/generator.py`): every backticked
  identifier must appear verbatim in retrieved context; otherwise ONE
  corrective escalation (steered toward replacing with the passages' actual
  identifiers). This converted Q6's `after_save` leak into a correct
  `on_update` answer and Q3's fabricated doctype.json mechanism into the
  corpus's real `extend_doctype_class`.
- **Corpus hygiene**: stale `/erpnext/v13/...learn.md` purged from the index;
  exclusion now goes through shared `config.is_excluded_doc_path()`
  (segment-aware) in BOTH crawler and loader — the old substring pattern had
  a latent bug that would exclude `/erpnext/v...aluation`-style slugs.
  Index: **7,410 chunks**.

## Verification state (2026-08-24, post-fix)

Full live sweep through POST /ask (`data/sweep_2026-08-24_hybrid_v2.json`):

- **Positives 15/15 confidence="high"**, every answer has sources and inline
  `[n]` markers. Grounding spot-verified against corpus text for every
  previously-defective question:
  - Q3 override controller → answers `extend_doctype_class` from hooks.md
    (verbatim example; corpus notes it is preferred over
    `override_doctype_class` in v16+) — fabrication gone.
  - Q5 custom app / Q6 hook after save / Q15 debug submit-validation → all
    answered again (coverage regression resolved), each grounded.
  - Q7 migration → cites exporting-customizations + bench migrate +
    before_migrate/after_migrate hooks; earlier wrong-[6] citation and
    `/erpnext/v13/` source leak both gone.
  - Q12 scheduled jobs → every bench command (`enable-scheduler`, `doctor`,
    `show-pending-jobs`, `purge-jobs`, `schedule`, `worker`) verified
    verbatim in bench-commands-cheatsheet / frappe-commands / bench-procfile
    pages now IN context — training-knowledge leak resolved.
- **Negatives 3/3 exact `no_match` shape**: refusal message, empty sources,
  ~0.2–1.5s, zero LLM calls (sourdough / auto_sync_with_jupiter / vague
  settings probe).
- Minor residual imperfections (documented honestly): Q15 includes mildly
  tangential journal-entry advice drawn from a cited troubleshooting page;
  Q2 has light editorializing ("securely and efficiently"); a document
  contributing two chunks can produce two near-identical-looking source
  entries (cosmetic).

## What's built and verified

- **Doc source resolved** — spec's git-repo option no longer exists; corpus
  crawled from docs.frappe.io `{url}.md` markdown alternates (BLOCKERS.md
  resolved; ADR in DECISIONS.md).
- **`ingestion/scrape_or_load_docs.py`** — sitemap crawl, alias→canonical
  dedupe, scope filter via `config.is_excluded_doc_path()` (shared with the
  loader as of 2026-08-24). Corpus: 1,000 distinct pages cached;
  ~174 permanently-dead sitemap entries recorded in `_failed_urls.txt`
  (re-crawl exits 1 — expected).
- **`ingestion/chunk_and_embed.py`** — MarkdownNodeParser → SentenceSplitter
  re-split; base64 data-URI scrub; stub chunks dropped; scalar metadata;
  cosine-space Chroma; loader re-applies the crawler's exclusion filter.
  Current v4-derived index: **7,410 chunks**.
- **`rag/retriever.py` + `rag/keyword_index.py`** — hybrid retrieval as
  described above; k=8, pool k×2 per signal.
- **`rag/generator.py`** — single litellm call site; grounded-only prompt
  with verbatim-identifier rule; citation-marker escalation loop;
  deterministic identifier-grounding net.
- **`service/main.py`** — POST /ask contract verified live end-to-end after
  the hybrid change (answer + sources + confidence; no_match → honest
  refusal, empty sources, no LLM call); GET /health; localhost-only; CORS
  middleware (env `COPILOT_CORS_ORIGINS`, default `*`).
- **Evaluation tooling** — `evaluation/retrieval_probe.py` (fused-score
  diagnostics for gate calibration); RAGAS two-phase harness in
  `evaluation/` (baseline recorded; re-score pending).
- **`frappe_app/`** — minimal Frappe app (sidebar panel: floating AI button,
  chat area, escaped HTML, Sources list, confidence badges, distinct red
  styling for no_match). Built per current v15/v16 conventions but **NOT
  installable-tested here — no bench exists on this box**.
- **`README.md`** — clean-machine setup (CPU-torch-first install, .env,
  crawl+embed, uvicorn, bench install steps, eval two-venv flow).

## DoD status (EVALUATION.md checklist)

- [x] ERPNext + Frappe docs ingested, chunked, embedded into Chroma
- [x] All 15 developer questions answered with correct citations (2026-08-24
      final sweep; grounding spot-verified against corpus text)
- [x] All 3 negative cases return "no confident answer" — now in the exact
      no_match + empty-sources shape
- [x] RAGAS baseline scores recorded (pre-hybrid baseline stands; re-score
      recommended but not required by the checklist wording)
- [x] FastAPI service running with the documented contract
- [ ] Minimal Frappe sidebar page verified against a real bench — NOT
      verifiable on this machine (no bench); code complete per current
      conventions
- [x] README clean-machine setup
- [x] progress/CURRENT.md accurate

## What's known to not work / not started yet

- Frappe sidebar untested against a real bench (no ERPNext install here).
- RAGAS not re-scored after the hybrid change — expect context_precision to
  move; current table describes the pre-change baseline.
- Q15/Q2 minor content imperfections noted above (grounded, just not
  maximally focused).
- Versioned doc subtrees remain excluded for Phase 1 (DECISIONS.md); the
  purge means the live index finally matches that decision exactly.
- Not started (later phases): ERPNext live-API tool, orchestrator,
  employee mode.

## Next step

**Phase 2 is functionally complete — every DoD item in
`docs/PHASE_2_SPEC.md` verified (see Phase 2 progress below).**
Remaining, bench-dependent only: the Frappe sidebar's diff/approve UI
(`docs/UI_SPEC.md` "Diff / edit approval") can be written but not tested
without a real bench — same conscious-deferral pattern as the Phase 1
sidebar install.

Upon user acceptance: start **Phase 3 — Company Knowledge**
(`docs/PHASE_3_SPEC.md`): ingest this project's custom app source +
internal docs into the existing Chroma store under `our_code` /
`company_doc` source-type tags. Note SECURITY.md's cloud-provider rule:
before Phase 3 puts company material into retrieval prompts, re-confirm
the `GENERATION_PROVIDER` choice with the user.

## Phase 2 progress

- **Task 1 DONE (2026-08-24).** `PROJECT_ROOT` config (config.py +
  .env.example, defaults to repo root); `tools/pathsafe.py`
  `resolve_in_project()` — resolve-then-verify (symlinks collapsed before
  containment check; in-root symlinks allowed, escapes rejected with a
  message naming both paths); `tools/files.py` `read_project_file()` —
  regular-files only, 1MB cap (`MAX_READ_FILE_BYTES`), strict UTF-8;
  `POST /tools/read_file` on the service (400 outside-root/400 non-file or
  binary/404 missing/413 oversized). Verified: 15/15 stdlib-unittest cases
  (`python -m unittest discover -s tests`) + live curl checks — real file
  reads back, `../../../etc/passwd`, `/etc/passwd`, and a symlink-out
  escape all rejected loudly; no silent redirects anywhere.
- **Task 2 DONE (2026-08-24).** `tools/search.py` — grep-equivalent over
  `git ls-files --cached --others --exclude-standard` (gitignore-aware,
  includes fresh untracked files), regex with literal fallback,
  case-sensitive default, results capped (`MAX_SEARCH_RESULTS`) with honest
  truncation flag + skipped-binary/large counters, every file re-scoped
  through pathsafe before reading. `tools/explain.py` — derives search
  terms from a problem description (quoted phrases > identifier-style
  tokens > noise-filtered words), ranks files by specificity-weighted
  capped match counts (snake_case/CamelCase ×3 so chatty files full of
  generic words can't drown the real one), excerpts windows around hits,
  ONE grounded-only LLM call reusing `rag.generator._complete` (the single
  litellm site) + its verbatim-identifier grounding net, cites
  `path` lines a-b, declines honestly on zero hits without spending an LLM
  call. Endpoints `POST /tools/search`, `POST /tools/explain`.
  Verified: 30/30 unittest cases; live — search finds 18 hits across 65
  files for `resolve_in_project` with `.env` (gitignored) excluded;
  explain correctly locates `service/main.py:194-218` for a KeyError-
  parsing-the-read_file-response description and walks the actual call
  chain grounded in excerpt text (first iteration ranked ingestion scripts
  top — fixed by the specificity weighting before sign-off).
- **Task 3 DONE (2026-08-24).** `tools/edit.py` + `POST /tools/propose_edit`
  / `POST /tools/apply_edit`. Gate order: validate → resolve (root scoping)
  → target-aware clean-tree gate (an untracked TARGET gets the precise
  "not in version control" refusal; unrelated dirt gets commit-or-stash) →
  tracked-not-ignored distinction via ls-files/check-ignore → exactly-once
  find match (ambiguity refused with counts) → unified diff returned,
  NOTHING written. Apply: requires explicit `confirmed:true`, re-checks
  tracked/stale/clean at apply time, writes+stages+commits that ONE file
  (atomic, batching structurally impossible), returns the short hash;
  proposals are one-shot with a 15-min TTL. Verified: 44/44 unittest cases
  (14 edit-specific, against a real throwaway git repo); live end-to-end —
  **three real edits applied as three isolated single-file commits**
  (`8a520b3`, `9552c00`, `c986988`: README chunk-count fix, README hybrid-
  retrieval description fix, DEVELOPMENT unit-test command), plus live
  refusals for dirty-tree (409), ignored `.env` (400), missing explicit
  confirmation (400), and ambiguous match ×2 (400).

## Phase 2 DoD status (`docs/PHASE_2_SPEC.md`)

- [x] Tier 1 (read/search/explain) verified working against this project
- [x] Path-traversal attempt verified rejected, not silently redirected
      (`../../../etc/passwd`, `/etc/passwd`, symlink-out all HTTP 400)
- [x] Tier 2 refuses to edit when the git tree isn't clean (unit + live)
- [x] ≥3 real edits end-to-end (diff shown → confirmed → applied →
      committed), each isolated in its own commit
- [x] Edit targeting a git-ignored file refused with clear explanation
      (`.env` live-refused; cache-file case covered in tests)
- [x] `progress/CURRENT.md` updated (this document)
