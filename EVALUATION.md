# EVALUATION.md — Acceptance Methods and Evidence

`ARCHITECTURE.md` is the sole canonical HLD; this document owns acceptance
methods, not design or approval. `ROADMAP.md` preserves historical Phase 1–8
acceptance with exceptions and orders future milestones. Post-roadmap work
requires a user-approved OpenSpec change. `SECURITY.md` and `DECISIONS.md`
govern locality, staging, individual confirmation and separate production
approval; an evaluation plan never authorizes model calls or data writes.

The original Phase 1 question set and checklist below remain historical
requirements/evidence. Their checked boxes are dated, not a present service
health assessment or proof that the future production gates have passed.

## Developer-mode test questions (Phase 1)

Manually verify each against real retrieved answers and correct citations:

1. How do I create a custom DocType?
2. How does `frappe.whitelist` work?
3. How do I override a controller in ERPNext?
4. How do I create a server script?
5. How do I create a custom app?
6. What hook should I use to run code after a document is saved?
7. How do I safely migrate a customization to a new ERPNext version?
8. How do I add a custom field to an existing DocType?
9. What's the difference between a Server Script and a Client Script?
10. How do I create a REST API endpoint for a custom DocType?
11. How do child tables work in Frappe?
12. How do I set up a scheduled/background job in Frappe?
13. How do permissions work for a custom DocType?
14. What's the correct way to query the database in a Frappe app (ORM vs
    raw SQL)?
15. How do I debug a validation error on document submit?

## Negative test cases (must correctly decline, not fabricate)

- A question with no relevant match in the corpus (e.g., an unrelated
  general-knowledge question)
- A question about a feature that doesn't exist in ERPNext/Frappe
- A question phrased ambiguously enough that retrieval returns low-relevance
  chunks

## Quality bar for each answer

- Grounded in retrieved content only — no fabricated ERPNext/Frappe
  internals not present in the source material
