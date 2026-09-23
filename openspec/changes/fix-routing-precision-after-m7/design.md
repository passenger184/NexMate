# Design: fix-routing-precision-after-m7

## Context

See `proposal.md` — Why. Current pipeline (`orchestrator.py`): Layer 1 exact fast-path (`_EXACT_CONVERSATIONAL`, `orchestrator.py:172`) → Layer 2 NLU (`_understand_with_llm`, `orchestrator.py:226`, kinds at `:186`) with `NLU_MIN_CONFIDENCE=0.5` (`config.py:79`) → task branch with follow-up condensation (`orchestrator.py:857-871`, `rag/generator.py:163`) → `decide_route` (`orchestrator.py:507`): `_heuristic_route` (`:487`) → `_classify_with_llm` (`:537`) → default `rag`. Degraded NLU reuses `_heuristic_route` only (`:822-831`).

Root causes (all signal/prompt gaps, not architecture):

1. `code-where`: `_CODE_HINTS` holds the over-specific literal `"where is it implemented"` (`:482`). "where is Sales Invoice implemented" scores code 0 / erp 0 → heuristic abstains → live classifier, whose prompt describes `code` only as "about THIS project repository's own source code" with no implementation-location signals, chose `rag`.
2. `followup-purchase` / `contam-newtopic`: condensed or direct how-to questions ("How do I create a Purchase Invoice?", "How do I submit a Purchase Order?") carry no `_ERPNEXT_HINTS` marker, so the heuristic abstains and the live classifier maps bare DocType nouns ("Purchase Invoice/Order", "submit") to `erpnext`. The classifier prompt never states that how-to/process framing means `rag`.
3. `ambiguous-payments`: "payments" is a bare topic word that `_NLU_PROMPT` (`:202`) nominally assigns to `clarify`, but the live model returned `task`, and the classifier then mapped the noun to `erpnext`. No deterministic layer owns this boundary today.

## Goals / Non-Goals

**Goals:** the four canonical cases plus paraphrase variants route correctly through generalized signals with explicit precedence; every new test fails on current code and passes after; `heuristic → classifier → default RAG` shape preserved.

**Non-Goals:** no new router/agent/model/provider; no orchestrator redesign; no U1–U10 / O2–O4 resolution; no threshold, readiness, write, consent, RAG, MCP, Workbench, tenancy, ACL, deployment, or packaging change. `evaluation/routing_cases.json` is not edited (M7 baseline comparability). The live 29-case re-run is a later checkpoint, not part of this change.

## Decisions

- **D1 — Fix in `orchestrator.py` signals + prompts only.** Rationale: all four defects trace to missing/over-narrow signals, and the deterministic layer already owns precedence ("Deterministic overrides first", `orchestrator.py:12-15`). Alternative (new router stage or model): rejected as redesign, explicitly out of scope.
- **D2 — Generalize, never string-match the four cases.** Code-location becomes a pattern family (where/which-file/which-function + implement*), not the literal "where is it implemented". How-to becomes a framing rule (how-do-I/how-to + absence of live-data markers → `rag`), tested with paraphrases across DocTypes (e.g. "Where is Purchase Invoice implemented?", "How do I configure a Payment Entry?"). Bare-noun clarify becomes a shape rule (single token / verbless fragment, not exact-conversational → `clarify`), not a "payments" special case. Alternative (four literals): rejected — brittle and explicitly forbidden by the request.
- **D3 — Explicit precedence ordering.** Order of evaluation: (1) exact fast-path (unchanged); (2) NLU kind dispatch (unchanged, prompt reinforced); (3) for `task` verdicts only, the bare-noun guard — a short verbless fragment clarifies immediately; (4) task-router heuristic with arms evaluated live-data → code → how-to-rag (new `rag` arm fires only when no live-data/code signal fired, so "how many users…" and "what fields does X have" still reach `erpnext`); (5) LLM classifier (prompt reinforced with the same boundary + negative examples: DocType noun alone is not a live-data signal; "submit" without status/count/list markers is how-to); (6) default `rag` (unchanged). Refinement found during implementation: the guard refines `task` verdicts instead of sitting literally before the NLU call — a pre-NLU position would intercept scripted conversational/capability/scope verdicts (proven by the `test_chat_boundary.py` NLU-kind matrix on the 2-token probe "Something vague") and shadow degraded-path telemetry. The safety property is unchanged: bare inputs clarify before condensation, heuristic, classifier, extraction, retrieval, or any tool. Alternative (prompt-only fix): rejected as primary — unprovable offline; prompts are supporting reinforcement, verified later live.
- **D4 — Offline proof via replayed live verdicts.** The key test technique: mock `generator._complete` to return the exact live-observed wrong classifier verdict (e.g. `{"route": "erpnext"}`) while exercising the REAL `_heuristic_route`/`decide_route` (no `decide_route` mock — unlike `tests/test_routing_eval.py:111-114`, which scripts it). Before the fix the wrong verdict flows through; after, the deterministic arm preempts it (`route_how == "heuristic"`). For `ambiguous-payments`, mock NLU as `task` (replaying the live misclassification) and assert the guard short-circuits to `clarify` before the mock matters. Alternative (live-model tests now): rejected — forbidden until the later checkpoint.
- **D5 — Degraded path inherits the `rag` arm.** `_heuristic_route` returning `rag` means NLU-down how-to questions degrade to confidence-gated read-only RAG instead of safe clarification. Acceptable: RAG is read-only with its own `high`-only generation gate (`orchestrator.py:959-971`), strictly safer than a tool path. Alternative (restrict degraded to erpnext/code): rejected — it would keep the current worse behavior of clarifying answerable docs questions during outages; recorded here so reviewers see the deliberate choice.
- **D6 — No `config.py` changes.** `NLU_MIN_CONFIDENCE` (0.5) and hint tuples stay configured where they are; new patterns live beside the existing hint tuples. Threshold tuning is not part of a precision fix.

## Risks / Trade-offs

- [Risk] How-to arm steals genuine live-data how-tos ("How do I check my outstanding invoices?") → Mitigation: boundary semantics say how-to framing IS a docs answer (UI steps), and any explicit live-data marker (how many/list/status/count/schema/fields) still wins by precedence; cover both directions in tests.
- [Risk] Code-location pattern over-fires on conceptual questions ("How is a DocType implemented in Frappe?") → Mitigation: pattern requires location interrogatives (where/which file/which function), not "how"; negative test included.
- [Risk] Bare-noun guard clarifies a legitimate one-word probe (e.g. "pathsafe") → Mitigation: the guard applies only to `task` verdicts over short fragments with no interrogative, auxiliary, or intent verb; clarification is the safe failure mode for a genuinely ambiguous single token, which carries no actionable intent on its own.
- [Risk] Prompt wording drifts from deterministic rules → Mitigation: prompts restate the same four-way boundary (HOW-TO→rag / LIVE-DATA→erpnext / CODE→code / BARE→clarify); deterministic tests, not prompt-text assertions, are the proof.

## Migration Plan

None — behavior-only change behind existing routes. Rollback is the pre-change tree. No data, index, config, or deployment migration. Offline suite (`python -m unittest discover -s tests`), `node` harness untouched, `git diff --check` confirm no out-of-scope files.

## Open Questions

None — the four expectations are pinned by `evaluation/routing_cases.json` and the M7 report; precedence above resolves the rest without new requirements.
