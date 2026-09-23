## Why

The authorized live 29-case re-run of commit `9f274ed` (model `qwen2.5-coder:7b`, digest `dae161e27b0e`, staging/local-only; raw results `/tmp/live29/live29_raw.json`) fixed 3/4 M7 defects but surfaced three regressions, all with safe failure modes except one: `knowledge-journal` flipped RAG→clarify, `followup-purchase` moved ERPNext→clarify instead of RAG, and the dead-port probe now escapes an uncaught provider exception through RAG generation. Overall 26/29 with no readiness, write, or cloud implications. This change corrects exactly those three demonstrated issues with generalized rules — no architecture, governance, or scope change.

## What Changes

- **Complete-question backstop + narrowed NLU wording (knowledge-journal):** a deterministic syntactic rule routes complete interrogative questions to the normal task pipeline even when NLU says `clarify` (existing confidence and retrieval gates still apply); the NLU prompt's bare-noun language is narrowed to single-token/verbless fragments and loses the noun-topic examples suspected of over-attracting `clarify` verdicts. Bare fragments ("payments", "purchase invoices") still clarify through both the NLU and guard paths.
- **Clarify-with-history condensation (followup-purchase):** an NLU-`clarify` verdict over an elliptical continuation ("what about X?") with non-empty history attempts the existing condenser and routes the rewrite through the normal task pipeline; condensation failure (or no history) clarifies exactly as today. Explicit live-data follow-ups ("what about Purchase Invoice status?") reach ERPNext only via the unchanged explicit-signal precedence on the condensed question.
- **Degraded-path provider containment (dead-port probe):** the NLU-down degraded branch again proceeds only on `erpnext`/`code` heuristic hits and clarifies otherwise — the new how-to `rag` arm no longer routes into provider-dependent generation when classification itself has failed. Model-present routing keeps the arm unchanged.

## Capabilities

### New Capabilities

(none — corrections restore intended behavior already pinned by the existing evaluation contract; no new behavior is introduced.)

### Modified Capabilities

(none — no existing `openspec/specs/` capability covers NLU/task-router precision semantics; gateway/boundary specs are untouched. Per the artifact instructions, no requirement is invented to satisfy validation: this change sets `skip_specs: true` in `.openspec.yaml`.)

Behavioral contract (pre-existing, not invented here):

- `evaluation/routing_cases.json` (unmodified): the 29 expectations, including `followup-purchase`→rag.
- `/tmp/live29/live29_raw.json` + `probes_raw.json` + `manifest.json`: the 26/29 result, the three regressions, and the dead-port uncaught `APIConnectionError` via `generate_answer`.
- `openspec/changes/fix-routing-precision-after-m7/`: the prior fix whose successes (code-location, bare-fragment boundary, explicit live-data signals, how-to arm, contamination protection) must not regress.

## Impact

- **Would edit on implementation:** `orchestrator.py` only (NLU prompt wording, two small clarify-dispatch predicates, one degraded-branch condition).
- **Would edit for proof:** routing tests (`tests/test_conversation.py` degraded/clarify classes and/or a new regression test file); `evaluation/routing_cases.json` left untouched.
- **Untouched:** `service/`, `rag/`, `tools/`, `config.py` (no thresholds), `frappe_app/`, specs, `.env`, data/indexes, tenancy/ACL/deployment/packaging, write paths, providers/models, M7 archives, `origin/main`.
- **Not in this change:** the live 29-case re-run (separate explicit checkpoint later).
