# progress/CURRENT.md — Current State

**Last updated:** 2026-08-23 (session 3: RAGAS baseline + Frappe sidebar + README — Phase-1 DoD complete)
**Current phase:** Phase 1 — Pure RAG, Developer mode (see `docs/PHASE_1_SPEC.md`)
**Current task:** Phase 1 build complete. Remaining before calling it done in the wild: install/verify the Frappe app on a real bench (impossible from this box), and optionally re-score RAGAS with a stronger judge model.

## RAGAS baseline (EVALUATION.md requirement)

Scored 2026-08-23, judge = same local qwen2.5-coder:7b that generates
(self-judging approximation), embeddings = bge-small. Samples:
`data/ragas_samples_2026-08-23T09:04:28Z.json`; results:
`data/ragas_baseline_2026-08-23T09:04:28Z_094756.json`.

| Metric | Score | Notes |
|---|---|---|
| Faithfulness | **0.992** | 12/15 rows valid; 3 NaN = judge JSON-parse failures (all on weak-retrieval rows), not low scores. Answers are supported by context. |
| Answer relevancy | **0.941** | 15/15 valid. |
| Context precision | **0.562** | Weak, matches known retrieval misses (override-controller 0.12). Caveat: some 0.0 rows (e.g. database-query, where probes show Database API retrieved top-1) look like judge noise — re-score with a stronger judge before drawing conclusions from this number alone. |

Harness lives in `evaluation/` (two-phase: generate in main venv, score in
`.venv-eval` Python 3.12 — ragas 0.2.x is incompatible with this machine's
Python 3.14 asyncio). Setup commands in README "Evaluate".

## What's built and verified

- **Doc source resolved** — spec's git-repo option no longer exists; corpus
  is crawled from docs.frappe.io via its official `{url}.md` markdown
  alternate. Logged in `BLOCKERS.md` (resolved) + `DECISIONS.md` ADR.
- **`ingestion/scrape_or_load_docs.py`** — sitemap crawl, alias→canonical
  resolution, out-of-scope refusal. Corpus: **1,000 distinct pages**
  (`data/raw_docs/`); ~174 permanently-dead sitemap entries recorded in
  `_failed_urls.txt` (re-crawl exits 1 — expected).
- **Canonical dedupe + base64 scrub (gotchas):** wiki serves `{alias}.md`
  for stale aliases → double-caching (1,606 files → 1,000 docs); ten pages
  embed screenshots as base64 data-URIs → ~19k gibberish chunks flooding
  top-k; both fixed in the loader.
- **`ingestion/chunk_and_embed.py`** — MarkdownNodeParser → SentenceSplitter
  re-split; stub chunks dropped; scalar metadata (clean tab-free titles
  since v4 index); cosine-space Chroma. v4 index: **7,424 chunks**.
- **`rag/retriever.py`** — k=8, best-chunk-per-document (pool k×2);
  12/15 eval questions retrieve clearly-relevant top-3.
- **`rag/generator.py`** — single litellm call site; grounded-only prompt
  (anti-echo, anti-keyword-overlap, partial-answer rule). Live-verified:
  qwen2.5-coder:7b synthesizes well; phi4-mini echoes/over-declines.
- **`service/main.py`** — POST /ask contract verified live end-to-end
  (answer + sources + confidence; no_match → honest refusal, empty
  sources, no LLM call); GET /health; localhost-only; CORS middleware
  (env `COPILOT_CORS_ORIGINS`, default `*` — fine for localhost dev).
- **Confidence gates (from measured distributions):** negatives
  0.623–0.719 → no_match below 0.72 (deterministic gate, no LLM call);
  high requires ≥0.80 so mediocre retrieval surfaces as "low", never as
  confident-wrong.
- **EVALUATION.md manual sweep:** 15/15 answered live, 13 clearly
  grounded+cited; 3/3 negatives decline. Known failure: "override a
  controller" fabricates at confidence="low" (retrieval miss is root
  cause; hybrid keyword search is the future fix).
- **`frappe_app/`** — minimal Frappe app (pyproject.toml flit skeleton,
  hooks.py `app_include_js`/`app_include_css`/`extend_bootinfo`, boot.py,
  `public/js/copilot.bundle.js` + css). Sidebar panel: floating AI button,
  chat area, escaped HTML, Sources list with doc links, confidence badges,
  distinct red styling for no_match. Built per current v15/v16 conventions
  (verified against frappe source/docs by research) but **NOT installable-
  tested here — no bench exists on this box**; first bench install is the
  verification step.
- **`README.md`** — clean-machine setup (CPU-torch-first install, .env,
  crawl+embed, uvicorn, bench install steps, eval two-venv flow).

## What's known to not work / not started yet

- Frappe sidebar untested against a real bench (no ERPNext install here).
- "Override a controller" fabrication at low confidence (documented above).
- RAGAS context_precision 0.562 partly judge-noise (see table); a
  stronger judge would sharpen it.
- Versioned doc subtrees excluded for Phase 1 (DECISIONS.md).
- Not started (later phases): ERPNext live-API tool, orchestrator,
  employee mode, hybrid keyword retrieval.

## Next step

Install `frappe_app/` on the real bench and confirm the sidebar works
against the live service (README "Install the Desk sidebar"). Optionally
re-score RAGAS with a stronger judge to firm up context_precision.
