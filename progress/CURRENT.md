# progress/CURRENT.md — Current State

**Last updated:** 2026-08-24 (session 4, continued: hybrid keyword+vector retrieval implemented and verified — all 2026-08-24 regressions resolved; full sweep 15/15 answered + cited, 3/3 negatives exact no_match)
**Current phase:** Phase 1 — Pure RAG, Developer mode (see `docs/PHASE_1_SPEC.md`)
**Current task:** Phase 1 build re-complete after the hybrid-retrieval fix. Remaining before calling it done in the wild: install/verify the Frappe app on a real bench (impossible from this box), optionally re-score RAGAS post-change.

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

Install `frappe_app/` on the real bench and confirm the sidebar works
against the live service (README "Install the Desk sidebar"). Optionally
re-run the RAGAS scoring phase against fresh samples to quantify the
hybrid-retrieval gain on context_precision.
