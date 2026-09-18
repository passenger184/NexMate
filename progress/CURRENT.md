# progress/CURRENT.md — Current State

**Last updated:** 2026-09-18 — `frappe-owned-conversation-state` implemented and live-verified in the test Bench (22/22 tasks); no commit/push.
**Current phase:** Historical Phases 1–8 functionally accepted 2026-08-24 with recorded exceptions; no new phase or production-readiness acceptance.
**Current task:** Awaiting user review of the `frappe-owned-conversation-state` implementation; archive when approved. Successor work (if any) needs a separately approved change.

## 2026-09-18 frappe-owned-conversation-state — implementation and live evidence

Change `openspec/changes/frappe-owned-conversation-state/` (G3): Frappe-owned
`NexMate Conversation` records (owner+site, child turn table) replace the
deleted JSON session store; gateway `ask()` takes an optional owned
`conversation_id` (stateless without); new owner-checked
start/transcript/reset methods; inference validates envelope consistency
only and persists nothing; legacy `session_id`/reset paths fail explicitly
(422/404). Desk auto-starts/restores/resets owned threads; preview
stateless. Live Bench (`frappe_docker_copilot_test`, site `frontend`):
migrate created tables; start→ask→transcript→reset verified as
Administrator; System-Manager probe user refused on admin threads and
served on its own; 3-way parallel asks serialized (1 winner + 2 loud
`Conversation is busy` retries, zero lost turns, retry succeeds);
inference-down ask leaves the lone user turn (explicit pre-append commit);
backend restart preserves threads; Task 6.3 boundary checks re-verified
(401s, health, forged-field refusal). Limits: generation LLM unreachable
here (degraded clarify, no tools), so cited-RAG-with-history is
unit-covered only; `ARCHITECTURE.md` still describes the old JSON store
(separate HLD reconciliation, not edited here). Test data cleaned
(0 threads, probe user disabled). Suites: 202 Python OK, 67 Node PASS.
No commit/push; live Bench left running with the app installed.

## 2026-09-18 Task 6.3 verification — live Bench/Desk acceptance (PASSED with noted limits) [SUPERSEDED for sessions: threads are now Frappe-owned; boundary checks re-verified above]

Environment (user-scoped to `~/copilot/frappe_docker_copilot_test`, project
`frappe_docker_copilot_test`): Docker Desktop 4.86.0 recovered from the
2026-09-17 WSL-integration outage on its own; no Bench/Docker repair was
needed. 8 services Up (backend/frontend/websocket/queues/scheduler,
mariadb:11.8 healthy, redis ×2), image `frappe/erpnext:v16.33.0`, single
site `frontend` (default), Frappe 16.31.0 / ERPNext 16.33.0. NexMate
installed live-container style (existing `frappe_app/` copied into
containers, `env/bin/pip install -e`, `install-app`, `bench build`;
frontend serves built `copilot.bundle.7NJBDU3K.js` + css, both HTTP 200).
FastAPI ran from this repo (`.venv` uvicorn :8000) with a strong 64-hex
test key, `NEXMATE_FRAPPE_SITE=frontend`, `ENV=development`,
`DEV_UNAUTHENTICATED=0`; stopped after the run. Site config:
`copilot_api_base=http://host.docker.internal:8000` (resolves in-container),
`nexmate_developer_roles=["System Manager"]` (JSON list via `--parse`),
`nexmate_inference_timeout=30` (JSON number via `--parse`).

