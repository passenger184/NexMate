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

  **RECOVERY 2026-09-09 (session 20):** the scoring phase had in fact
  COMPLETED on 2026-09-08 — `data/ragas_baseline_2026-08-24T11:32:30Z_124955.json`
  exists with timestamp 2026-08-24T11:32:30Z, but no session ever logged it.
  Verified before recording: (1) result rows match the samples file
  row-by-row (questions, answers, contexts, ground_truth all identical);
  (2) means recomputed from raw rows = stored values exactly (0.734/0.939/
  0.564). Env confirmed reproducible: ragas 0.2.15, .venv-eval Python
  3.12.14, judge qwen2.5-coder:7b reachable via OLLAMA_BASE_URL,
  bge-small embeddings cached. NO new score run was needed — the artifact
  was complete; it was a logging gap, not a scoring gap. Per-row detail:
  faithfulness 8/15 valid (5×1.0, Q3 0.0, Q7 0.5, Q11 0.375; Q12–Q15 all
  NaN = judge JSON-parse failures on the small local judge); answer
  relevancy 11/15 (Q12–Q15 NaN); context precision 9/15 (Q10–Q11, Q12–Q15
  NaN). Pre-hybrid for comparison: 0.992 (12 valid) / 0.941 (15) / 0.562
  (15). CURRENT.md RAGAS section rewritten with the post-hybrid table as
  the recorded baseline.
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

- Phase 2 Task 3 (Tier-2 edit flow): two-endpoint design over an ephemeral
  server-side proposal store (uuid id, 15-min TTL, 50-slot cap, one-shot on
  apply). Gate ordering refined during testing: the clean-tree check is
  target-aware — an untracked TARGET file gets the precise "not in version
  control" refusal (with git add guidance) instead of a generic
  commit-or-stash, because '?? <target>' in porcelain IS the dirt; apply
  re-checks tracked -> stale-content -> clean in that order so a changed
  target reports stale_proposal (the diff the user saw is void) even when
  unrelated dirt also exists. find must match exactly once; ambiguity
  refused with observed counts — this caught ME twice live when my own
  find strings ignored line-wrapping (0 occurrences), which is precisely
  the sloppy-edit class the gate exists to stop.
- Live end-to-end per DoD: prerequisite commit of session work first
  (ae49a87 — the clean-tree gate correctly refuses otherwise), then three
  real doc-drift fixes through the full propose->diff->confirm->apply->
  commit cycle: 8a520b3 (README chunk count 7400->7410 post-purge),
  9552c00 (README retrieval description matches hybrid RRF reality),
  c986988 (DEVELOPMENT gains the unittest command). Each verified as its
  own single-file commit via git show --name-only.
