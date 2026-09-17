## Why

NexMate's architecture documents no longer describe its implemented routing, retrieval, state, frontend, or tool boundaries, and historical phase completion is being confused with production readiness. Before further features, establish one source-backed HLD that distinguishes the current implementation from the user-approved production direction, unresolved choices, and deferred capabilities.

## What Changes

- Make `ARCHITECTURE.md` the canonical HLD, with separate current and target diagrams, component responsibilities, state ownership, trust boundaries, migration direction, and future acceptance gates.
- Document seven response routes, Layer-1 exact paths, Layer-2 NLU, the three-way task router, descriptive capability registry, sessions, version-awareness, telemetry, hybrid BM25/vector/RRF retrieval, confidence gates, source types, and resolved-issue memory.
- Record the approved direction: authenticated Frappe control plane; browser-to-Frappe only; separate private inference; Frappe-owned state and permission enforcement before retrieval/execution; site-isolated private knowledge; local-only sensitive data by default; durable approvals and auditable actions.
- Preserve all 20 long-term requirements through a status and coverage matrix, including provider interfaces, release/version/patch lifecycle, Bench/Docker source parity, page-aware Desk context, streaming/realtime, transparency, search scaling, and deferred MCP/Developer Workbench.
- Reconcile phase terminology, NexMate/NexPilot naming, document ownership, contradictory progress claims, and current versus unverified Bench/frontend/Docker integration.
- Restore removed historical ADRs from Git with provenance; retain superseded history and distinguish user-approved direction from unresolved implementation choices.
- Establish an evidence matrix separating implemented, tested (with test type), live-tested, unverified, planned, and deferred claims. Historical acceptance with exceptions is recorded separately from production readiness.

## Capabilities

### New Capabilities

None. This documentation-only change does not introduce runtime behavior. `.openspec.yaml` declares `skip_specs: true`; no speculative runtime capability specs will be created or archived as delivered functionality.

### Modified Capabilities

None. The repository currently has no OpenSpec capability specs. Future implementation changes will introduce durable behavioral requirements and scenarios grounded in this HLD; this change preserves the target requirements in architecture documentation and its coverage matrix.

## Impact

Primary documentation: `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`, `PROJECT.md`, `AGENTS.md`, `SECURITY.md`, `DEVELOPMENT.md`, and `EVALUATION.md`. Supporting reconciliation: `README.md`, `CHANGELOG.md`, relevant existing `docs/` specifications, `frappe_app/README.md`, and `progress/`. Limit supporting edits to contradictory scope, references, naming, evidence, and ownership; preserve pre-existing user changes.

No API, runtime, dependency, package metadata, or deployment changes. Code references are evidence only. The current `pyproject.toml` compatibility declaration and package layout will be documented, not changed or certified.

## Non-goals

No application implementation, authentication, dependencies, Docker/Bench installation, MCP, Developer Workbench, production writes, model/provider configuration changes, re-ingestion, tests against live systems, release/publishing, or second HLD. No automatic acceptance of unresolved architecture choices, invented implementation evidence, runtime renames, or removal of existing production-write approval requirements. Planning creates only this change's artifacts; subsequent apply work remains documentation-only.