| # | Check | Result |
|---|---|---|
| 1 | Desk reachable | PASS — `:8081/desk/home` 200 (442 KB) as Administrator |
| 2 | App loaded | PASS — Desk HTML includes built bundle hash; `bench list-apps`/Module Def/hooks confirm install; `get_versions` lists all 3 apps |
| 3 | Authenticated `ask()` | PASS — session-cookie + CSRF POST → 200 (`smalltalk/high`, `capability/high`) |
| 4 | No direct browser→inference | PASS — Desk flag is `pathname==="/ui/preview.html"`; Desk path fetches same-origin `/api/method/...` only (0 `:8000` fetches); gateway-only key server-side; leak scans (key vs Desk HTML/bundle/logs) clean |
| 5 | Server-side user/site/mode | PASS — mode derived from actual roles; forged `user`/`execution_scope` fields → `unsupported_gateway_fields`; site mismatch → sanitized `gateway_upstream_http_error` |
| 6 | No browser elevation | PASS — mapping `[]` + browser `mode:"developer"` → `employee` (2/2, no implicit admin elevation); `["System Manager"]` → `developer` (3/3); browser `mode:"employee"` ignored (3/3) |
| 7 | Server-side credential forwarding | PASS — end-to-end 200s only possible with valid key (fail-closed service); wrong-key rotation produced safe gateway failure, restored after |
| 8 | FastAPI rejects without key | PASS — no header → 401 `service_credential_required`; wrong key → 401 `invalid_service_credential` (strict even in development) |
| 9 | Minimal `/health` | PASS — exact `{"status":"ok"}`, unauthenticated, incl. from inside the container |
| 10 | Chat-only preserved | PASS — versions suppressed (`unknown/unavailable`); capability text describes chat only |
| 11 | No code/ERPNext/write dispatch | PASS — code + ERPNext probes → deterministic Desk-unavailable denial; write probe → clarify/low; Customer count 0 before and after |
| 12 | Normal chat | PASS (bounded) — `hi`/`help` high-confidence; LLM-backed RAG untested (see limits) |

Limits (unchanged scope, not failures): generation LLM unreachable from
this runner (LiteLLM errors → safe degraded `clarify`, no tools/leak), so
cited-RAG answers were not exercised live; Desk start-fresh button not
clicked live (static code evidence only); transcript restore/streaming/
realtime remain target work. Operational lessons: (a) gunicorn workers
cache site config — `set-config` needs `--parse` for JSON types AND a
backend restart before retest (one false "mode honored" reading was stale-
worker flap, disproven 3/3 after restart); (b) repo app has three
Bench-install gaps, shimmed container-side ONLY (repo untouched):
`env/bin/python` is the frappe runtime (not `/usr/local/bin`), model-sync
needs an (empty) `<app>/<Desk-module>` submodule for the `modules.txt`
entry, `app_description` hook is required by `get_versions()`, and
`public/` must live under `<app>/<pkg>/public` for esbuild discovery;
(c) `sites/assets` symlinks to container-local `bench/assets`, so built
files were mirrored backend→frontend for nginx. Archived change and specs
left untouched (still record 20/21 pending this note); no commit/push;
`frappe-owned-conversation-state` not started.

## 2026-09-17 authenticated boundary — implementation and bounded evidence

Source basis: HEAD `3e060c3` plus the uncommitted boundary implementation,
read on 2026-09-17. The user supplied the offline execution results below;
this documentation pass inspected source/tests, not live services or secrets.

- `config.py:16` and `service/auth.py:30`: production-default credential gate
  on all current direct endpoints, assets, docs, unknown paths and OPTIONS.
  Exact `/health` is fixed public minimal liveness, not readiness. The
  64-hex key must be non-repetitive; this is strength-shape validation, not
  proof of random generation. Only both exact development settings permit
  missing-header requests with valid/unset key. Blank remains invalid,
  including the copied `.env.example` assignment; see DEVELOPMENT.md.
- `frappe_app/erpnext_ai_copilot/api.py:116`: non-guest chat gateway derives
  user/site from Frappe and persona from explicit `nexmate_developer_roles`
  (default `[]`, no implicit admin elevation). Server-only key/destination;
  fixed chat-only envelope, sanitized failures, no redirect or direct-browser
  fallback. Configured read timeout is numeric `(0,900]`, default 300 seconds,
  with a 5-second connect timeout; not total duration, cancellation or retry.
