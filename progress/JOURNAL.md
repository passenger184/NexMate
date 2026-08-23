# progress/JOURNAL.md — Dated Work Log

Append a short entry per work session. Newest at the bottom. Keep entries
factual and specific — what was done, what was tested, what assumption was
made and why (per `AGENTS.md`'s guidance on low-stakes ambiguity).

## [2026-08-23]

- Session 1 (scaffolding): spec docs, ADR log created.
- Session 2: researched doc sources + stack APIs before coding (researcher
  agent). Key findings: git-repo docs dead → crawl docs.frappe.io `{url}.md`
  markdown alternates; MarkdownNodeParser has no size cap → hybrid resplit;
  litellm reads OLLAMA_API_BASE natively, we map OLLAMA_BASE_URL explicitly
  in generator.py instead. Logged as ADRs in DECISIONS.md.
- Built `ingestion/scrape_or_load_docs.py`: sitemap crawl (1,836 matching
  URLs), `{url}.md` fetch with canonical-redirect fallback and out-of-scope
  guard. Two bugs found and fixed during verification: (1) fallback fetched
  canonical HTML because `.md` suffix missing; (2) first fetch after
  refactor dropped the `.md` suffix entirely. Final corpus: **1,606 pages**
  cached under `data/raw_docs/`; 174 permanent failures (dead sitemap
  entries + aliases now redirecting to other Frappe products) recorded in
  `_failed_urls.txt`. Full re-crawl exits 1 by design (fail loud) due to
  those permanent dead ends.
- Built `ingestion/chunk_and_embed.py`, verified on 15-page smoke test
  end-to-end into cosine-space Chroma.
- Installed pinned deps on Python 3.14.4; installed CPU-only torch from the
  PyTorch CPU index BEFORE requirements.txt to avoid ~4GB of CUDA wheels
  this box will never use (README must tell setup users the same two-step
  install).
- Wrote `rag/retriever.py`, `rag/generator.py` (single litellm call site,
  grounded-only system prompt, citation markers), `service/main.py`
  (/ask contract per spec). Syntax-checked only — runtime test pending
  embed completion. Assumption logged: confidence thresholds 0.55/0.35 are
  placeholders to calibrate against EVALUATION.md's negative cases.
- Assumption: versioned subtrees (/erpnext/v13|v14|v15/) excluded from
  Phase 1 corpus to avoid mixing conflicting version guidance without any
  version-detection to disambiguate (DECISIONS.md).
- Full run in flight at session end: 44,279 chunks embedding into Chroma
  (~30 min remaining). Chunk stats flagged for follow-up: max 4,751 chars
  (> bge 512-token window → truncated embeddings), min 3 chars junk stubs.
- Full-corpus index iterations (all embedded into cosine-space Chroma):
  v1 44,279 chunks — probe exposed two corpus defects. (a) Wiki alias URLs
  serve `{alias}.md` with 200 instead of 404, so pages were double-cached
  under old+new paths: 1,606 files were only 1,000 distinct docs; fixed by
  canonical-URL dedupe in `_load_documents` + physical prune. (b) Ten wiki
  pages embed screenshots as multi-KB base64 data-URIs; those became
  ~19k gibberish chunks whose near-identical vectors flooded top-k for
  unrelated queries (Sales Return FAQ dominating "override a controller").
  Fixed by stripping data-URIs at load time (`[image]` placeholder).
  v3 clean index: **1,000 docs → 7,424 chunks**; also dropped 551
  sub-50-char stub chunks.
- Retrieval tuning per spec's "tune k by manual testing": bge query-prefix
  instruction tested and rejected (no ranking improvement); RETRIEVAL_K
  raised 5→8 after k=10 probes showed relevant pages at ranks 6–7;
  query-time best-chunk-per-document dedupe added to stop one page's
  sections crowding top-k. Result: 12/15 eval questions retrieve clearly-
  relevant material top-3. Known misses logged in CURRENT.md.
- Confidence thresholds recalibrated from measured distributions:
  dev 0.766–0.848 vs negatives 0.623–0.719 → high≥0.73, no_match<0.60.
- Wrote `.env` from example; Ollama health check FAILED from WSL at all
  four candidate addresses (localhost/127.0.0.1/NAT gw/DNS IP). Session
  paused awaiting user action on Windows side or provider switch.
- (same session, continued) User made Ollama reachable at
  http://172.30.224.1:11434 (NAT gateway). Installed models: phi4-mini,
  qwen2.5-coder:7b; llama3.1:8b NOT installed — used qwen2.5-coder:7b via
  .env only, no pull needed.
- Live /ask verification loop with three prompt/threshold iterations:
  (1) phi4-mini echoed context passages verbatim → added anti-echo rules;
  (2) phi4-mini then over-declined on partially-covered questions (e.g.
  frappe.whitelist, whose explanation IS in corpus across rest_api.md +
  ajax-call pages) → allowed partial answers; switched to
  qwen2.5-coder:7b which synthesizes properly; (3) negatives initially
  classified "low" and spent an LLM call to decline → raised LOW cutoff
  to 0.72 so off-domain questions no_match deterministically.
- Discovery of the phase's key failure mode: on "override a controller"
  (retrieval miss, top score 0.766 from Credit-Limit keyword overlap)
  qwen2.5-coder fabricated a confident, plausible, UNGROUNDED answer —
  exactly what PROJECT.md forbids. Mitigation: HIGH threshold raised to
  0.80 (mediocre retrieval → "low" label) + anti-keyword-overlap prompt
  rule; fabrication persists at "low" confidence. Root cause is bge not
  surfacing override_doctype_class for this phrasing; hybrid keyword
  search logged as the future fix.
- Final live sweep: 15/15 dev questions answered through POST /ask,
  13 grounded+cited correctly; 3/3 negatives → no_match/empty sources.
- Model note: generation quality is highly model-dependent (echo vs
  decline vs synthesize); recorded so future model swaps get re-tested.

## [2026-08-23] — session 3: RAGAS baseline, Frappe app, README (Phase-1 DoD)

- Re-indexed (v4) to pick up title cleanup; same 7,424 chunks.
- Frappe app built from researcher-verified v15/v16 conventions: flit
  pyproject skeleton, modules.txt/patches.txt, hooks (app_include_js/css +
  extend_bootinfo), boot.py exposing copilot_api_base from site_config,
  vanilla-JS sidebar bundle with XSS escaping, sources list, confidence
  badges, distinct no_match styling. NOT bench-tested — no bench here.
- FastAPI gained CORS middleware (COPILOT_CORS_ORIGINS env, default `*` —
  acceptable because service binds localhost and holds no secrets).
- RAGAS baseline recorded (see CURRENT.md table): faithfulness 0.992,
  answer_relevancy 0.941, context_precision 0.562. Judge noise caveats
  noted per-row in the results JSON.
- Dependency archaeology for ragas: latest (0.4.x) requires scikit-network
  → no cp314 wheel + no compiler on this box → pinned ragas==0.2.15; that
  needed the 0.3-era langchain family (1.x removed chat_models.vertexai);
  ragas 0.2.x then broke under Python 3.14 asyncio (wait_for/timeouts
  task-context) → scoring isolated into `.venv-eval` (uv-managed Python
  3.12). Two-phase harness: `generate` (main venv) then `score` (.venv-eval).
- Flagged additions beyond the locked stack: ragas+langchain family
  (sanctioned by ARCHITECTURE "Evaluation: RAGAS"), uv as a dev tool only,
  requests/python-dotenv already noted earlier.
- Wrote root README (clean-machine setup incl. CPU-torch-first install,
  two-phase eval commands) + frappe_app/README.
- DoD checklist: all items done except real-bench verification of the
  sidebar (impossible on this box) — stated honestly in CURRENT.md.
