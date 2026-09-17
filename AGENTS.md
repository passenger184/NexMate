# AGENTS.md — NexMate Engineering Instructions

Treat NexMate as software for a real company, not a demo. Production
quality is the goal, not a claim about current readiness. Read the documents
below for their distinct authority; automatically loaded historical text
does not override the approved scope or standing security policy.

## Read order and authority

1. `PROJECT.md` — NexMate name, audiences, v16 scope and product invariants.
2. `ARCHITECTURE.md` — sole canonical HLD: current implementation, approved
   target direction, unresolved decisions and deferred capabilities.
3. `ROADMAP.md` — historical Phase 1–8 acceptance with exceptions, then
   ordered future migration gates; not an active Phase 2 pointer.
4. The user-approved change in `openspec/changes/` — proposal, design and
   tasks bound post-roadmap work. Future behavior changes introduce
   maintained requirements/scenarios in `openspec/specs/`; neither planning
   artifacts nor specs are proof of delivery.
5. `docs/PHASE_1_SPEC.md` through `docs/PHASE_4_SPEC.md` — historical
   requirements, not competing current build scope. Read when relevant.
   `docs/FUTURE_MULTI_WORKSPACE.md` remains deferred reference only.
6. `docs/UI_SPEC.md` — standing interaction reference;
   `docs/UI_VISUAL_SPEC_updated.md` is the canonical blue visual reference,
   superseding `docs/UI_VISUAL_SPEC.md`. Neither proves real Desk delivery.
7. `SECURITY.md` — standing guardrails and target enforcement requirements;
   `DECISIONS.md` — sole canonical ADR ledger, including approval provenance.
8. `EVALUATION.md` — acceptance methods and evidence requirements;
   `progress/CURRENT.md`, `progress/BLOCKERS.md`, `progress/JOURNAL.md` —
   dated observations and remaining verification, not design authority.
9. `DEVELOPMENT.md` — development/release runbook; `README.md` — onboarding.

## The scope rule

**Build only the user-approved OpenSpec change and explicitly assigned
scope.** The original eight phases are historically functionally complete
with recorded exceptions. Their sequence was public RAG, live code tools,
company knowledge, memory, ERPNext reads, orchestration, employee mode,
then ERPNext writes. Historical prohibitions against those later phases do
not prohibit maintaining implemented features, nor authorize new work.

The approved production direction is authenticated Frappe control/state
ownership with separate private inference, not a completed migration.
Unresolved implementation choices and deferred features in the HLD are not
permission to implement them. The current system remains single-project;
site isolation as a target does not authorize shared multi-workspace routing.
Stop and ask before adding architecture, cost, privileges or scope.

For `reconcile-architecture-and-production-hld`, work is documentation-only:
no runtime/configuration/dependency changes, installation, live tests,
model calls, data mutation, release or production approval. Respect explicit
file ownership and preserve other contributors' changes. Documentation
reconciliation does not invoke the product's confirmed Git-edit tool;
its clean-tree/per-edit-commit safeguards remain product requirements,
not an instruction to auto-commit this repository's documentation work.

## Model downloads — confirm before pulling an LLM

Never run `ollama pull` (or any generation-model download command) without
telling the user the exact model name and approximate size and waiting for
explicit confirmation. See the existing `opencode.json` permissions; do
not change configuration to bypass the rule. The local embedding model
`BAAI/bge-small-en-v1.5` (~130MB) may download automatically when authorized
runtime work needs it; a docs-only change does not need or trigger it.

There are two model roles, not a fixed inventory of installed models:
- **Embedding:** local sentence-transformers, independent of generation.
- **Generation:** local Ollama or explicitly configured cloud provider.
  `llama3.1:8b` is ~4.7GB, `mistral:7b` ~4.1GB, `phi3:mini` ~2.3GB.
  Cloud generation requires no local generation-model download.

## Operating principles

- Correctness over cleverness. Every technical answer must be traceable to
  a real source; confidence heuristics and identifier repair are not proof.
- Generation provider/model stays configurable via `.env`, never hardcoded.
  See `ARCHITECTURE.md` and `DEVELOPMENT.md`. The user runs Ollama on Windows,
  not WSL; do not install a second instance. Cloud configuration does not
  grant private-data consent. Follow `SECURITY.md` for all-call egress policy;
  any other paid API (embeddings or a new tool) requires confirmation first.
- Fail loud. Surface ingestion, embedding, retrieval and service errors;
  document bounded fallback behavior rather than silently hiding failures.
- Update `progress/CURRENT.md` and `progress/JOURNAL.md` as meaningful units
  complete, unless explicit file ownership excludes them; then hand off
  evidence and blockers without editing others' files.
- Record consequential technical decisions in `DECISIONS.md` with rationale,
  status and provenance. Approved direction is not chosen implementation.
- For low-stakes ambiguity, document the assumption and continue within
  scope. For architecture, cost, security or scope changes, stop and ask.
- Never commit, release or archive without explicit user instruction.
  Preserve the product tool's separate confirmed atomic-commit contract.

## Definition of Done

Use the approved change's requirements and `EVALUATION.md` verification
methods. Record test type, date, environment/artifact, limitations and next
gate; do not infer production readiness from historical phase completion.
Run the applicable full question set before a new quality/phase acceptance
claim. Mocked NLU and stub-DOM tests do not establish live NLU or Bench
acceptance. Documentation-only acceptance checks consistency, provenance,
scope and OpenSpec validity; it does not run or pass future runtime gates.
