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

## [2026-08-24] — session 4: verification run + hybrid retrieval rebuild

- Tester-subagent independent verification (live service, HEAD d3538e3):
  9/15 clean, Q3 fabrication confirmed fixed by the tightened gate, but the
  gate caused a coverage regression (Q5/Q6/Q15 refuse at 0.788-0.797 vs
  0.80) and N2/N3 negatives return low+sources instead of no_match; Q7/Q12
  citation/grounding defects; one stale /erpnext/v13/ page found embedded.
  Findings logged in CURRENT.md; DoD item 2 declared failing.
- Implemented hybrid retrieval per the pre-logged plan: in-house Okapi BM25
  over the Chroma corpus (no rank-bm25 dep), RRF fusion, second-chunk-per-doc
  rule for near-tied lexical evidence, suffix-folding tokenizer. Iterations:
  - First coverage-veto design used IDF-weighted term coverage but weighted
    unseen query terms at ZERO -> fabricated-feature negatives passed the
    veto. Fixed: unseen terms weigh max-IDF; plus a dedicated veto for terms
    absent from the entire corpus (df=0 is the fabrication signal; merely
    rare jargon like 'orm' df~10 must NOT veto - first attempt at an
    idf>=6 threshold veto broke Q7/Q14 and was replaced by the df=0 rule).
  - Header-boost experiment REVERTED same session: boosting title/section
    matches let every page titled '*controller*' sweep Q3's rankings and
    buried hooks.md deeper. Replaced by FUSION_KEYWORD_WEIGHT=1.5 +
    DOC_SECOND_CHUNK_MIN_RELATIVE_BM25=0.9, which admits the winning section
    of a multi-section page when siblings tie lexically.
- Gate recalibration on measured distributions: rescue band cos>=0.74 with
  cov>=0.45; final probe separation: 15/15 positives high, 3/3 negatives
  no_match (data/sweep_2026-08-24_hybrid_v2.json).
- Incident during v13 purge: my naive '/erpnext/v' substring filter matched
  /erpnext/v(aluation|at|olunteer)... and deleted 5 legitimate chunks;
  repaired by re-embedding those pages through the standard pipeline
  (index 7424 -> 7405 -> 7410). Root cause fixed properly with
  config.is_excluded_doc_path() now shared by crawler AND loader (the
  crawler had the same latent bug since the pattern was introduced).
- Generator: added verbatim-identifier prompt rule + deterministic
  backticked-identifier grounding check with ONE corrective escalation
  (steered toward replacement-over-deletion after the first wording made
  the model decline instead of substituting on_update for after_save).
- Final full live sweep: 15/15 high confidence, all with sources and inline
  [n] markers; 3/3 negatives exact no_match shape (empty sources, ~1s,
  no LLM call). Grounding spot-verified against corpus text via grep:
  Q12 bench commands verbatim in bench-commands-cheatsheet.md /
  frappe-commands.md / bench-procfile.md; Q7 before_migrate/after_migrate in
  hooks.md and 'clean and map the data' steps verbatim in
  accounting-migration-overview.md; Q10 integration-user/API-credentials
  verbatim; Q15 System-Settings traceback toggle verbatim in security-faqs;
  Q3 answers extend_doctype_class from hooks.md (corpus marks it preferred
  in v16+); Q6 answers on_update per executing-code-on-doctype-events.md.
- New tooling: evaluation/retrieval_probe.py prints fused scores + gate
  decision for the whole question set (used for calibration).
- Assumption logged: negative-test expectation is the DESIGNED behavior -
  N2/N3-class probes now return no_match+empty sources via the df=0 veto,
  not the old low+sources shape; EVALUATION.md's letter ('must correctly
  decline') and letter-of-contract both satisfied.
- Not done this session: RAGAS re-score post-retrieval-change (baseline
  stands; harness ready), real-bench sidebar install (still impossible here).

## [2026-08-24] — session 5: Phase 1 closed, Phase 2 opened

- RAGAS re-score attempt: generate phase completed against the hybrid
  pipeline (data/ragas_samples_2026-08-24T11:32:30Z.json — 15/15 rows,
  all confidence=high, 8 contexts each; harness bug fixed first:
  ragas_eval.py still called classify_confidence with the pre-hybrid
  signature). Scoring phase (~40 min) was launched detached and then
  ABORTED mid-run by user order: Phase 1 is functionally complete enough;
  drop bench install + re-score. Samples file kept so a future session
  can score it directly without regenerating (command in CURRENT.md).
