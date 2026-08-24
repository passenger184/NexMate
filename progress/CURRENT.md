# progress/CURRENT.md — Current State

**Last updated:** 2026-08-24 (session 11: Phase 7 — Employee/User mode — restricted persona live with least-privilege routes; DoD met)
**Current phase:** Phase 7 — Employee/User mode (ROADMAP.md) — functionally complete, awaiting user acceptance
**Current task:** None in flight. Proposed next: Phase 8 — Write-capable ERPNext Agent (LAST roadmap phase; staging-only per SECURITY.md).

## Phase 6 closure note (2026-08-24)

Phase 6 accepted via user instruction to proceed (commit a56fa83); routing
matrix and version-authority checks below.

## Phase 5 closure note (2026-08-24)

Phase 5 accepted via user instruction to proceed (commit a029ddc); DoD met
per the verification table below.

## Phase 4 closure note (2026-08-24)

Phase 4 accepted via user instruction to proceed; verification table and
DoD status below.

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

**Phase 7 is functionally complete** (see below). Upon user acceptance:
start **Phase 8 — Write-capable ERPNext Agent**, the LAST roadmap phase.
SECURITY.md hard rules apply before any code: staging-only until
explicitly approved for production, every write needs a confirmation
step, no silent multi-step actions against live company data.

## Phase 7 — Employee/User mode: what changed

- **Same orchestrator, restricted persona** (`orchestrator.handle_question`
  gains `mode`): no new subsystem, exactly as ROADMAP.md prescribes.
- **Least privilege by route**:
  - `code` agent -> DENIED for employees (polite out-of-scope message,
    `route_how` marked `+denied`); developers unaffected.
  - `erpnext` schema introspection -> DENIED; document/list lookups stay
    available (employees ask about their data, not metadata).
  - `rag` -> public-docs-only retrieval (company engineering corpus is
    developer material), answered with the plain-language desk-user
    persona: UI steps via awesomebar/lists/buttons, explicit rule to say
    "contact an administrator" instead of guessing at admin tasks.
- **`POST /orchestrate`** gains `mode` ("developer" default | "employee"),
  echoed in responses; unknown modes refuse.
- Generator carries two personas (`rag.generator.PERSONAS`); version
  authority still injected on both.

## Phase 7 verification (live POST /orchestrate)

| Probe | Result |
|---|---|
| E1 how-to as employee | "How do I create a Sales Invoice?" -> plain UI steps cited from public Sales Invoice docs, conf=high |
| E2 code question as employee | pathsafe question -> DENIED, "needs developer access... ask your administrator", route_how=heuristic+denied |
| E3 schema as employee | "What fields does Customer have?" -> denied with redirect hint toward document/list questions |
| E4 live list as employee | "How many roles are set up?" -> high, "20 roles ... [1]" from the real instance |
| Developer control | SAME Customer-fields question in developer mode -> full 87-field schema answer, unchanged |

## Phase 7 DoD status (self-defined; no dedicated spec doc — ROADMAP.md
## defines this phase as "restricted persona/prompt on the same
## orchestrator and knowledge base")

- [x] Restricted persona live (plain-language desk-user prompt, separate
      from the developer persona)
- [x] Least-privilege tool access enforced (code agent + schema denied;
      document/list allowed) — unit-tested AND live-verified
- [x] Knowledge-base restriction verified (employee RAG searches public
      docs only — asserted include_company=False in unit test)
- [x] Developer mode provably unchanged (live control probe)
- [x] progress/CURRENT.md updated (this document)

## Phase 6 — Orchestrator/router: what changed

- **`orchestrator.py`** — routes each question: `erpnext` (live-instance
  data), `code` (this repo's source/errors), `rag` (default, general
  knowledge). Deterministic hint overrides first; one LLM classifier call
  breaks ties; ANY failure defaults to rag — routing can be wrong, never
  fatal.
- **Version-awareness (PROJECT.md non-negotiable)** — the connected
  instance's Frappe/ERPNext versions are fetched read-only
  (`frappe.utils.change_log.get_versions`, cached TTL 600s) and injected
  into generation prompts on rag + erpnext branches: answers must be valid
  for Frappe 16.31.0 / ERPNext 16.32.3, not "latest docs". Instance down
  -> honest `status: unavailable`, answers continue without version
  authority.
- **ERPNext branch**: LLM extracts {op, doctype, name?, fields?,
  filters?, limit?} as strict JSON (one corrective escalation for
  fence/prose slips), executes the matching read-only client op, answers
  ONLY from the returned payload with [1]-style citations +
  identifier-grounding net.
- **Scope-aware retrieval** — generic how-tos search PUBLIC docs only;
  project-scoped questions (PROJECT_SCOPE_HINTS) keep the boosted company
  pool. Root cause fixed: our own meta-docs quote eval questions verbatim,
  so BM25 ranked EVALUATION.md/PROJECT.md above the real Frappe tutorial
  for generic questions.
- **`POST /orchestrate`** — single entry point; sessions behave like
  /ask (routing runs on the condensed follow-up question).

## Phase 6 verification (live POST /orchestrate)

| Probe | Result |
|---|---|
| Live schema question | route=erpnext(heuristic) -> "Customer DocType has 87 fields", payload-cited, versions=live |
| Honest empty count | "How many submitted Sales Orders..." -> "0 ... [1]" (instance truly has none) |
| Code question | route=code -> pathsafe walkthrough citing tools/pathsafe.py with line spans |
| Generic how-to | route=rag(classifier) -> public DocType tutorial leads; meta-file hijack GONE |
| Scoped project Q | company corpus cited (ARCHITECTURE/DECISIONS/chunk_and_embed) |
| Misroute guard | "What is a DocType conceptually?" stays rag, never touches the instance |
| Version authority | frappe 16.31.0 / erpnext 16.32.3 in every response; image-markdown leak also fixed |