- `service/auth.py:75`, `service/main.py:572`: authenticated complete envelope
  and exact `NEXMATE_FRAPPE_SITE` check precede history/routing/retrieval;
  malformed envelopes cannot downgrade to legacy, even under dev exemption.
- `orchestrator.py:862`, `service/main.py:656`: request-local `chat_only`
  blocks code/ERPNext dispatch before entry in both personas, including
  troubleshooting, rewritten follow-ups and degraded routing. Incidental
  version calls are suppressed; conversational/cited cached RAG remains.
  This is not ACL-aware retrieval or a new corpus permission grant.
- `frappe_app/public/js/copilot.bundle.js:360`: Desk chat uses Frappe only;
  mode override, slash tools and stale approval/rejection controls are
  unavailable. Start-fresh clears locally and replaces the session ID, with
  no JSON deletion request. Old responses are ignored, not cancelled.
  Preview remains a separate dual-opt-in legacy workflow without a key.
- Optional legacy sessions still forward unchanged to JSON storage. Site
  validation is not authenticated history ownership or site-isolated storage.
  Standard Frappe authentication/CSRF integration is not proven by mocked
  Frappe or stub-DOM tests. Do not deploy this as multi-user/production-ready.

| First full-pass evidence supplied for 2026-09-17 (before wording fix) | Result and limitation |
|---|---|
| `.venv` offline `python -m unittest discover -s tests`, dotenv disabled, model/network mocked | 190 tests OK; includes auth matrix, gateway and dispatch negatives. Unit/mock/local fixture evidence, not live model or Bench proof. |
| `node frappe_app/public/js/copilot.bundle.test.js` | 64 checks pass: 26 preview + 38 Desk, stub-DOM/fetch fixtures only. |
| Syntax checks | Reported pass, including bundle syntax; not lint/typecheck. |
| Strict OpenSpec validation and `git diff --check` | Reported pass; structural/documentary checks, not final implementation/security acceptance. |
| Preliminary system `python3` run | 13 import failures with the wrong interpreter; superseded by successful project `.venv` discovery, not hidden or counted as runtime defects. |

Artifacts are the supplied execution report and inspected test sources:
`tests/test_service_auth.py`, `tests/test_chat_boundary.py`,
`tests/test_frappe_gateway.py`, and the Node harness. No new result artifact
or runtime run was created here. Source/test review supports rollback only
by retaining authentication/chat-only enforcement or disabling Desk chat;
synthetic key mismatch and sanitized gateway failures are not a deployed
rotation or rollback exercise.

Latest parent-reported evidence, 2026-09-17: strict validation before runtime
implementation was independently confirmed (task 1.1 checked). Final read-only
security review found no blocking finding. OpenSpec verification mapped
18 requirements and 51 scenarios, retaining incomplete-acceptance warnings.
These bounded reviews are complete, not overall acceptance.

The last clarification/out-of-scope wording warning was fixed with
scope-aware guidance (`orchestrator.py:366`, `:382`, `:406`) and the additional
`tests/test_chat_boundary.py:236` regression test. The parent reports the full
project `.venv` rerun exited OK after that fix and the Node harness passed.
This continuation records a full rerun passed after the additional wording
test, without inferring an exact executed test count from source. The
190 Python / 64 Node counts above remain the historical first full pass.
No runtime suite was rerun by this documentation continuation.

User-supplied 2026-09-17 acceptance-session evidence (this pass reran
nothing): offline command `PYTHON_DOTENV_DISABLED=1 HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1 LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python
-m unittest discover -s tests` returned **191 tests OK in 1.628s**, with a
Starlette/httpx deprecation warning and no dependency changes. The Node
harness passed 64 checks (26 preview + 38 Desk); `node --check` passed for
both bundle and test harness. The user-supplied tooling inspection covered
root/nested pyproject/package metadata, Makefiles, tasks, CI, scripts and
documentation: Python lint/typecheck and JavaScript lint/typecheck are each
**not configured**; nested `frappe_app/pyproject.toml` is packaging only,
and `.opencode` package dependencies are agent tooling, not application
lint/typecheck tooling. Per explicit user acceptance, task 6.1 is complete
on this not-configured basis — reported as not configured, not passed.
Syntax checks are not lint/typecheck. Do not invent or install a tooling
stack for this acceptance.

