# SECURITY.md — Guardrails (always in effect)

These apply regardless of phase and override convenience shortcuts.

## Current phase (RAG over public docs only)

- No credentials, API keys, or company-internal data are needed or used —
  the corpus is public documentation only. If any task seems to require a
  secret or company-internal data, stop; that's a later-phase concern
  (Phase 3+), not this one.
- The vector DB and embeddings run locally regardless of generation
  provider choice. Generation itself is user-configurable (see
  `ARCHITECTURE.md`'s "Generation provider config") — if `GENERATION_PROVIDER`
  is set to a cloud service (Anthropic/OpenAI/etc.), retrieved document
  content IS sent to that provider as part of the prompt. This is fine and
  expected for Phase 1 (public docs only). Once Phase 2/3 introduce company
  code and internal documents into retrieval, re-confirm with the user
  before leaving a cloud `GENERATION_PROVIDER` active — that's the point at
  which "content sent to a third party" starts to include proprietary
  material, not just public ERPNext docs.
- The FastAPI service should bind to localhost only during development, not
  `0.0.0.0`, unless explicitly required for the Frappe app to reach it
  across a network boundary — and if so, document the exposure.

## Standing rules for later phases (do not implement yet, but do not violate when their time comes)

- **Read-only until proven safe.** The ERPNext API tool (Phase 4) is
  read-only. No write/create/delete calls against a live ERPNext instance
  without an explicit, separate, confirmed decision.
- **Staging before production.** The Developer Agent (Phase 7, write
  actions) operates against a staging ERPNext environment only until
  explicitly approved for production use, and every write action requires a
  confirmation step — no silent multi-step actions against live company
  data.
- **Company knowledge stays local.** Company-specific documents, code, and
  configuration (Phases 2–3) are embedded and served locally; they are not
  sent to any third-party API unless that specific decision is made and
  logged in `decisions/`.
- **Least privilege for tools.** Each tool (RAG, ERPNext API, code search)
  should only be able to do what its phase requires — no tool gets broader
  access "just in case" for a future phase.

## Dependency hygiene

- Pin versions in `requirements.txt`.
- Don't install packages outside what `ARCHITECTURE.md`'s locked stack (and
  its per-phase additions) specifies without flagging the addition.
- Never trigger an `ollama pull` (generation model download) without
  confirming the model name and size with the user first — this is now
  hard-enforced by `opencode.json`'s permission settings, not just an
  instruction. The embedding model is exempt from this — it's small and
  safe to auto-download. See `AGENTS.md`'s "Model downloads" section.