- Live refusals demonstrated: dirty-tree 409 naming the stray file,
  .env ignored-file 400 (won't touch secrets silently),
  confirmation-required 400, ambiguous-match 400 x2. Tree ended clean.

## [2026-08-24] — session 7: Phase 3 (Company Knowledge)

- SECURITY.md cloud-provider precondition checked before ingesting company
  material: GENERATION_PROVIDER=ollama (local) — no third-party exposure,
  no confirmation needed per the rule's wording.
- Assumption logged (spec said "ask what internal docs exist"): the repo's
  own markdown IS the internal-docs corpus on this box — root *.md +
  docs/*.md + progress/*.md as company_doc; user can point at external
  material later, ingest_project.py re-runs idempotently.
- ingest_project.py: stdlib ast boundary chunking for .py (no tree-sitter
  per spec), MarkdownNodeParser for .md, same resplit budget as public
  pipeline. Idempotent sync deletes only our_code/company_doc chunks.
- Two live-found bugs fixed during verification:
  (1) standalone module-docstring chunks lost best-per-document dedupe to
  symbol chunks → P1 got the intro without the mechanism and generation
  honestly declined; fix = merge preamble into first symbol chunk.
  (2) indexing our own journals put past negative probes in-corpus:
  auto_sync_with_jupiter df=4 defeated the df=0 veto AND an earlier
  leftover unconditional-rescue block (stale duplicate from the Phase-1
  gate edit) kept it high after the rare-term guard was added. Both fixed;
  N2 now low+sources (honest decline). Lesson: when editing gate ladders,
  grep for superseded blocks.
- Also: corpus_df initially looked up unfolded surface forms (pathsafe →
  pathsaf phantom df=0); normalize inside corpus_df. And uvicorn must be
  launched with setsid like any long-lived child — a timed-out parent
  shell otherwise takes the service down with its process group mid-probe.
- Phase 3 sweep saved to data/phase3_sweep.json (P1–P6, D2, negatives).

## [2026-08-24] — session 8: Phase 4 (Project Memory)

- Session store: JSON files under data/sessions/, id validated against a
  strict pattern BEFORE any path composition (traversal-proof), budgets
  applied at read time, atomic writes via tmp+replace. Both sides of an
  exchange stored per /ask call.
- Key design find: per-turn retrieval runs before generation, so pure
  anaphora ("which constant did you cite?") refuses at the gate before
  memory can matter. Added condense_followup — one LLM call rewriting the
  follow-up against history BEFORE retrieval; all gates then run on the
  rewritten query unchanged. Two prompt iterations: v1 paraphrased
  ("dampens" vs corpus "dampener") and kept filler ("which named..."),
  sinking IDF-weighted coverage to 0.365 < 0.45 despite cos 0.756 and the
  right #1 source; v2 demands verbatim symbols + no scaffolding. Turn-2
  with this specific small model still won't copy RRF_K; turn-3-style
  rewrites referencing BM25_K1/BM25_B work and correctly answered RRF_K=60.
  Documented as model-compliance limitation, not architecture gap.
- Resolved-issue memory: ONE chunk per applied edit (motive + message +
  diff), url_or_path embeds commit hash so dedupe can't collapse multiple
  resolutions of the same file. apply_edit indexes AFTER the commit (edit
  already safe) but surfaces failures loudly in the response (`memory`
  field). Backfills use --context supplied from actual knowledge of why
  each doc fix happened — never invented.
- Live verification: continuity incl. second-order follow-up answered
  RRF_K=60 in config.py [3]; stateless control shows no memory;
  reset clears thread but resolutions still retrieve ("README wrong chunk
  count" → high, recounts 8a520b3); auto-index on real edit 6235935.
- Dirty-tree gate refused my own first README edit attempt because Phase 4
  implementation was uncommitted — correct behavior; committed prerequisite
  d21c9ed first, exactly as designed.

## [2026-08-24] — session 9: Phase 5 (read-only ERPNext API tool)

- User supplied live instance (localhost:8081) + API credentials; stored
  ONLY in .env (gitignored, verified zero diff). Connectivity verified
  BEFORE any code: ping -> pong 200; DocType/Customer read confirmed.
- Client design per SECURITY.md read-only rule: the module exposes only
  GET-shaped helpers — no post/put/delete exists to misuse (test asserts
  this). Segments percent-encoded with safe=""; traversal input becomes
  an escaped literal segment instead of a path. Auth header built per
  request from env; error bodies truncated to 300 chars and never include
  auth material. Response cap 2MB; timeout loud as ErpnextUnavailable.
- Live bug caught before sign-off: get_doctype_schema omitted the
  "DocType/" prefix so it silently queried /api/resource/{doctype} (the
  document LIST) and returned data=[] — looked like "no schema" instead
  of an error. Fixed by prefixing; lesson: empty-but-200 responses deserve
  suspicion when shape changes.
- Instance reality check: fresh dev instance — Customer/Item/Sales Order
  hold zero documents; User(1)/Role(3+)/Company(1) have data. Verified all
  three ops on what EXISTS: schema(Customer, 87 fields), list+filter
  (Roles disabled=0 -> 10), document(User passengerlunar5@gmail.com, full
  roles table). Administrator doc -> clean 403 passthrough (Frappe-
  enforced), which doubles as the permission-behavior check.
- 59/59 tests green. Endpoints: /tools/erpnext/schema|document|list.

## [2026-08-24] — session 10: Phase 6 (Orchestrator/router)

- Router design: deterministic hint overrides -> one LLM classifier call
  (strict JSON route) -> default rag on ANY failure. Routing may be wrong,
  never fatal. Version-awareness via cached read-only
  change_log.get_versions (TTL 600s): live Frappe 16.31.0 / ERPNext
  16.32.3 injected into rag + erpnext prompts; instance down degrades to
  status=unavailable with empty preamble, answers continue.
- ERPNext branch: LLM extracts {op,doctype,...} JSON; small model needed
  the fence/prose-tolerant parser + ONE corrective escalation (first live
  run returned conversational prose and the honest low-failure path fired;
  after escalation "0 submitted Sales Orders... [1]" works).
- Two retrieval findings fixed live:
  (1) FUSION_COMPANY_BOOST hijacked GENERIC how-tos — but removing it
  wasn't enough because (2) our own EVALUATION.md/PROJECT.md/ragas_eval.py
  quote eval questions verbatim, so global BM25 ranked them above the real
  tutorial. Fix = scope-aware retrieval: PROJECT_SCOPE_HINTS gate both the
  boost AND company-pool participation; generic questions search public
  docs only. /ask keeps legacy always-company behavior (its sweep passed);
  /orchestrate is scope-aware.
- Also fixed: code-route sources lost titles in shape mapping (explain
  returns path/lines keys); image-markdown leak into prose (prompt rule).
- Live matrix: erpnext schema + honest-zero count + code walkthrough with
  line spans + rag generic/scoped split + misroute guard all PASS; versions
  live in every response.

## [2026-08-24] — session 11: Phase 7 (Employee/User mode)

- Mode implemented as a parameter on the SAME orchestrator
  (handle_question gains mode), not a parallel pipeline — per ROADMAP's
  "restricted persona/prompt on the same orchestrator and knowledge base".
- Least-privilege mapping: code agent fully denied (route_how gets
  "+denied" suffix so the UI can badge it); erpnext schema op denied but
  document/list kept (employees ask about their DATA); rag retrieval
  forced include_company=False (internal engineering docs are developer
  material) + EMPLOYEE_SYSTEM_PROMPT: plain UI steps, no code identifiers,
  explicit contact-an administrator fallback, grounded+cited like the dev
  persona. Unknown modes refuse loudly.
- Subtle implementation choice: schema denial happens AFTER extraction so
  the refusal can name the actual DocType and redirect toward document/
  list phrasing; run_erpnext_branch gained preextracted param to avoid
  double LLM extraction calls.
- Live matrix: E1 public-docs how-to (Sales Invoice steps cited), E2 code
  denial, E3 schema denial with redirect, E4 live count "20 roles... [1]"
  (no filter -> total roles; earlier 10 was disabled=0 — consistent),
  developer control unchanged (87-field Customer answer).

## [2026-08-24] — session 12: Phase 8 (Write-capable ERPNext Agent) — ROADMAP COMPLETE

- Write capability lives in tools/erpnext_write.py, deliberately separate
  from the GET-only read client. Master flag ERPNEXT_WRITE_ENABLED checked
  at propose AND apply (proven live: 403 before enabling).
- Tier-2 pattern reused for data writes: exact preview (method+URL+body),
  one-shot TTL'd proposals, explicit confirmed=true.
- Pre-flight schema validation refuses unknown fieldnames before any HTTP
  call — live-proven with a typo'd fieldname (custmer_nme -> 400 listing
  it). Frappe ignores unknown keys silently, so this guard catches what
  the server would have swallowed.
- DELETE does not exist anywhere in the write module (test-asserted);
  multi-step actions are sequential individually-confirmed proposals.
- Server-validation honesty proven: Frappe rejected group-type
  customer_group and our error path surfaced its exact message; adapted by
  querying valid leaf groups from the instance itself.
- Audit trail verified: both live writes appended with env_label=staging,
  reasons, payload keys; update confirmed by read-back through the read
  tool ("Copilot Test Customer (renamed)").
- Two test Customers remain on staging (clearly labeled); deletable via UI.

## [2026-08-24] — session 13: sidebar rebuilt to UI_SPEC + testable preview

- User asked whether the UI matched docs/UI_SPEC.md and how to test it.
  Honest answer was no (Phase-1-minimal panel, jQuery-dependent). Rebuilt
  frappe_app/public/js/copilot.bundle.js dependency-free (~530 lines) and
  rewrote copilot.css to Frappe-var-with-fallback tokens. Preview page at
  GET /ui/preview.html (FastAPI StaticFiles mount of frappe_app/public)
  loads the identical bundle, so everything is browser-testable here.
- Approval cards bring SECURITY.md's Tier-2 flows INTO the chat: /edit →
  unified diff card (Approve & Commit / Reject); /newdoc//editdoc → ERPNext
  write preview cards with env label + reason shown before Approve.
- Writes-enabled re-proven live post-rebuild: propose returned proposal_id
  + env=staging WITHOUT applying (no side effects; expires via TTL). The
  earlier 403 in reports was the pre-enable proof, not current state.
- node --check caught one real syntax error (over-escaped quotes in a JSX-
  free template string) before deployment; fixed.

## [2026-08-24] — session 14: UI error-banner contradiction fix

- Report: `/read` showed "Can't reach the assistant" AND "No such file…"
  for one request. Root cause: submit()'s single catch fed every rejection
  into appendError, which unconditionally prepended connectivity prose —
  so a correct HTTP 404 application error was wrapped in a false claim
  that the service was down. Not a double render; one banner, two claims.
- Fix: post() tags HTTP errors (isServerError+status); appendError takes
  opts.kind — server errors render a neutral amber banner with ONLY the
  server's message ("Request failed (HTTP 404). No such file…"); network
  failures keep the red connectivity banner. Catch passes flag through.
- Verified with the bundle's actual functions (extracted + node-eval)
  against real live-service bodies: 404 read, 400 traversal, 422 array
  all render single coherent messages; TypeError fetch failure and
  non-Error rejections keep connectivity wording.

## [2026-09-03] — code-route fabrication fix (reported live)

- Report: "what files are inside the project" (route=code) returned
  architecture-vision prose presented as current reality PLUS invented
  "Error/Unexpected Behavior" and "Recommendations" sections quoting a
  "developer mentioned" comment existing nowhere. Reproduced live
  verbatim before fixing.
- Root causes: (1) EXPLAIN_SYSTEM_PROMPT asserted every input is an
  error description — false premise forcing non-error questions into
  the error template (same class as Q3/Q9); the identifier grounding
  net cannot catch plain-prose inventions like fake quotations.
  (2) Retirement gap: no listing capability existed, and nothing marked
  ARCHITECTURE.md/ROADMAP.md/FUTURE_MULTI_WORKSPACE.md as vision.
- Fix: deterministic `looks_like_error` classifier selects between the
  (hardened) error prompt and a new CODE_QA prompt that forbids error
  framing, invented sections/quotations, and requires vision docs to be
  labeled planned-not-built; `_VISION_DOCS` suffix in passage headers;
  `_looks_like_listing` + deterministic `list_project_files` tree answer
  in the orchestrator code branch (employee denial stays first).
  Misclassification degrades gracefully both ways by prompt design.
- Tests: 10 new (classifier true/false, prompt selection incl. the exact
  reported question, vision label, listing detection + live-index answer,
  employee listing denial). Full suite 98/98 green.
- Live re-verified: reported question now returns the real 81-file tree
  with no vision docs and no error sections; a genuine KeyError report
  still gets a grounded diagnosis from real excerpts.

## Session 14 — UI visual restyle per docs/UI_VISUAL_SPEC.md

- Self-check restatement: the panel read as a generic SaaS chat widget
  (white cards, blue accent, pill badges, tracked-out uppercase labels,
  shadowed toggle/panel, GitHub-green/red diff). Plan was to convert it
  to an ERP-diagnostic instrument: ink-navy surfaces, hairline borders,
  amber as the single accent, teal strictly for trust, rust strictly for
  caution. Audit confirmed the generic defaults present, so the full CSS
  was rewritten rather than patched.
- What changed and why: token table from the spec verbatim
  (--surface-base #12141C etc.); shadows removed (toggle/panel now
  hairline-bordered); all four uppercase+tracked labels reverted to
  normal case; pill confidence badges became status LEDs (dot + short
  label); middle-dot-joined meta strings replaced (route "via rag
  (heuristic)", comma-joined sources/version); diff view rebuilt as a
  terminal diff with per-line colored gutters at 12% fills; citations
  muted with monospace paths; approve button moved to amber (single
  accent), committed-confirmation stays teal; user bubble flattened to
  an amber-tint hairline box. Slide-in kept short/decisive; approve
  commit sweep added; both gated behind prefers-reduced-motion. Kept
  `font-family: inherit` for Desk-typography matching (spec asks to
  check what Desk uses — no bench on this box, so inheritance is the
  honest best-effort); system mono stack lists JetBrains/IBM Plex Mono
  first with ui-monospace fallback when absent.
- One deliberate deviation logged: UI_SPEC.md says use Desk's CSS vars
  and don't hardcode hex; UI_VISUAL_SPEC.md mandates exact dark hexes
  and explicitly wants the panel to stand apart from Desk's light
  chrome. Followed UI_VISUAL_SPEC (newer, more specific) for colors.
- Verification: node --check clean; full avoid-list grep clean; 15/15
  DOM-harness checks pass against a stub that boots the real bundle
  (toggle/panel, LED, route/source/version rendering, copy buttons,
  diff gutters, approve sweep, write-card casing, server-vs-network
  error banners).
- Harness caught a REAL pre-existing bug the suite missed: /newdoc
  parsed its JSON from the wrong regex group (the /editdoc name slot),
  so every /newdoc failed with "Payload is not valid JSON." Fixed by
  reading group 3 unconditionally; covered by the new harness check.

## Session 15 — UI rebuild to docs/UI_VISUAL_SPEC_updated.md (literal)

- The updated spec supersedes the amber instrument-panel direction
  entirely: rebuilt `frappe_app/public/css/copilot.css` to its exact
  token table (`--panel-bg #15171C` … `--danger #E5484D`), `#2E6FF2` as
  the only accent (user bubble, send arrow, focus rings). Removed per
  spec: orange Send button (now icon-only accent arrow SVG), blue
  mode-dropdown fill (neutral + custom muted chevron), all shadows,
  all tracked-out uppercase labels, middle-dot-joined meta strings.
- Structural changes the new spec forced in the bundle: citation pills
  now read `[n] path` in monospace directly under the answer (separate
  numbered sources list deleted); confidence is a quiet inline row
  BELOW the pills (checkmark/success, warning/danger) and the old
  low/no-match callout boxes are gone; diff card header follows the
  literal "Proposed fix — <file>" pattern; approve is #F2F3F5/#15171C,
  reject is ghost, equal-width flex.
- Judgment calls (low-stakes, spec-silent): toggle button went neutral
  surface-card circle (accent is restricted to bubble/send/focus, and
  amber was banned); non-http pills expose section detail via tooltip;
  write-card keeps its existing content under the same muted header
  treatment; header title set to the spec's literal "ERPNext copilot"
  casing. UI_SPEC tap-to-open behavior preserved for http pills.
- Constraints preventing exact verification: no browser/screenshot
  tooling on this box, so instead of screenshots — 21 DOM-harness
  assertions (`/tmp/opencode/ui_smoke.js`, throwaway) booting the real
  bundle against a stub DOM, all passing; `node --check` clean; served
  bytes from GET /ui/* verified byte-identical to disk. Desk font
  matching still best-effort via `font: inherit` (no bench here).
- Harness caught one REAL pre-existing bug: `/newdoc` read its JSON
  from the wrong regex capture group, so every /newdoc failed with
  "Payload is not valid JSON." Fixed (group 3 unconditionally) and
  covered by a harness check.

## Session 16 — live-testing round, five bugs fixed

- (1) Markdown nested lists flattened into one numbered list with blank
  filler lines — the old code stripped indentation with `^\s*` regexes and
  wrapped runs by first-item type. Replaced with an indent-aware block
  parser (`renderLists` in the bundle): nesting preserved, blank lines
  tolerated inside lists via lookahead, ordered/unordered runs never
  mixed, continuation lines join their item.
- (2) Citations rendered as raw malformed markdown (`[[1]text](url)`).
  Two-layer fix: SYSTEM_PROMPT + EMPLOYEE_SYSTEM_PROMPT now forbid
  markdown-link citations (bare [n] only, UI renders pills from the
  structured sources array), plus a deterministic rewrite net mirroring
  the identifier-grounding pattern for when the small model slips anyway.
- (3) Short-input validation note firing repeatedly — consecutive
  identical system notes now collapse in `systemNote`. (Exact triple-fire
  trigger not reproduced; the dedupe fixes the symptom class regardless
  of whether the cause was key auto-repeat or rapid taps, since the guard
  path never set the busy flag.)
- (4) Classifier routed "hey" to the ERPNext live-lookup tool. New
  deterministic greeting short-circuit in `handle_question` answers with
  no retrieval/tools/LLM (new `smalltalk` route, added to the response
  contract). Defense in depth: document-op extraction now requires a
  name, closing the hole where the tool ran with a missing argument.
- (5) Condensation carried the previous topic onto greetings/topic
  changes. New `should_condense_followup` gate: condense only with
  history AND an anaphoric reference AND a non-greeting; wired into both
  /ask and /orchestrate. Errs toward over-triggering (`just/cite/cited`
  count) since the condense prompt forbids adding facts.
- Tests: 15 new Python cases (greetings, anaphora gate incl. the exact
  reported phrasings, extraction name rule, prompt contract, citation
  regex shapes); persisted the DOM harness as
  `frappe_app/public/js/copilot.bundle.test.js` (`node <file>`, exit-code
  contract) with nested-list + note-dedupe sections. Full run: 113
  Python green + 25 node checks green.
- Live-verified all five against the restarted service: smalltalk route
  for "hey"; "hello" in-session answers as greeting with no Sales
  leakage; anaphoric control still condenses; answers carry bare [n]
  markers with zero markdown-link citations.

## Session 17 — NexMate naming pass (per PROJECT.md product name)

- Renamed UI-facing product references from generic placeholders to
  NexMate: sidebar header + toggle tooltip, smalltalk greeting
  ("Hey, I'm NexMate! ..."), standalone preview <title>/heading,
  README title + tagline, FastAPI OpenAPI title. Code identifiers
  (`copilot_api_base`, `localStorage` keys, app dir), comments, and
  historical CHANGELOG entries deliberately untouched.
- Fixed the node harness header check that asserted the old spec casing
  the rename replaced. Full run: 113 Python green + 25 node checks
  green; live-verified greeting, preview title, and OpenAPI title.

## Session 18 — NexPilot conversational-redesign continuation (recovery + fixes)

- Recovered the previous session's uncommitted redesign instead of
  restarting: Layer-1 exact fast-path, Layer-2 NLU classifier (6 kinds),
  capabilities.py registry, clarify/scope/troubleshoot routes, degraded
  path, input-validation fix, condense gate, telemetry, 29-case routing
  dataset + harnesses. Verified each claim against the diff before
  touching anything; no reverts, no duplicated functionality.
- Fixed the routing-eval harness (3 real bugs, all in the harness, none
  in the product): (1) NLU=None cases raised through the mock instead of
  returning None (the graceful-degradation value); (2) the `_complete`
  mock forbade calls the erpnext/conversational branches legitimately
  make — now returns canned text while rag/tools counters measure
  wiring; (3) mocks were addCleanup-stacked across cases so code-where's
  scripted decide_route leaked into later cases — now ExitStack-scoped
  per case. Dataset gained scripted `task_route` for live-balance and
  code-where (same philosophy as scripted NLU: understanding decisions
  pinned, wiring measured). Heuristics deliberately NOT broadened —
  "outstanding balance"/"where is X implemented" as substring hints
  would be the phrase list the redesign forbids; the live classifier
  handles them.
- Genuine product gap found and fixed: thin follow-ups ("why?") ignored
  the NLU topic at retrieval time. New `_anchor_thin_followup`: task +
  follows_topic + named topic + <=4 words retrieves as
  "<topic>: <question>". Self-contained questions untouched, so no
  contamination (covered by unit tests incl. greeting-after-topic).
- Live failure found and fixed: with the provider unreachable, NLU hung
  5+ min in litellm retries, making the degraded path unreachable in
  practice. `_complete` gained timeout/num_retries params (defaults
  unchanged for answer generation); NLU uses NLU_TIMEOUT_SECONDS=20 +
  num_retries=0 (the corrective re-ask is the retry). Worst-case
  provider-down is now ~40s to honest clarify, not silence.
- Added ok/okay/got it to the exact ack fast-path (same canonical-token
  class as existing entries, full-match only — not a phrase list).
- Verification: 133 Python green (was 128 + 5 failing) + 26 node green.
  Live on :8001 with Ollama DOWN: hey/hi/bye/thanks/ok instant
  smalltalk; hii/invoices/why honest clarify/degraded ~40s; blank input
  clean 422; session invoices->clarify then hey->smalltalk (no
  contamination); versions live (Frappe 16.31.0 / ERPNext 16.32.3).
  BLOCKED: full 16-message NLU verification (Ollama at .env address and
  current nameserver both unreachable; no generation calls possible).
  Next session with Ollama up: rerun the 16-message matrix live.

## Session 19 — condenser version-echo injection found and fixed

- Injection point (measured, not guessed): turn-1's assistant answer
  carries the version authority ("...in ERPNext 16.31.0 and 16.32.3").
  `condense_followup` fed that verbatim into the rewrite context, and
  the small model copied the phrase into the refined query despite
  CONDENSE_PROMPT rule 5 forbidding it. Proved with a mocked
  `_complete` capture: identical echo in context, identical echo in
  output. Nothing downstream re-adds it — the contamination happens
  inside the condenser call itself. So the fix is at the injection
  point, not more prompt wording: `_scrub_version_echoes` strips only
  the version-number tokens (bare "in ERPNext" stays — it is a useful
  retrieval keyword), applied to assistant history turns before the
  context is built AND to the rewritten output as a backstop.
- `_classify_with_llm` inspected line-by-line: single `messages` build,
  two `_complete` calls = first attempt + corrective retry (the
  documented pattern, same as NLU/extractor) — no duplication, no dead
  validation, no cleanup needed. The earlier claim described code that
  does not exist in the working tree.
- Tests: 6 new `VersionEchoScrubTest` cases (digits-only scrub, context
  hiding, output backstop, history scoping). Full run: 145 Python green
  + 26 node green.
- Live probe (fresh session, restarted service with scrub loaded): Q1
  Sales Invoice how-to -> high (Sales Invoice docs); Q2 "what about
  Purchase Invoices?" -> refined "How do I create a Purchase Invoice in
  ERPNext?" -> high, Purchase Invoice docs, correct PO/supplier steps.
  Telemetry confirms no digit tokens in the refined query.

## [2026-09-17] — documentation reconciliation, progress handoff (Tasks 4.1/4.2)

- Scope: only `progress/CURRENT.md`, `progress/BLOCKERS.md` and this journal
  under `reconcile-architecture-and-production-hld`. Read proposal, design
  and tasks, the reconciled `ARCHITECTURE.md`/`ROADMAP.md`/`EVALUATION.md`,
  existing progress records and uncommitted progress diffs. Evidence basis:
  HEAD a7676ec plus the working-tree documentation reconciliation; this is
  source/document reading, not runtime verification or independent review.
- CURRENT now records the change IN PROGRESS and historical Phase 1–8
  acceptance with exceptions (2026-08-24), not a current phase or production
  readiness claim. Corrected stale "not started" phases, universal fallback,
  BM25 "cannot drift", RAGAS causality and preview-as-Desk overclaims.
  BLOCKERS now distinguishes pending documentary review from future
  implementation decisions and verification gates.
- Historical interpretation annotations: session 10's "ANY failure" applies
  to the old task-router summary, not the later NLU layer (failed NLU uses
  strong task heuristics or clarification). Sessions 18–19's "troubleshoot
  route" wording denotes an NLU kind, not an eighth response route. The
  29-case evaluation used mocked NLU; reported 145 Python + 26 Node checks
  are unit/mock and stub-DOM evidence. Session 18's outage is historical,
  not a current connectivity measurement. Session 19's later successful
  follow-up does not complete the full live conversational/NLU matrix.
- Sessions 13–15's browser-testable/UI conclusions refer to the standalone
  preview and stub-DOM checks, not verified Bench packaging or real Desk.
  The updated blue visual specification supersedes historical amber UI
  direction. Bench installation/assets/Desk remain unverified; Docker is
  planned. Live staging API results are not Bench/Docker delivery evidence.
- Preserved the user's existing uncommitted RECOVERY 2026-09-09 addition
  exactly, including artifact names, row details, dates and environment
  observations. No earlier journal entry was rewritten. That recovery is
  historical evidence, not a new score run or present provider-health check.
  Post-hybrid means remain 0.734 faithfulness (8/15), 0.939 relevancy
  (11/15), 0.564 precision (9/15), versus pre-hybrid 0.992 (12/15),
  0.941 (15/15), 0.562 (15/15). Changed coverage and self-judging prevent
  causal attribution: neither harmless judge noise nor regression is
  established. Q3/Q7/Q11 lows require independent per-question review;
  stronger judging and held-out cases remain future evidence requirements.
- Historical counts, installed versions, service availability and staging
  test-record observations do not establish today's inventory or settings.
  Session 3's "holds no secrets"/localhost CORS rationale is not current
  authentication evidence: later ERPNext clients use configured credentials.
  No credential or live configuration inspection occurred in this pass.
- Approved production direction means authenticated Frappe control/state
  ownership and separate private inference. It selects no physical tenancy,
  executor, protocol or ACL mechanism and grants no production-write or
  private-data cloud consent. Future contracts and runtime gates remain
  pending; MCP, Workbench and shared multi-workspace routing stay deferred.
- Documentary evidence: inspected the scoped diffs and reconciled claims
  against the HLD evidence matrix and evaluation methods. No tests, lint,
  model calls/downloads, network probes, runtime/configuration changes,
  data operations, commits, release or archive. Independent read-only review
  and final validation/outcome are PENDING with the parent; task checkboxes
  and HLD publication are outside this file ownership. The parent will
  append the final review outcome later; no Tasks 5.x completion is claimed.

## [2026-09-17] — documentation reconciliation, final acceptance (Tasks 5.x)

- Documentary acceptance COMPLETE for `reconcile-architecture-and-production-hld`.
  Two independent read-only content reviews (architecture/HLD fidelity and a
  fresh review after one earlier reviewer disclosed a /tmp script write
  outside the repository) plus a security review found no blocking
  documentation findings. The sole finding (extra blank line at EOF in this
  journal) was fixed and re-checked.
- Verification run by the parent: strict OpenSpec change validation
  (`openspec validate reconcile-architecture-and-production-hld --type
  change --strict --no-interactive`) PASSES; `git diff --check` PASSES;
  removal commit `a576c7b` for the four restored ADRs re-verified from Git
  history. Review coverage included R01–R20 traceability, current-vs-target
  separation, unresolved-decision register, restored-ADR provenance and
  preservation of the pre-existing 2026-09-09 RAGAS recovery entry.
- ALL 24 change tasks are now complete. The change is NOT archived and NOT
  committed — awaiting explicit user instruction. No runtime, configuration,
  dependency, deployment, model, service or data operation was performed;
  historical Phase 1–8 acceptance is not re-run and no production gate is
  passed. Remaining future gates (live NLU matrix, Bench/Desk/Docker parity,
  independent RAGAS judging, production contracts U1–U10) stay open in
  progress/BLOCKERS.md.

## [2026-09-17] — authenticated boundary documentation/evidence handoff

- Scope: README.md, DEVELOPMENT.md, progress/CURRENT.md, this journal and
  `openspec/changes/authenticated-frappe-control-plane/tasks.md` only.
  Read all five before editing; inspected proposal/design/three delta specs,
  appended ADR provenance, current config/auth/service/orchestrator/gateway/
  boot/bundle source and synthetic tests. Source basis is HEAD `3e060c3`
  plus the uncommitted boundary implementation, not a released artifact.
- README and DEVELOPMENT now distinguish authenticated chat-only Desk from
  legacy credential-gated APIs and dual-opt-in preview. Documented all
  inference/site configuration names/defaults, 64-hex non-repetitive key
  strength shape versus randomness, exact fixed site binding, empty role
  mapping without implicit admin elevation, and numeric `(0,900]` read
  timeout (300-second default, 5-second connect timeout), not total duration,
  cancellation or retries. Blank example-key assignment must be replaced
  or removed, not confused with unset. No real configuration was inspected.
- Documented public minimal `/health` versus readiness, sanitized failures
  without fallback, unavailable Desk tools/cards, local-only start-fresh,
  ignored stale responses without server cancellation, and unchanged
  transitional JSON sessions without ownership or ACL proof. The successor
  `frappe-owned-conversation-state` remains separately approved future work,
  not implemented: persistent Frappe records, user ownership, site association,
  caller-controlled ownership/JSON replacement and migration/compatibility.
- Supplied 2026-09-17 evidence, not rerun here: project `.venv` offline
  unittest discovery 190 tests OK with dotenv disabled and integrations
  mocked; Node harness 64 checks (26 preview + 38 Desk); syntax checks pass.
  Preliminary system `python3` discovery had 13 import failures with the
  wrong interpreter, superseded by the successful `.venv` run. Test sources
  are `tests/test_service_auth.py`, `tests/test_chat_boundary.py`,
  `tests/test_frappe_gateway.py` and the bundle harness. These are unit/mock/
  local-fixture and stub-DOM results, not live model or real Bench evidence.
- Marked 17/21 tasks checked from source plus supplied evidence: 2.1–2.3,
  3.1–3.5, 4.1–4.2, 5.1–5.3, 6.2, 6.4 and 7.1–7.2. Route inventory remains
  present in the service diff and inventory fixture. Rollback review is
  source/test-based: retain the inference gate and chat-only guard or disable
  Desk; synthetic mismatch/sanitized failure evidence is not an executed
  deployment rotation or rollback. No production bypass is a recovery path.
- Open tasks: 1.1 needs parent confirmation of validation chronology before
  implementation; 6.1 lacks user-supplied lint/typecheck commands (none found
  in the runbook/build metadata); 6.3 lacks authorized real Bench/Desk
  integration, including authentication/CSRF and assets; 7.3 awaits actual
  post-verification successor handoff. Parent final security and OpenSpec
  implementation reviews are still pending. No all-complete, full G2/M2,
  phase, production, release/write, ownership/ACL or cloud-consent acceptance.
- Documentary checks in this pass: strict OpenSpec validation
  (`openspec validate authenticated-frappe-control-plane --type change
  --strict --no-interactive`) and `git diff --check` passed. These structural
  checks are distinct from the pending final reviews. No runtime-test rerun,
  model/network/live service/deployment call, actual `.env` access, data
  mutation, new file, staging, commit or archive was performed.
- Preserved pre-existing CURRENT reconciliation/evidence and all previous
  journal entries, including the exact September 9 RAGAS recovery. Historical
  reconciliation was archived in `10d6c8e` under
  `openspec/changes/archive/2026-09-17-reconcile-architecture-and-production-hld/`;
  earlier unarchived/uncommitted statements describe that earlier handoff,
  not the active authenticated-boundary change.

## [2026-09-17] — authenticated boundary final bounded-review update

- Continuation scope: only progress/CURRENT.md, this journal and
  `openspec/changes/authenticated-frappe-control-plane/tasks.md`; README/DEVELOPMENT
  were already updated in the earlier handoff. Read all three before editing,
  re-checked the wording-fix sources (`orchestrator.py:366/382/406`,
  `tests/test_chat_boundary.py:236`) and prior progress records.
- Parent-reported review outcomes, 2026-09-17: strict OpenSpec validation
  before runtime implementation independently confirmed (task 1.1 checked);
  final read-only security review found no blocking finding; OpenSpec
  verification mapped 18 requirements and 51 scenarios, retaining
  incomplete-acceptance warnings. Recorded as completed bounded reviews —
  documentation/security/verification coverage only, not overall change
  acceptance and no fresh full pass of future runtime gates.
- Wording-fix evidence recorded as parent-reported: the last
  clarification/out-of-scope wording warning was fixed with scope-aware
  guidance and the additional regression test; the full project `.venv`
  rerun exited OK afterwards and the Node harness passed. The exact latest
  executed count is not inferred from source in this pass; 190 Python /
  64 Node remains the dated historical first full pass. No runtime suite
  was rerun by this documentation continuation.
- Task status: 18/21 checked (1.1 added). 6.1 stays unchecked — no
  applicable lint/typecheck commands were found in the runbook or build
  metadata and the user has not supplied any. 6.3 stays unchecked — no
  authorized real Bench/Desk integration evidence exists. 7.3 stays
  pending: the actual successor handoff follows verification; no new change
  was created and `frappe-owned-conversation-state` remains unimplemented.
- This pass performed no code/config edits, runtime-test reruns,
  model/network/service/deployment calls, `.env` access, data mutation,
  staging, commit or archive. Historical entries, including the September 9
  RAGAS recovery, are preserved unchanged.

## [2026-09-17] — authenticated boundary acceptance completion and authorized handoff (Tasks 6.1/7.3)

- Scope: only DEVELOPMENT.md, progress/CURRENT.md, this journal and
  `openspec/changes/authenticated-frappe-control-plane/tasks.md`. All four
  read before editing; all prior entries preserved unchanged. No code,
  configuration, dependency, runtime-test, model, network, service,
  deployment or data action; the target repository's `.env` was not read.
- User-supplied acceptance-session evidence, rerun by nobody in this pass:
  offline `PYTHON_DOTENV_DISABLED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
  LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m unittest discover
  -s tests` → **191 tests OK in 1.628s** with a Starlette/httpx deprecation
  warning and no dependency changes; Node harness 64/64 (26 preview + 38
  Desk); `node --check` clean for bundle and harness.
- Tooling inspection (user-supplied): root/nested pyproject/package
  metadata, Makefiles, tasks, CI, scripts and documentation show Python
  lint, Python typecheck, JavaScript lint and JavaScript typecheck each
  **not configured**. Nested `frappe_app/pyproject.toml` is packaging only;
  `.opencode` dependencies are agent tooling, not application tooling. Per
  explicit user acceptance, task 6.1 closes on this not-configured basis
  (not passed lint); no tooling stack is invented or installed.
- Bench-environment inspection (user-supplied): a Bench exists at
  `/home/passenger/projects/frappe_docker/development/frappe-bench` with
  apps `crm`/`erpnext`/`frappe`/`hrms` and `sites/development.localhost`,
  but no `erpnext_ai_copilot` app directory; `bench`, `chromium` and
  `google-chrome` absent from PATH; `ss` showed only DNS listeners, not app
  listeners; bounded no-proxy curl to `http://127.0.0.1:8081` exited 7
  (connection refused, HTTP 000); `docker ps`/`version`/`compose` could not
  execute `/usr/bin/docker` (Input/output error), so container status cannot
  be determined from that CLI — not evidence of no containers globally. No
  install/start/config/migration/login/browser/model/ERP-data actions.
- Credential note: the operator shell read the adjacent `frappe_docker`
  `.env` through name-filtered output (nonsecret values visible, not
  reproduced here); the target repository's actual `.env` was not read; no
  credential use or change occurred.
- Security/scope status: the prior read-only security review (no blocking
  finding) and the latest independent final scope review (no out-of-scope
  runtime/dependency work) are recorded, not rerun.
- Task 7.3 closed by explicit user authorization as handoff ONLY despite
  pending Bench verification: the next milestone requires the separately
  approved `frappe-owned-conversation-state` change — Frappe-owned
  persistent records, authenticated user ownership, site association,
  persistence across inference restarts, removal of caller-controlled
  session ownership, explicit migration/compatibility strategy and eventual
  removal of the JSON store. Nothing was scaffolded or implemented. Task
  status: **20/21 complete; only 6.3 remains open** (all real
  authentication/CSRF, Desk actions, assets, preview and minimal-health
  integration checks unverified; synthetic tests do not substitute).
  This acceptance/handoff is not full G2/M2, production readiness, owned
  state, ACL isolation, release/production-write approval or private-data
  cloud consent. No tests, lint/typecheck installs, network/runtime changes,
  staging, commit or archive were performed by this pass. Strict OpenSpec
  change validation and `git diff --check` re-run clean after these edits.