User-supplied 2026-09-17 Bench-environment inspection: a Bench exists at
`/home/passenger/projects/frappe_docker/development/frappe-bench` with apps
`crm`, `erpnext`, `frappe`, `hrms` and `sites/development.localhost`, but no
`erpnext_ai_copilot` app directory. `bench`, `chromium` and `google-chrome`
were absent from PATH; `ss` showed only DNS listeners, not app listeners;
the bounded no-proxy curl to `http://127.0.0.1:8081` returned exit 7,
connection refused, HTTP 000. `docker ps`/`version`/`compose` could not
execute `/usr/bin/docker` (Input/output error), so container status cannot
be determined from that CLI — this is not evidence of no containers
globally. No install, start, configuration, migration, login, browser,
model or ERP-data action was performed. Task 6.3 therefore remains
unchecked: all real authentication/CSRF, Desk actions, assets, preview and
minimal-health integration checks are unverified; synthetic tests do not
substitute. In the same session the operator shell read the adjacent
`frappe_docker` `.env` through name-filtered output; nonsecret values were
visible and are not reproduced, and the target repository's actual `.env`
was not read. No credentials were used or changed.

Security status: the prior read-only security review found no blocking
finding and is not rerun; the latest independent final scope review found
no out-of-scope runtime/dependency work. Tasks 6.1 and 7.3 are closed by
explicit user authorization in this acceptance session. Task 7.3 is the
authorized handoff ONLY — it creates and implements nothing. The next
milestone requires the separately approved `frappe-owned-conversation-state`
change: Frappe-owned persistent records, authenticated user ownership, site
association, persistence across inference restarts, removal of
caller-controlled session ownership and the JSON store, and an explicit
migration/compatibility strategy. Task status: **20/21 complete; only 6.3
remains open** (unverified real Bench/Desk integration). This handoff is
not full G2/M2, production readiness, owned state, ACL isolation,
release/production-write approval or private-data cloud consent. No live
model/network/test/deployment calls, data mutation, staging, commit or
archive occurred in this documentation pass.

Historical reconciliation was archived under
`openspec/changes/archive/2026-09-17-reconcile-architecture-and-production-hld/`
in commit `10d6c8e`. Earlier unarchived/uncommitted statements below describe
that earlier handoff, not the active boundary. Pre-existing CURRENT evidence
and the September 9 JOURNAL recovery are retained. The prior conversational
redesign (`a7676ec`) used mocked NLU; its full live NLU matrix remains
incomplete and its historical provider outage is not today's health.

## 2026-09-17 documentation reconciliation (Tasks 4.1/4.2) — status and corrections

Docs-only, source-read-only pass under the approved change
`reconcile-architecture-and-production-hld`. No runtime, test, model-call,
network or data activity. At this handoff, independent review (Tasks 5.x)
was pending; it is now complete as recorded in the final acceptance journal entry.
Historical evidence below is retained, with obsolete current-state summaries
corrected and historical limitations annotated. Phase 1–8 tables and checked
DoD items report 2026-08-24 acceptance, not fresh verification. Source basis:
working-tree HLD/ROADMAP/EVALUATION at HEAD a7676ec plus uncommitted
reconciliation; no runtime artifact was regenerated. Per those documents:

