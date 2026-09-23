# Tasks: fix-post-live-routing-regressions

Planning only — no implementation started. Each task states its verification inline. The live 29-case re-run is explicitly NOT part of this change (later checkpoint).

## 1. Failing-first regression tests (no source changes yet)

- [x] 1.1 Add complete-interrogative tests: with NLU mocked as `clarify` (confidence 0.9, topic set), `handle_question` on "what is a journal entry?", "What is a sales invoice?", "How does purchase invoice work?" reaches the task pipeline (mocked classifier → `rag`, retrieval mocked high) instead of short-circuiting to `clarify`, and verify all three FAIL against the unmodified code while "payments", "purchase invoices", "invoices??", and "Something vague" with NLU `clarify` still return `clarify` in the same run (overcorrection guards).
- [x] 1.2 Add clarify-with-history condensation tests: with NLU mocked as `clarify` plus `context_dependency: follows_topic` and the Sales-Invoice how-to history, `handle_question("what about purchase invoices?")` with `condense_followup` mocked to "How do I create a Purchase Invoice?" routes `rag` with ERPNext tools asserting silence; with `condense_followup` mocked to `None` it returns `clarify`; with no history it returns `clarify` without calling the condenser; and verify the `rag` case FAILS against the unmodified code.
- [x] 1.3 Add the explicit-signal follow-up leg: same setup as 1.2 but `condense_followup` mocked to "What is the status of Purchase Invoice?" routes `erpnext` (extraction mocked, no real transport), and verify it FAILS against the unmodified code (which clarifies before condensation); plus a new-topic control reusing the existing `test_self_contained_question_never_condenses` shape ("How do I submit a Purchase Order?" + unrelated history never calls the condenser).
- [x] 1.4 Extend `DegradedNluTest` (do not fork a parallel harness): with `generator._complete` raising (provider down) and `generate_answer` mocked to raise if called, `handle_question("How do I create a Sales Invoice?")` returns `clarify` with `route_how == "degraded"` and no exception escapes, and verify it FAILS against the unmodified code (uncaught `APIConnectionError`-class error today); existing degraded code-signal/no-signal/timeout tests must pass unchanged before and after.

## 2. Deterministic corrections (implementation, `orchestrator.py` only)

- [x] 2.1 Narrow the `_NLU_PROMPT` clarify bullet to single bare words / short verbless fragments with no question structure, removing the noun-topic examples and the absolute "never task" sentence, and verify by wording review that no business-noun example remains while the HOW-TO/LIVE/CODE guidance is untouched.
- [x] 2.2 Implement the complete-interrogative backstop in the `kind == "clarify"` dispatch (leading interrogative/auxiliary + auxiliary verb present + more than two tokens → fall through to the task pipeline with verdict confidence intact), and verify task 1.1 now passes with no noun list, no DocType literal, and no change to non-interrogative clarify behavior.
- [x] 2.3 Implement clarify-with-history condensation (elliptical continuation shape + non-empty history → attempt `condense_followup`; non-empty rewrite enters the normal task pipeline with the confidence gate applied; failure or no history clarifies as today), and verify tasks 1.2–1.3 now pass while bare-without-history inputs still clarify immediately.
- [x] 2.4 Restrict the degraded branch to `erpnext`/`code` heuristic hits (`"rag"` treated as non-proceeding → `_clarify_result(degraded)`), leaving model-present `decide_route` untouched, and verify task 1.4 now passes with existing degraded expectations byte-identical.

## 3. Offline verification and scope audit (no new behavior)

- [x] 3.1 Run the full offline suite (`python -m unittest discover -s tests`) plus the `node` harness and `node --check` on the bundle, and verify zero regressions versus the `9f274ed` baseline (record counts; `test_routing_eval` dataset green with `evaluation/routing_cases.json` unmodified).
- [x] 3.2 Audit the diff for scope compliance (only `orchestrator.py` + routing tests changed; no `service/`, `rag/`, `tools/`, `config.py`, `frappe_app/`, specs, `.env`, index, tenancy, ACL, deployment, packaging, write-path, or M7-archive files; no `~/projects/frappe_docker` access at any point) via `git status --short` and `git diff --stat`, and verify `git diff --check` is clean with no commit created.
- [x] 3.3 Confirm prompt-wording review is recorded, the deferred live 29-case re-run is handed off as a separately-authorized checkpoint, and no live model/service call occurred in planning or implementation beyond the authorized offline suite (which mocks all transports).

## Closure evidence — authorized live validation 2026-09-23 (commit `ee8b0de`)

- Model `qwen2.5-coder:7b` digest `dae161e27b0e` at `http://172.30.224.1:11434`; dataset `evaluation/routing_cases.json` unmodified; staging ERPNext unreachable (read branch to lookup-failure only, not a routing failure).
- Result **28/29, 0 harness errors**: `knowledge-journal`→RAG, `followup-purchase`→RAG, dead-port probe→safe `clarify`/`degraded` with no exception; `code-where`/`ambiguous-payments`/`contam-newtopic` fixes intact; employee probes 2/2 pass.
- Sole non-pass: `bye` ("see you later", two unparseable NLU outputs → safe degraded clarify; model-output variance across three runs, not a demonstrated routing regression; not relabeled fixed).
- This record is routing evidence only: no production-readiness, write, cloud, U/O, or threshold implication; M7 remains authoritative. Raw artifacts: `/tmp/live29/live29_ee8b0de.json`, `probes_ee8b0de.json`, `manifest_ee8b0de.json` (outside the repo by procedure).