- Researcher-subagent invocation for the runbook failed twice with
  provider network errors; fell back to direct read-through of the
  evaluation harness instead (same outcome, no code risk encountered).
- ROADMAP.md phase pointer moved to Phase 2 with an honest Phase 1 status
  line (functionally complete, user-accepted; deferred items listed).
- Phase 2 Task 1 outlined in CURRENT.md: PROJECT_ROOT config + canonical
  symlink-aware path-safety helper + Tier-1 read_file + traversal-rejection
  verification, per docs/PHASE_2_SPEC.md and SECURITY.md guardrails.

## [2026-08-24] — session 6: docs audit + Phase 2 Task 1

- Full doc-set audit at user request (all 15 .md files + opencode.json).
  Fixes applied: AGENTS.md duplicate "5" in read order, stale PHASE_1_SPEC
  references made phase-agnostic, ADR location corrected to DECISIONS.md
  (the `decisions/` dir it named was empty); EVALUATION.md Phase-1 DoD
  boxes ticked to match tester-verified reality; UI_SPEC.md pointed from
  nonexistent MEMORY_SPEC.md to PHASE_4_SPEC.md; README bench-install typo
  (erpnot->erpnext); SECURITY.md current-phase section refreshed for the
  Phase 2 transition; CHANGELOG.md backfilled with real history;
  opencode.json instructions now include CHANGELOG.md (restart needed to
  take effect). No guardrail-weakening changes anywhere.
- Phase 2 Task 1 built and verified. Design decision logged here rather
  than as an ADR (implementation detail, not a stack choice): path safety
  is resolve-THEN-verify — Path.resolve() collapses symlinks/'..' before
  containment is checked against resolved PROJECT_ROOT — so a symlink
  inside the root pointing outside is rejected on its DESTINATION.
  Rejection raises with both the requested and resolved paths (loud, no
  sanitization/redirect), per SECURITY.md wording. In-root symlinks are
  allowed (they're legitimate project structure).
- tools/files.py caps reads at MAX_READ_FILE_BYTES (1MB default) instead
  of truncating silently — truncation would corrupt any code explanation
  built on it; raising the cap is a deliberate act. Strict UTF-8 decode:
  binary content refuses loudly rather than returning mojibake.
- Verification: 15/15 stdlib-unittest cases green; live curl checks via
  restarted service — real file OK, ../..-traversal / /etc/passwd /
  symlink-out all HTTP 400 with explanatory detail, missing file 404,
  oversized/binary covered by unit tests. Spec DoD item "path-traversal
  attempt verified rejected, not silently redirected": done.

## [2026-08-24] — session 6, continued: Phase 2 Task 2 (Tier-1 search + explain)

- search: git ls-files --cached --others --exclude-standard as the file
  universe (gitignore-aware AND includes new untracked files — the two
  naive alternatives each fail one way). Regex-first with silent literal
  fallback (declared in the response), grep-style case-sensitive default.
  Every listed file re-scoped through resolve_in_project before reading —
  the gitignore filter is a quality feature; pathsafe remains THE
  boundary. Honest counters for skipped binary/large and truncation.
- explain: term extraction (quoted > identifier-length-ranked > noise-
  filtered), then scoring = position-weight x specificity(x3 for
  snake/CamelCase) x per-term match count CAPPED AT 5. The cap matters:
  first live iteration let 'response/client/parse' hit-storms in ingestion
  scripts outrank service/main.py for a read_file KeyError description;
  after the fix service/main.py:194-218 ranks #1 and the walkthrough cites
  only real identifiers. Excerpts window around hits; sources report the
  true excerpt span (min/max-of-hits spans were misleadingly wide).
- LLM access via rag.generator._complete + _ungrounded_identifiers reuse —
  still exactly one litellm call site in the codebase; explain's prompt
  requires `path` + plain line-number citations so the backtick grounding
  net stays compatible.
- Zero-hit or zero-term descriptions decline WITHOUT an LLM call (asserted
  by tests), matching the /ask no_match philosophy for Tier 1.
- Verification: 30/30 unittest (incl. decoy-file regression + excerpt-span
  tests); live search 18 hits/65 files with .env excluded; live explain
  grounded walkthrough of the read_file flow.