- **Live NLU acceptance remains incomplete.** The 29-case routing eval
  used MOCKED NLU; sessions 18–19 report unit/mock Python and stub-DOM
  Node checks (latest aggregate 145 Python + 26 Node, recorded by the
  2026-09-09 status update) and only limited live checks. The full live
  conversational/NLU matrix required by
  `EVALUATION.md` (exact fast paths, non-exact conversation, capability,
  clarify, out-of-scope, troubleshoot, all three task routes, follow-ups,
  mode restrictions, provider timeout/invalid-output paths) has never been
  run live. Session 18's Ollama unreachability is a dated 2026-09-08-era
  observation, NOT a current connectivity measurement.
- **"Troubleshoot route" is shorthand, not architecture.** Troubleshoot is
  an NLU kind (`orchestrator.py:174`), not an eighth response route; the
  seven routes are erpnext/code/rag/smalltalk/capability/clarify/
  out_of_scope (`service/main.py:224`).
- **"BM25 can never drift" was inaccurate.** The lexical snapshot is taken
  once per process (`rag/keyword_index.py:209`) and is not refreshed after
  later ingestion/resolution insertions, so it can go stale relative to the
  vector store; global corpus statistics also feed the confidence gates.
- **RAGAS causality wording corrected.** The 0.992→0.734 faithfulness
  comparison mixes changed valid-row coverage (12→8) with a self-judge; it
  can be neither dismissed as harmless judge noise nor read alone as a
  grounding regression. Means are reported with valid-row counts and
  self-judge limitations; independent judging and per-question review are
  the future evidence requirement (`EVALUATION.md`).
- **Bench/Docker/UI status.** All sidebar/UI verification to date is
  standalone-preview plus stub-DOM harness work on this box. Real Bench
  installation, packaged-asset injection and Desk behavior are unverified;
  Docker is planned, not delivered. "Testable in-browser" always meant the
  service-served `/ui` preview, not Desk. Live API/ERPNext tests
  (2026-08-24) are not Bench deployment evidence.
- **Counts and versions are dated.** Corpus counts (1,000 pages cached,
  7,410 public / +321 project chunks) and Frappe 16.31.0 / ERPNext 16.32.3
  describe the 2026-08-24-era runs, not current inventory or connectivity.
- **Direction vs choice vs consent.** The user-approved 2026-09-17
  production direction (authenticated Frappe control plane + separate
  private inference) is recorded in `DECISIONS.md`; it selects no tenancy,
  executor, protocol or ACL implementation, grants no production-write
  approval and no private-data cloud consent.

## Session 13 — UI completion (docs/UI_SPEC.md)

> 2026-09-17 annotation: dated 2026-08-24 record. "Testable in a browser"
> meant this box's standalone `/ui` preview served by the service; "same
> bundle a bench injects" describes source identity of the asset file, not
> verified Bench packaging. Real Desk injection, transcript restoration,
> streaming/realtime remain unverified target work (ARCHITECTURE.md). The
> Session 15 rebuild to `docs/UI_VISUAL_SPEC_updated.md` (canonical blue)
> supersedes the visual direction of this era.

The Phase-1 sidebar was rebuilt as a self-contained vanilla-JS bundle:
slide-out resizable right panel with header (mode switch developer/
employee, start-fresh, close), markdown answers with fenced-code copy
buttons, citation pills that flash their source row, subtle high-
confidence badge vs prominent amber/red callouts for low/no_match,
typing indicator, service-unreachable banner, empty state with
suggestion chips, Enter/Shift+Enter + autofocus, session continuity via
localStorage + POST /tools/session/reset, route badges and live-version
footer per answer, and inline APPROVAL CARDS: /edit renders the unified
diff with Approve&Commit/Reject (Tier-2), /newdoc//editdoc render exact
ERPNext write previews with the same two-button flow (Tier-2-for-data).
Slash commands expose every tool (/read /search /explain).

Standalone preview served by the service itself at **GET /ui/preview.html**
(same bundle a bench injects), so the entire system is testable in a
browser on this box. Bench-only leftover: verifying injection inside a
real Desk (`app_include_js` + boot settings).

## Phase 7 closure note (2026-08-24)

