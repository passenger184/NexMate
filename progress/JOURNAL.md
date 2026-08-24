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
