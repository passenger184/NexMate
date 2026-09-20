## Purpose

The M7 production-readiness review independently assesses whether NexMate's implementation and recorded evidence satisfy the accepted production criteria, producing separate release, production-write, and cloud-consent decisions without performing implementation work itself.

## ADDED Requirements

### Requirement: Gate evidence inventory
The review SHALL inventory evidence for HLD gates G1–G7 and the delivered M2/M3/M4/M5/M6 changes, recording for each item: capability/requirement ID, architectural status, source revision, verification type (implemented / tested with scope / live-tested / unverified / planned / deferred), date, environment, artifact, result, limitations, and next gate, per `EVALUATION.md` evidence discipline. Missing evidence SHALL stay explicit; dated historical acceptance SHALL NOT be presented as current health or passed gates.

#### Scenario: Complete inventory
- **WHEN** the review covers a gate (e.g., G4 isolated retrieval)
- **THEN** every proof obligation from the HLD traceability row and `EVALUATION.md` method section is listed with its evidence state, and gaps are named rather than inferred as passing

#### Scenario: No inflated claims
- **WHEN** only mocked, stub-DOM, or preview-level evidence exists for a boundary (e.g., NLU matrix, Desk delivery)
- **THEN** the inventory records it as unit/mock evidence, not live or Bench acceptance

### Requirement: Quality and evaluation evidence with known limitations
The review SHALL execute or reference the held-out grounded-question and negative sets, the full live conversational/NLU matrix, and RAG/evaluation evidence, carrying the recorded limitations: RAGAS self-judging by the generating model, changed valid-row coverage (faithfulness 8/15 post-hybrid vs 12/15 pre-hybrid), and unresolved per-question review. Retrieval confidence and NLU confidence SHALL be kept distinct from correctness or permission guarantees.

#### Scenario: Held-out quality assessment
- **WHEN** answers are judged against held-out questions and negatives
- **THEN** each answer is checked against its actual cited passages and installed versions with an independent judge identified by provider/model, sample/index revision, valid and missing rows, and failure causes

#### Scenario: Limitations preserved
- **WHEN** RAGAS baselines are cited
- **THEN** the self-judge identity, valid-row counts, and missing-row causes accompany every mean, and no causal regression-or-noise claim is made from means alone

### Requirement: Security, locality, and audit evidence
The review SHALL assess control-plane evidence (authenticated Frappe entry, caller/site binding, chat-only enforcement, legacy/direct denial), locality/egress evidence (deny-by-default across generation, retries, NLU, condensation, embeddings, and judge paths; grant/revocation behavior; secret exclusion), and audit/proposal/write evidence (durable lifecycle, correlated success/denial/failure records, redaction/access/retention), each against `SECURITY.md` standing policy — which the review SHALL NOT reinterpret as current enforcement.

#### Scenario: Policy versus enforcement kept separate
- **WHEN** a standing policy (e.g., deny-by-default egress) is compared with implementation
- **THEN** the finding states the enforcement state with negative-test evidence, never treating policy text as proof of enforcement

### Requirement: Deployment and operational evidence
The review SHALL assess Bench installation/migration evidence (M6: `test-fresh-clone`, 4 DocTypes/tables, zero rows, root-independent imports), Docker parity/build evidence, upgrade/backup/rollback evidence where existing criteria require it, and operational latency/cost/recovery budgets. Where existing acceptance criteria name no numeric threshold, the review SHALL record "threshold requiring explicit agreement" and SHALL NOT invent one.

#### Scenario: Absent threshold flagged
- **WHEN** a criterion (e.g., latency budget) has no agreed value in existing documentation
- **THEN** the review records the gap as requiring explicit agreement instead of choosing a passing value

### Requirement: Findings taxonomy and gap handling
Every finding SHALL be classified into exactly one class: implementation defect, missing evidence, unresolved architecture decision, intentional deferred scope, or governance/approval decision. Deferred items (MCP R15, Workbench R20, alternate search/reranking, shared tenancy) SHALL be recorded as explicit exclusions, never as missing work to implement during the review.

#### Scenario: Finding classified
- **WHEN** a gap is found (e.g., Docker custom-image build never run end-to-end)
- **THEN** it is labeled with one taxonomy class plus the owning gate/requirement, distinguishing it from the other four classes

### Requirement: Separate decision outputs
The review SHALL produce three independent decision records — (1) release readiness, (2) production-write authorization for a named environment, (3) private-data cloud/provider consent — each with its own rationale, evidence linkage, and approval provenance in `DECISIONS.md` format. No output SHALL imply that one decision grants the others. The review SHALL NOT itself approve production writes, grant cloud consent, or declare production readiness; it prepares these decisions for the user.

#### Scenario: Decisions stay separate
- **WHEN** the evidence supports release readiness but no production-write approval exists
- **THEN** the release record states readiness while the production-write record states refusal/pending, with neither inheriting the other's outcome

### Requirement: Review safety boundary and historical milestones
The review SHALL NOT modify production or test environments, run migrations, restart/rebuild services, install packages, make model calls beyond explicitly authorized evaluation runs, write business data, or authorize paid calls merely to obtain evidence. Any validation requiring mutation SHALL be flagged for separate authorization instead of executed. M5 and M6 SHALL be referenced as CLOSED historical milestones; the review SHALL NOT reopen them or recreate their work.

#### Scenario: Mutation-requiring validation deferred
- **WHEN** a check (e.g., live uncertain-outcome reconciliation) needs a state-mutating run
- **THEN** it is recorded as blocked pending separate authorization, not performed inside the review

### Requirement: Explicit review exclusions
The review SHALL NOT perform implementation work and SHALL NOT cover MCP, Developer Workbench, alternate search engines / Qdrant / pgvector, reranking, shared tenancy, new AI providers, RAG redesign, or production deployment, unless existing documentation explicitly requires an item for the M7 gate. Excluded items SHALL appear in the report as explicit exclusions with their deferral provenance.

#### Scenario: Exclusion recorded
- **WHEN** the report is assembled
- **THEN** each excluded surface is listed with its `ARCHITECTURE.md`/roadmap deferral reference, not silently omitted