Phase 7 accepted via user instruction to proceed (commit c7b8267); live
matrix below.

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
- **RAGAS re-score post-hybrid-retrieval** — RECOVERED 2026-09-09: the
  scoring phase had in fact COMPLETED on 2026-09-08
  (`data/ragas_baseline_2026-08-24T11:32:30Z_124955.json`, verified
  against the samples file row-by-row: questions, answers, contexts,
  references all match). It was never logged — CURRENT.md still said
  "aborted mid-run". Judge = same local qwen2.5-coder:7b, embeddings =
  bge-small. The 2026-08-23 pre-hybrid table is kept below for
  comparison; the post-hybrid table is now the recorded baseline.

## RAGAS baseline (EVALUATION.md requirement)

Scored 2026-09-08 on the post-hybrid 2026-08-24 samples (hybrid retrieval +
grounding net + confidence gates), judge = same local
qwen2.5-coder:7b that generates (self-judging approximation), embeddings =
bge-small. Samples: `data/ragas_samples_2026-08-24T11:32:30Z.json`; results:
`data/ragas_baseline_2026-08-24T11:32:30Z_124955.json` (recomputed + verified
row-by-row against samples 2026-09-09; means match stored values exactly).

| Metric | Score | Notes |
|---|---|---|
| Faithfulness | **0.734** | 8/15 valid; 7 NaNs reported as judge parse failures, not zero scores. Pre-hybrid 0.992 had 12/15 valid. Changed coverage and self-judging prevent causal attribution; Q3/Q7/Q11 lows require review, not dismissal as noise. |
| Answer relevancy | **0.939** | 11/15 valid versus pre-hybrid 0.941 (15/15); similar means do not establish unchanged quality. |
| Context precision | **0.564** | 9/15 valid versus pre-hybrid 0.562 (15/15); changed coverage limits comparison. |

2026-09-17 interpretation correction: the earlier claim that the faithfulness
change reflected judge failures rather than worse grounding was unsupported.
Neither harmless judge noise nor a regression is established by these means.
Independent judging, per-question source review and held-out cases remain
pending. The recovered results and dates are retained; no rerun occurred.

Pre-hybrid baseline for comparison (scored 2026-08-23, samples
`data/ragas_samples_2026-08-23T09:04:28Z.json`, results
`data/ragas_baseline_2026-08-23T09:04:28Z_094756.json`): faithfulness
0.992 (12/15 valid), answer relevancy 0.941 (15/15), context precision
0.562 (15/15).

Harness lives in `evaluation/` (two-phase: generate in main venv, score in
`.venv-eval` Python 3.12 — ragas 0.2.x is incompatible with this machine's
Python 3.14 asyncio). Setup commands in README "Evaluate".

## Hybrid retrieval (2026-08-24) — what changed and why

Root fix for the verification-run regressions (see DECISIONS.md
[2026-08-24]):

- **`rag/keyword_index.py`** — in-house Okapi BM25 over the same Chroma
  collection (no new dependency); lazy snapshot once per process. The old
  "can never drift" claim is corrected as of 2026-09-17: subsequent index
  mutations do not refresh that snapshot (`rag/keyword_index.py:209`).
  Tokenizer folds plural/-ing/-ed/final-e suffixes identically on queries
  and corpus.
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

## Historical Phase 1 implementation and verification (2026-08-24)

2026-09-17 context: the inventory below describes that acceptance run, not
current service health, corpus counts or UI delivery. Later phases and UI
sessions supersede this minimal sidebar. Version-subtree exclusion does not
prove exact installed-v16 compatibility; citation/identifier repair does not
prove semantic grounding. Localhost binding is an operating requirement,
not authentication or a source-established measurement of today's bind.

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

## Remaining observations and next gate (2026-09-17)