- Cites specific document(s)/section(s)
- Version-appropriate (does not assume the newest ERPNext version's
  behavior if the corpus spans versions — flag this as a known limitation
  in `progress/CURRENT.md` if version-scoping isn't built yet)

## RAGAS metrics (introduce before declaring Phase 1 done)

Run RAGAS against the test set and record scores for:
- Faithfulness (is the answer supported by retrieved context?)
- Answer relevancy
- Context precision

Log baseline scores in `progress/CURRENT.md`. There's no fixed passing
threshold yet — the point is to have a measured baseline to compare future
changes against, not to eyeball quality.

## Definition of Done — Phase 1

Status as of 2026-08-24 (independently verified + user-accepted; see
`progress/CURRENT.md` for evidence and the two consciously-deferred items):

- [x] ERPNext + Frappe docs ingested, chunked, embedded into Chroma
- [x] All 15 developer questions above answered with correct citations,
      verified manually
- [x] All 3 negative test cases correctly return a "no confident answer"
      response instead of fabricating
- [x] RAGAS baseline scores recorded
- [x] FastAPI service running with the documented request/response contract
- [ ] Minimal Frappe sidebar page sends a question and displays answer +
      sources *(consciously deferred — no bench exists on this machine;
      app code complete per current conventions)*
- [x] `README.md` lets a second person set this up from a clean machine
- [x] `progress/CURRENT.md` accurately reflects state, including known
      issues or shortcuts taken

## Evidence discipline for future acceptance

Every new claim records capability/requirement ID, architectural status,
source revision, verification type, date, environment, artifact, result,
limitations and next gate. Distinguish **implemented**, **tested** (name
unit/mock/integration/browser scope), **live-tested**, **unverified**,
**planned** and **deferred**. A source file proves implementation, not
installation or a passed security boundary. Missing evidence stays explicit.
Dated historical acceptance does not certify current settings or health.

- Run the applicable full question set, negatives and held-out cases before
  a new quality acceptance claim. Review answers against actual cited
  passages and installed Frappe/ERPNext versions, not citation presence or
  identifier matching alone. Keep retrieval confidence distinct from NLU
  confidence; neither is a correctness or permission guarantee.
- Complete the live conversational/NLU matrix separately from retrieval
  evaluation: exact fast paths, non-exact conversation, capability,
  clarification, out-of-scope, troubleshooting, all three task routes,
  follow-ups, mode restrictions and provider timeout/invalid-output paths.
  Troubleshoot is an NLU kind, not an eighth response route. Mocked NLU
  results and one live follow-up do not complete this matrix; a historical
  outage does not establish current model unreachability.
- Stub-DOM/Node tests and standalone preview checks do not prove real Desk
  assets, authentication, page context, history or realtime behavior. Live
  ERPNext API tests do not establish Bench packaging or Docker parity.
- Judge runs must identify provider/model, locality/consent, embedding
  model, sample/index revision, valid rows, missing rows and failure causes.
  Independent judging and per-question groundedness review are needed to
  resolve uncertainty; self-judging is not independent acceptance.

### Recorded RAGAS baseline limitations — not a rerun

Reported in `progress/CURRENT.md`: scoring completed 2026-09-08 on
2026-08-24 samples and was recovered/logged 2026-09-09. Artifacts:
`data/ragas_samples_2026-08-24T11:32:30Z.json` and
`data/ragas_baseline_2026-08-24T11:32:30Z_124955.json`. Judge was the same
local `qwen2.5-coder:7b` used for generation, with bge-small embeddings.

| Metric | Post-hybrid mean (valid rows) | Pre-hybrid 2026-08-23 mean (valid rows) |
|---|---|---|
| Faithfulness | 0.734 (8/15) | 0.992 (12/15) |
| Answer relevancy | 0.939 (11/15) | 0.941 (15/15) |
| Context precision | 0.564 (9/15) | 0.562 (15/15) |

Reported NaNs include judge parse failures; changed valid-row coverage and
self-judging prevent a clean causal comparison. The faithfulness drop
cannot be dismissed as harmless judge noise, nor does it alone establish
an application regression. Retain per-question failures for independent
review and use held-out cases; RAGAS does not evaluate full orchestration,
authorization or UI behavior. No artifact was regenerated here.

## Future production acceptance gates — planned, not passed

These methods correspond in order to M1–M7 in `ROADMAP.md` and the HLD's
migration stages. Each runtime gate needs its own approved OpenSpec change,
maintained requirements/scenarios, controlled test environment and review.
The tests below are obligations, not instructions to execute them in this
docs-only change. Choose exact latency, quality, scale, retention and
recovery targets before evaluating the affected gate; do not invent passing
thresholds or assume a deployment topology to make documentation complete.

### G1 — Reviewed contracts and measurable criteria

Review ADRs for identity/site propagation, private-service authentication,
tool/provider contracts, index/ingestion ownership, ACLs, executor/repository
binding, tenancy, egress grants/revocation, durable state/audit, transport
and version/packaging policy. Record alternatives, accepted mechanism,
approval provenance and unresolved dependencies. Requirements must map to
observable acceptance scenarios before implementation. A recommendation
for physical per-site deployment is not an accepted decision.

### G2 — Authenticated Frappe entry and authorization

Use integration and negative tests for every entry point, including
legacy/direct tool replacements: browser traffic terminates at authenticated
Frappe; private inference verifies caller/site binding. Demonstrate rejection
of unauthenticated, wrong-site and unauthorized requests before retrieval or
execution. Caller-selected mode, session identifiers, page hints and LLM
output must not grant authority. Verify actual Frappe permissions, not only
the shared upstream API account's permissions or CORS settings.

### G3 — Owned state, authorized context and Desk delivery

Test real Frappe persistence and owner/site checks for conversations and
proposals across restart and concurrent turns. Validate route/DocType/name
hints (including Sales Invoice SI-00042) before minimal field reads. Use
permitted and denied documents/fields, later-turn permission revocation and
history/context reauthorization cases; denied data must not reach inference.
Verify reset/retention behavior without deleting resolution knowledge by
accident. In real browsers/Desk, test transcript restoration, authorized
user-scoped streaming/realtime, reconnect, partial/duplicate events,
cancellation and revocation. Synthetic browser fixtures do not replace
real Bench integration evidence.

### G4 — Isolated retrieval, compatible providers and safe indexes

Use separate site and intra-site permission fixtures for company documents,
code, resolved issues and live context. Assert denied material never enters
vector/lexical candidates, retrieved context, caches, citations or model
input, and does not leak through diagnostics. Site isolation alone is not
user authorization; post-retrieval answer filtering cannot pass this gate.

Instrument every provider boundary with synthetic sensitive-data markers:
generation, corrective retries, routing/NLU, condensation, embeddings and
evaluation/judge paths. Assert local-default/deny-by-default egress for
prompts, history, company docs/code/resolutions, live results, embeddings,
telemetry and Debug; mixed requests inherit sensitive-content restrictions.
Exercise exact data-class/provider/purpose grants and revocation, and
exclude synthetic secrets even with ordinary content approval. Configuration
alone must not enable cloud transmission or silent fallback. Do not use
real credentials/private data as test payloads or authorize a paid call by
writing a test plan.

Provider conformance covers bounded inputs/outputs, model/capability
identity, errors, timeouts, cancellation/streaming and locality for each
selected generation provider, not just one successful LiteLLM call.
Embedding changes require model/revision, dimension, normalization/metric
compatibility checks and controlled rebuilds. Vector adapters must preserve
search/filter/upsert/delete semantics, IDs, metadata, provenance and ACL
scope. Prove safe rebuild publication, deletion/update handling, counts,
rollback, preservation of unrelated public/company/resolution corpora and
lexical/vector freshness coupling. Recalibrate confidence and run held-out
retrieval/grounding checks after model/index/search changes. Search-scaling
choices require measured latency/memory/freshness/quality evidence; Qdrant,
pgvector, alternate inverted indexes and reranking are not selected here.

### G5 — Durable tools, human approval and complete audit

Contract tests cover validated bounded tool inputs/outputs, provenance,
permission/context, side-effect class, approval, typed errors, timeouts,
cancellation and audit. Exercise durable actor/site-bound proposals,
immutable exact payload/diff approval, rejection, expiry, revocation,
permission recheck and stale target preconditions. Changed payloads require
new approval. Include restart, concurrent/conflicting actions, duplicate
requests, retry/idempotency, unknown upstream outcomes and reconciliation
without blind replay; demonstrate controlled audit-failure recovery.

Keep business writes in authorized staging and individually confirmed;
production writes need separate approval. For code execution, test the
separate confined executor, repository binding, root/symlink containment,
tracked-not-ignored/clean-tree gates and per-edit confirmed atomic-commit
contract, including concurrency and partial failure. Do not infer a
cross-system atomic transaction from a successful one-file commit.

Audit evidence must correlate actor/site/request/action across AI requests,
permitted retrieval, tool calls, proposals, approvals/rejections/expiry,
executions, successes, denials, failures and security events. Test access,
redaction, retention/deletion, tamper resistance and recovery against the
chosen guarantees, not only successful post-write JSONL. Debug disclosure
tests verify authorized retrieval provenance, documents/fields and raw
results; generated queries are visible only where they exist and disclosure
is permitted. No SQL-generation tool or unrestricted prompt dump is implied.

### G6 — Release, version/patch lifecycle and deployment parity

From the same Git application source, prove clean install and update in
ordinary Bench and Docker without an application fork. Verify the actual
monorepo packaging path, packaged assets, hooks/boot injection and real Desk
behavior; a filesystem-served preview does not pass. Validate selected app,
Frappe/ERPNext v16, Python, inference-service and index compatibility,
versioning policy, normal Frappe patches/migrate and CI tests/lint checks.
Current dynamic package versioning and Frappe `>=15` metadata are not a
tested v16 support matrix (`frappe_app/pyproject.toml:9`, `:16`).

Record backup/restore, upgrade/index migration and rollback artifacts and
recovery outcomes before an explicitly approved versioned release and
repeatable installation/update. No install, release or Docker-readiness
claim is made by this reconciliation.

### G7 — Independent production readiness decision

Independent security, quality and operational review evaluates G1–G6
artifacts, held-out cited answers and negatives, the full live NLU matrix,
provider/locality/audit evidence and agreed latency/cost/recovery budgets.
Document limitations and unresolved decisions rather than accepting a
build agent's self-report. Release approval is separate from explicit
production-write authorization for a named environment in `DECISIONS.md`.
MCP and Developer Workbench remain deferred exclusions, not missing work
to implement during this review.

### R01–R20 proof-method index

The HLD owns architectural status; this index only locates future methods.

| Requirement | Future method / explicit exclusion |
|---|---|
| R01 LLM abstraction | G1 contract; G4 per-provider conformance, locality and failure tests. |
| R02 Embedding abstraction | G4 model/dimension compatibility, locality and controlled rebuild. |
| R03 Vector abstraction | G4 adapter operations, metadata/ACL preservation and rollback. |
| R04 Deployment boundary | G2 authenticated Frappe/private inference; G6 deployment evidence. |
| R05 Professional lifecycle | G6 source-to-package-to-checks/migrate-to-approved-release/update. |
| R06 Bench/Docker parity | G6 same-source clean install/update and real Desk checks in both. |
| R07 Versioning/compatibility/patches | G1 chosen matrix; G6 version, patch/migrate, restore/rollback tests. |
| R08 Auditability | G5 correlated full lifecycle, failure/recovery, redaction/access/retention. |
| R09 Explicit tools | G2 entry-point coverage; G5 authorized typed tool contracts. |
| R10 Desk/history/streaming/realtime | G3 owner-bound persistence and real-browser delivery cases; G6 assets. |
| R11 Page context | G3 untrusted hint validation and minimal authorized document/field reads. |
| R12 Context/history answers | G3 ownership, bounded context and later-turn permission rechecks. |
| R13 Authorization before retrieval/execution | G2, G3, G4 and G5 denied-data/denied-action tests at each boundary. |
| R14 Debug/transparency | G5 role/policy-filtered disclosure; no new query-generation capability. |
| R15 MCP | Deferred; future approved consumer/trust/protocol scope and authorization/audit tests. |
| R16 Search scaling | G4 measured scale/quality/freshness, compatibility and isolated migration. |
| R17 Human-approved writes | G5 durable immutable approvals, concurrency/retry/uncertain outcomes; G7 separate production approval. |
| R18 Site-isolated private knowledge | G1 topology decision; G4 cross-site plus intra-site ACL negatives. |
| R19 Local-default company/live data | G4 deny-by-default all-call egress, grants/revocation and secret exclusion. |
| R20 Developer Workbench | Deferred separate engineering surface; future approved privileged UX/authorization/audit scope, not an employee mode. |

## Documentation-only acceptance for this change

Verify source fidelity, exact ADR restoration/provenance, reference and
phase/name/status consistency, R01–R20 coverage and unresolved/deferred
boundaries. Inspect diffs to preserve pre-existing work and explicit file
ownership; no runtime/config/dependency, secret, model, service, data or
deployment operation is part of acceptance. Run strict OpenSpec change
validation and `git diff --check`, then obtain independent read-only review.
Record dated documentary evidence and hand off blockers when progress/tasks
files are owned by others. These checks pass no future runtime gate and
create no fresh phase, production, release or cloud-consent approval.
