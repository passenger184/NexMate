# progress/BLOCKERS.md — Open Blockers

List anything that stopped forward progress and needs a human decision.
Remove an entry once resolved, and note the resolution in
`progress/JOURNAL.md`.

**Last updated:** 2026-09-17 — source-only documentation reconciliation
`reconcile-architecture-and-production-hld` COMPLETE as a documentary unit.
No runtime tests, model calls, network checks or live configuration
inspection occurred in this change.

## Documentation acceptance — resolved (2026-09-17)

- **Independent review DONE.** Two independent read-only reviews (architecture
  content, plus a fresh review after one reviewer disclosed a /tmp script
  write outside the repository) and a security review found no blocking
  documentation findings. Strict OpenSpec change validation and
  `git diff --check` pass; one trailing-blank-line finding was fixed.
  Documentary acceptance only — no runtime gate is passed, the change is
  archived at
  `openspec/changes/archive/2026-09-17-reconcile-architecture-and-production-hld/`
  and NOT committed, and the unresolved decisions below remain open.

## Open — documentation acceptance

(none — prior pending-review entry resolved 2026-09-17; see journal)

## Remaining verification and decisions — future gates, not current tasks

- **Live conversational/NLU acceptance incomplete.** The 29-case routing
  evaluation used mocked NLU; reported 145 Python + 26 Node checks are
  unit/mock and stub-DOM evidence. Session 18's provider outage is historical
  (recorded by the 2026-09-08-era status), not a current measurement; the
  later session 19 follow-up success does not complete the live matrix.
  See `EVALUATION.md` for the full future acceptance set.
- **Bench/Desk unverified; Docker planned.** Real installation, packaged
  assets/boot injection and browser behavior need evidence. Standalone
  preview/stub-DOM checks and 2026-08-24 staging API tests do not establish
  Bench installation or same-source Bench/Docker install/update parity.
  History restoration, authorized page context and streaming/realtime remain
  target work, not verified UI delivery.
- **RAGAS interpretation unresolved, recovery recorded.** The 2026-09-08
  score on 2026-08-24 samples was recovered/logged 2026-09-09, not awaiting
  its first score. Faithfulness 0.734 (8/15), relevancy 0.939 (11/15) and
  precision 0.564 (9/15) use a self-judge; pre-hybrid coverage differs.
  Neither harmless judge noise nor a regression follows from these means.
  Independent judging, per-question source review and held-out cases remain
  necessary; Q3/Q7/Q11 lows cannot be dismissed without review.
- **Production contracts unresolved.** `ARCHITECTURE.md` U1–U10 owns the
  decision register: physical tenancy/repository binding, index ownership,
  executor confinement, identity/service/tool/provider/streaming contracts,
  intra-site ACLs, all-call egress grants/revocation, durable state/audit,
  version/packaging policy, operational budgets and Debug disclosure.
  These block dependent implementation gates, not documentation of options.
- **Direction is not choice or consent.** Authenticated Frappe control/state
  ownership with separate private inference is approved direction, not a
  selected per-site/shared topology, executor/protocol or implementation.
  Production writes remain unapproved; staging, flag gating and individual
  confirmation remain mandatory. Provider configuration is not private-data
  cloud consent. No present environment settings are certified here.
- **Index/quality gaps need separately approved work.** Public rebuilds can
  remove unrelated corpora; BM25 snapshots and current-code chunks can go
  stale. Version exclusions do not prove exact v16 compatibility. Historical
  corpus counts and installed versions are dated, not current inventory.
  No rebuild, migration or model call is authorized to resolve these here.
- **Deferred, not missing delivery:** MCP, Developer Workbench, shared
  multi-workspace routing and alternative search engines remain outside
  scope. Future runtime work requires a separately approved OpenSpec change.

No future production gate is passed by this documentary handoff.

## Resolved

## [2026-08-23] ERPNext/Frappe doc source no longer exists in git
**Finding:** `PHASE_1_SPEC.md`'s preferred option — doc source in the
`frappe/erpnext` / `frappe/docs` repos — is dead. Both docs sites migrated
off GitHub into Frappe's wiki platform (~2021): canonical sources are now
`https://docs.frappe.io/erpnext` and `https://docs.frappe.io/framework`
(docs.erpnext.com links there directly). Verified absent from git:
`frappe/erpnext@version-15` has no docs dir; `frappe/frappe@version-15`
and `develop` have no `frappe/docs/`; `github.com/frappe/docs` is 404.
**Resolution:** Ingest via sitemap crawl of docs.frappe.io (clean markdown
with YAML front-matter per page, CC-BY-SA 3.0). This is the spec's own
named fallback ("scraping the live site") and the site docs.erpnext.com
itself points to — not a workaround guess. Logged as ADR in
`DECISIONS.md`; flagged to user for veto.

