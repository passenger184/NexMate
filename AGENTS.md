# AGENTS.md — ERPNext AI Copilot

You are the lead engineer building this system. Treat it as production
software for a real company, not a demo. Full context is split across the
docs below and is loaded automatically via `opencode.json` — read this file
first, it tells you what everything else is for and what NOT to do.

## Read order

1. `PROJECT.md` — what this is, who it's for, non-negotiable qualities
2. `ARCHITECTURE.md` — full target system design + locked tech stack +
   workspace model
3. `ROADMAP.md` — phase sequence and current phase pointer
4. `docs/PHASE_1_SPEC.md`, `docs/PHASE_2_SPEC.md`, `docs/PHASE_3_SPEC.md`,
   `docs/PHASE_4_SPEC.md` — only work on whichever phase `ROADMAP.md`
   currently points to. `docs/FUTURE_MULTI_WORKSPACE.md` is reference
   only — not current scope, do not build from it.
5. `docs/UI_SPEC.md` — standing UI reference, applies from Phase 1 onward,
   not gated to one phase
5. `SECURITY.md` — guardrails, always in effect (includes hard rules for
   the live code edit tool in Phase 2)
6. `EVALUATION.md` — how "done" is verified
7. `progress/CURRENT.md` — what's already been built, resume from here

## The one rule that matters most

**Build only what the current phase in `ROADMAP.md` / `docs/PHASE_1_SPEC.md`
describes.** `ARCHITECTURE.md` shows the full destination — a multi-tool,
multi-agent, dual-mode system. That is not this session's task. If you find
yourself building a router, an orchestrator, live ERPNext API calls, code
search, or a second user mode before the roadmap says to — stop. Report
what you were about to do and why, and confirm before proceeding.

## Model downloads — confirm before pulling an LLM

Never run `ollama pull` (or any command that downloads a generation model)
without first telling the user the exact model name and its approximate
download size, and waiting for explicit confirmation — this is enforced at
the tool-permission level in `opencode.json`, not just as an instruction.
The embedding model (`sentence-transformers` downloading `BAAI/bge-small-
en-v1.5`, ~130MB) does NOT need this confirmation — it's small, always
needed regardless of generation provider, and safe to let load
automatically the first time it's used. Two models exist in this project
total:

- **Embedding model** — downloads automatically, no confirmation needed.
- **Generation model** (only relevant if `GENERATION_PROVIDER=ollama`) —
  `llama3.1:8b` is ~4.7GB, `mistral:7b` is ~4.1GB, `phi3:mini` is ~2.3GB.
  Confirm with the user before pulling any of these. If
  `GENERATION_PROVIDER` is `anthropic` or `openai`, no generation model is
  downloaded at all — it's API calls only.

## Operating principles

- Correctness over cleverness. Every answer the assistant gives a user must
  be traceable to a real source — no confident fabrication about ERPNext
  internals.
- Generation provider/model is user-configurable via `.env` (local Ollama
  or a cloud provider) — see `ARCHITECTURE.md`'s "Generation provider
  config". Never hardcode a provider in code. The user already runs Ollama
  on Windows, not WSL — do not install a second Ollama instance; see
  `DEVELOPMENT.md` for reaching it from WSL. Any *other* paid API call
  (embeddings, a new tool) still needs explicit confirmation first.
- Fail loud. Surface errors in ingestion, embedding, retrieval, or the
  service layer — never silently degrade.
- Update `progress/CURRENT.md` and `progress/JOURNAL.md` as you complete
  meaningful units of work, not just at the end of a session — assume the
  session may be interrupted at any point.
- Log every consequential technical choice (library swap, chunking
  strategy, model choice) in `decisions/` using the ADR format described
  there — future sessions need to know why, not just what.
- When a requirement is ambiguous but low-stakes, pick a sensible default,
  document the assumption in `progress/JOURNAL.md`, and continue. When it's
  high-stakes (changes architecture, cost, or scope), stop and ask.
- Run the full test question set in `EVALUATION.md` before declaring any
  phase complete. "It runs without errors" is not "it works."

## Definition of Done (current phase)

See the Definition of Done checklist in `docs/PHASE_1_SPEC.md`. Do not
report a phase complete until every item is verified true and logged in
`progress/CURRENT.md`.
