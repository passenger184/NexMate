## Why

The authoritative M7 model-present live NLU matrix (29 cases, `qwen2.5-coder:7b`) passed 25/29 with 4 genuine route mismatches kept as findings (`m7-review-report.md:18`, `tasks.md` 3.2). Three of the four over-route into ERPNext on business-document nouns ("purchase invoices", "payments", "Purchase Order"); the fourth misroutes an implementation-location question to RAG. This change fixes those four demonstrated defects with generalized routing signals — no architecture, governance, or scope change.

## What Changes

- **Generalized code-location signal:** `_CODE_HINTS` / `_heuristic_route` (`orchestrator.py:479-504`) recognize implementation-location phrasing ("where is X implemented", "which file/function implements X") instead of only the literal "where is it implemented", so `code-where` routes `code` deterministically.
- **How-to vs live-data boundary:** a deterministic how-to arm in the task router sends process questions ("How do I create/submit a Purchase Invoice/Order?") to `rag`, reserving `erpnext` for questions carrying live-data markers (counts, statuses, lists, field values, schema). Fixes `followup-purchase` (post-condensation) and `contam-newtopic`.
- **Bare-noun clarify boundary:** NLU still produces its normal kind/verdict, but for a `task` verdict over a single-token / verbless-fragment input, a deterministic guard overrides to `clarify` before condensation, heuristic routing, classifier fallback, extraction, retrieval, or tools. Fixes `ambiguous-payments` ("payments"): insufficient task fragments never reach downstream routing, while existing NLU boundary/telemetry behavior is preserved.
- **Prompt reinforcement (supporting only):** `_NLU_PROMPT` (`orchestrator.py:190`) and `_CLASSIFIER_PROMPT` (`orchestrator.py:523`) state the same four-way semantic boundary (HOW-TO→rag, LIVE-DATA→erpnext, CODE→code, BARE→clarify) so live-model behavior aligns with the deterministic layer. Offline proof rests on the deterministic layer, not prompt text.
- **Regression tests** that replay the live-observed wrong verdicts and fail before / pass after the fix, plus paraphrase variants proving no exact-string special-casing.

## Capabilities

### New Capabilities

(none — no new behavior is introduced; this restores the routes already pinned by the existing evaluation contract.)

### Modified Capabilities

(none — no existing `openspec/specs/` capability covers NLU/task-router precision semantics; gateway/boundary aspects of routing are already specified in `frappe-api-gateway` and `endpoint-access-control` and are unchanged. Per the artifact instructions, no requirement is invented to satisfy validation: this change sets `skip_specs: true` in `.openspec.yaml`.)

Behavioral contract (pre-existing, not invented here):

- `evaluation/routing_cases.json`: `code-where`→code, `followup-purchase`→rag, `ambiguous-payments`→clarify, `contam-newtopic`→rag.
- `openspec/changes/archive/2026-09-20-production-readiness-decision/tasks.md` 3.2 + `m7-review-report.md:18`: authoritative live expectations and observed deviations.

## Impact

- **Edited on implementation:** `orchestrator.py` only (hints/patterns, router precedence, NLU + classifier prompt wording, one small deterministic clarify guard).
- **Edited for proof:** routing regression tests (`tests/test_orchestrator.py` and/or a new `tests/test_routing_precision.py`); `evaluation/routing_cases.json` left untouched to preserve the M7 baseline.
- **Untouched:** `service/`, `rag/`, `tools/`, `config.py` (no threshold change), `frappe_app/`, specs, `.env`, data/indexes, tenancy/ACL/deployment/packaging, write paths, providers/models.
- **Not run in this change:** the live 29-case re-evaluation (separate explicit checkpoint later).