## Phase 5 — Read-only ERPNext API tool: what changed

- **`tools/erpnext.py`** - GET-only by construction (no post/put/delete
  helper exists in the module; asserted by test). Credentials from .env
  (ERPNEXT_BASE_URL/API_KEY/API_SECRET, gitignored), sent only as the
  Authorization header, never logged or echoed in errors. Path segments
  percent-encoded with safe="" so ../ and / cannot form URL paths.
  Payloads capped (ERPNEXT_MAX_RESPONSE_BYTES=2MB); timeouts loud.
- **Service endpoints**: POST /tools/erpnext/schema {doctype},
  /document {doctype,name}, /list {doctype,filters?,fields?,limit?,
  order_by?} (limit hard-capped at 100). Statuses mapped cleanly:
  instance-down -> 503, upstream 403/404 passed through, oversized -> 413.
- **Config**: ERPNEXT_TIMEOUT_SECONDS / _MAX_RESPONSE_BYTES /
  _DEFAULT_LIST_LIMIT / _MAX_LIST_LIMIT.

## Phase 5 verification (live instance http://localhost:8081)

| Check | Result |
|---|---|
| Connectivity + auth | ping -> pong, HTTP 200 |
| Schema | Customer: module Selling, naming_rule By-Naming-Series, 87 field rows |
| List + filter | Roles disabled=0 -> exactly 10 expected roles; User list -> the instance's one real user |
| Document by name | passengerlunar5@gmail.com -> full record incl. roles table |
| Permission behavior | Administrator doc -> clean HTTP 403 passthrough (Frappe protects it) |
| Error path | nonexistent DocType -> clean 404 with Frappe's message |
| Empty-data honesty | Customer/Sales Order lists return count 0 (no records in instance) |
| Tests | 59/59 unittest green (7 new client cases incl. GET-only-by-construction) |

Bug found and fixed during live verification: schema lookup omitted the
DocType/ path prefix, silently querying the document list instead -
surfaced as data=[] and fixed before sign-off.

## Phase 4 — Project Memory: what changed

- **Session continuity** — `/ask` gains optional `session_id` (validated
  against `[A-Za-z0-9_-]{1,64}` before touching disk). Threads persist as
  JSON under `data/sessions/` (survive restarts), capped at
  SESSION_MAX_TURNS/SESSION_MAX_CHARS at read time. `POST
  /tools/session/reset` implements "start fresh" — clears thread state,
  never touches indexed knowledge.
- **Condense step for follow-ups** — per-turn retrieval runs BEFORE
  generation, so anaphoric follow-ups ("which constant did you just
  cite?") retrieve nothing alone and hit the absolute refusal. With a
  live session, `generator.condense_followup` rewrites the question
  against recent turns first (best-effort; falls back to raw question on
  failure); retrieval + all confidence gates then run on the rewritten
  query. Prompt demands verbatim symbols and no scaffolding filler.
- **Resolved-issue corpus** — every applied Tier-2 edit now indexes ONE
  chunk into the same collection (`source_type: resolved_issue`,
  url_or_path `<file>@<hash>` so dedupe never collapses resolutions):
  motive (proposal `context`) + commit message + diff. `tools/memory.py`
  also provides `--backfill-commit`; the three real Phase 2 doc fixes were
  backfilled with their true motivations, and the first post-feature edit
  (`6235935`, README layout) auto-indexed via the apply flow.
- resolved_issue chunks ride the boosted company pool; generator labels
  them "past fix in this project".

## Phase 4 verification (live)

| Probe | Result |
|---|---|
| Continuity, second-order | "And what other constants sit next to it in that same config block?" → condensed using prior turns' symbols → high → "`RRF_K`, set to 60 in the `config.py` file [3]" |
| Stateless control | Same follow-up without session_id → no memory of prior exchange |
| Reset semantics | reset → cleared:true; subsequent turn has no memory; resolved-issue chunks STILL retrievable afterwards |
| Resolution retrieval | "I remember the README used to have the wrong chunk count - what happened?" → high, recounts commit 8a520b3's story, sources led by `resolved_issue: README.md` |
| Auto-indexing on apply | propose(context=…)→apply → `memory.indexed=true`, chunk `README.md@6235935` |
| Backfills | 8a520b3 / 9552c00 / c986988 indexed with real motives |

Known limitation (documented, not a bug): follow-ups whose OWN phrasing
retrieves poorly can still land in `low` before condensation quality can
save them when the small judge/generator model paraphrases instead of
copying symbols (e.g. it wrote "dampens" where corpus says "dampener");
turn-3-style symbol-bearing rewrites work.

## Phase 4 DoD status (`docs/PHASE_4_SPEC.md`)

- [x] Session continuity verified (incl. second-order anaphoric follow-up)
- [x] ≥3 real Phase 2 edits indexed as resolved_issue chunks (3 backfilled
      + 1 automatic = 4)
- [x] Similar-question test retrieves and cites the resolution
      (README chunk-count case, commit hash included)
- [x] "Start fresh" clears visible thread without deleting resolved-issue
      knowledge (verified live)
- [x] `progress/CURRENT.md` updated (this document)

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