- Documentation reconciliation is COMPLETE as a documentary unit (2026-09-17):
  independent read-only content review (architecture + fresh review after a
  prior reviewer's /tmp write disclosure) and security review found no
  blocking documentation findings; strict OpenSpec change validation and
  `git diff --check` pass. This is documentary acceptance only — it passes
  no runtime gate. The change is NOT archived and NOT committed; ADRs, task
  checkboxes and this file were updated by the parent after the review pass.
- Full live NLU acceptance, real Bench installation/assets/Desk behavior and
  Docker parity remain outstanding. Historical lack of Bench on this box
  is not a new environment measurement or absence of the staging API.
- The post-hybrid RAGAS recovery is recorded, not pending a first score.
  Independent judging and per-question review, including Q3/Q7/Q11 lows
  and Q2/Q15 content imperfections, remain quality-evidence gaps. A stronger
  judge alone would not establish causality or production acceptance.
- Earlier "not started" references to ERPNext reads, orchestration and
  employee mode were obsolete: Phases 5–7 implemented them and were
  historically accepted 2026-08-24, with the HLD's authorization limits.
- Versioned-subtree exclusion and the dated v13 purge do not establish a
  present corpus inventory or exact v16 compatibility. Public rebuilds can
  remove unrelated corpora; lexical snapshots and current-code chunks can
  become stale (ARCHITECTURE.md, "Known index lifecycle gaps"). No reindex
  or runtime remediation is authorized by this work.
- Production writes remain unapproved under SECURITY.md; staging gating and
  individual confirmation remain mandatory. No live flag/configuration was
  inspected. Future implementation requires separately approved changes and
  decisions in DECISIONS.md, not historical phase completion.
- Historical housekeeping: Phase 8 reported two labeled staging test
  Customers. Their current existence is unmeasured; no deletion or other
  data action is part of this change. The product has no delete operation.

See progress/BLOCKERS.md for pending review and future decision gates.

## Phase 8 — Write-capable ERPNext Agent: what changed

- **`tools/erpnext_write.py`** — SEPARATE module from the read client
  (which stays GET-only by construction). Writes exist only behind
  `ERPNEXT_WRITE_ENABLED=true` (.env), checked at propose AND apply.
- **Tier-2 discipline**: propose returns an EXACT preview (HTTP method +
  URL + JSON body) and applies nothing; apply requires explicit
  `confirmed:true`; proposals one-shot with TTL.
- **Pre-flight schema validation**: fieldnames not present on the target
  DocType are refused before any HTTP call (live-proven with a typo'd
  field).
- **Create/Update only; DELETE does not exist** in the module (test-
  asserted). Every applied write appended to
  `data/erpnext_writes.jsonl` with env label, reason, payload keys.
- **Endpoints**: POST /tools/erpnext_write/propose|apply with clean
  refusal mapping (403 flag / 400 confirm+fields+payload / 404 doctype /
  410 expired).
- Multi-step actions = sequential individually-confirmed proposals;
  silent chaining is structurally impossible.

## Phase 8 verification (live staging instance localhost:8081)

| Check | Result |
|---|---|
| Master gate | flag off -> 403 writes_disabled (proven before enabling) |
| Create | propose preview -> confirm -> Customer created live, name returned, audited |
| Server-validation honesty | group-type customer_group rejected BY FRAPPE; exact server message surfaced loudly |
| Update | rename applied live; read-back via our read tool confirms |
| Confirmation gate | confirmed=false -> 400 refusal |
| Schema preflight | typo'd fieldname refused 400 BEFORE any HTTP call |
| Audit log | both writes present with env_label=staging, reasons, payload keys |
| Tests | 88/88 unittest green (11 new guarded-write cases) |

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
  knowledge). This records the 2026-08-24 three-way task router, not the
  later full conversational flow. Correction dated 2026-09-17: task-router
  classifier failure defaults to RAG (`orchestrator.py:498`); failed NLU
  uses strong task heuristics or clarification (`orchestrator.py:769`).
  "ANY failure defaults to rag" was not a universal fallback guarantee.
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
