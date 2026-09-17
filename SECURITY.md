# SECURITY.md — Guardrails (always in effect)

Standing policy for NexMate, regardless of phase; convenience does not
supersede it. `ARCHITECTURE.md` is the canonical current/target HLD and
`DECISIONS.md` is the sole approval/ADR ledger. Historical Phase 1–8
acceptance is not production readiness. The 2026-09-17 acceptance is of
production direction, not implementation choices, production writes or
private-data cloud consent.

## Policy versus current enforcement

The requirements here do not certify current enforcement. The current
browser-facing FastAPI accepts caller-selected mode/session identifiers
(`service/main.py:198`); employee routing guards are not authenticated
roles and do not cover legacy/direct tools. Shared upstream ERPNext
credentials do not establish the incoming user's permissions. Source-type
tags are not ACLs, and localhost/CORS settings are not authentication.
Proposals are process-local and write audit is appended after execution
(`tools/erpnext_write.py:188`, `tools/erpnext_write.py:238`). The common
provider call has no enforced private-data consent gate
(`rag/generator.py:213`). These are gaps, not policy exceptions.

The code-edit rules below describe the product tool. Documentation-only
reconciliation does not invoke that tool or authorize repository commits;
follow explicit file ownership, preserve existing changes, and never
commit this documentation work without the user's request. Product
clean-tree, confirmed per-edit atomic-commit safeguards remain unchanged.

## Live code read/edit agent (Phase 2) — non-negotiable guardrails

This tool operates on the user's actual project source code. These rules
apply from the moment this tool exists, with no exceptions and no "just
this once":

- **Project-root scoping.** Every file operation must resolve to a path
  inside this project's root (the one project this system is currently
  scoped to — see `ARCHITECTURE.md`'s "Scope: single project for now").
  Reject — don't sanitize, don't "helpfully" redirect — any path that
  resolves outside it, including via `..` traversal or symlinks.
- **Read/search/explain tools are always-on, no confirmation needed.**
  Reading a file, searching code, or explaining an error is safe and
  should not require the user to approve every lookup — that would make
  the tool annoying to the point of being unused.
- **Write tools require a clean git tree before they run.** If the
  workspace's git status isn't clean, refuse the edit and tell the user to
  commit or stash first. This is not optional — it's what makes every
  subsequent edit revertible.
- **Every edit is its own confirmed, atomic commit.** Show the user the
  diff before applying it. Get explicit confirmation. Apply it, then commit
  it with a clear message. Never batch multiple file edits into one
  unreviewed commit.
- **No edits to files outside version control**, and no edits to
  git-ignored files (build artifacts, `.env`, credentials, `node_modules`,
  etc.) — if a requested edit targets one, say so and ask how the user
  wants to handle it rather than silently proceeding or silently skipping.
- **This tool never touches live ERPNext data** — no document
  creates/updates/deletes via the ERPNext API. That's a separate,
  Phase 8 capability with its own, stricter guardrails. Code
  editing and data editing are different risk profiles and must stay
  architecturally separate — not the same tool with different arguments.

## Standing operational constraints

- **Separate read and write authority.** The Phase 5 ERPNext read tool
  stays read-only. Phase 8 create/update is separately flag-gated by
  `ERPNEXT_WRITE_ENABLED` at proposal and execution, staging-only under the
  2026-08-24 ADR. Delete is deliberately unimplemented. Every write requires
  explicit confirmation; multi-step work means individually approved
  actions, never silent chaining.
- **Staging before production.** No production writes without a separate,
  explicit approval recorded in `DECISIONS.md`, including the intended
  environment. Release approval, an environment label, historical staging
  success or the accepted HLD direction grants no such authorization.
- **Local development exposure.** FastAPI must bind to localhost, not
  `0.0.0.0`, unless cross-network access is explicitly required and the
  exposure documented. This is a containment rule, not authentication.
- **Least privilege.** No tool receives broader access for a possible
  future feature. Read/search/explain needs no per-call confirmation, but
  that does not exempt it from authenticated authorization or locality.

## Target identity, context and knowledge enforcement — not delivered

- Browser requests use authenticated Frappe methods only; inference is
  private and validates caller/site binding. Frappe is the control/state
  authority, not merely a transport proxy. Identity propagation and service
  authentication protocols remain unresolved.
- Frappe derives allowed tools, documents/fields and corpus scope from the
  authenticated user before context retrieval or execution, including
  legacy/direct entry points. Client mode, session ID, page route, DocType,
  document name and LLM classifications never establish authority.
- Validate browser page hints and minimize document data. Bind persistent
  conversations and proposals to owner/site; authorize history, subsequent
  turns and realtime delivery, including after permission changes.
  Inference receives only bounded authorized context, not workflow authority.
- Isolate each site's private knowledge/search and enforce intra-site user
  ACLs independently. Denied content must not enter retrieval candidates
  or model context; filtering an answer afterward is insufficient. Apply
  this to company documents, code and resolved issues as well as ERP data.
  Index lifecycle, lexical caches and rebuilds must preserve those bounds.
- Physical per-site versus shared service/index isolation, public-index
  sharing, ACL representation and site-to-repository binding remain open.
  Site isolation does not approve shared multi-workspace routing.

## Local-default data and all-call egress policy

Company documents, source code, configuration, resolved issues and live ERP
results remain embedded and served locally unless specific cloud disclosure
is explicitly approved and recorded in `DECISIONS.md`. Public-provider
configuration alone is not consent once any private content enters a call.

The target enforced policy is deny-by-default across **all** provider calls,
not only final RAG answers. Classify and minimize user prompts, conversation
history, NLU/classification and condensation inputs, retrieved documents,
code/diffs/resolutions, tool results, embeddings, telemetry and Debug data.
Derived summaries and vectors do not automatically become public. Policy
must identify permitted data classes, recipients/providers and purpose,
check locality and revocation before sending, and refuse rather than
silently switch providers. No remote embeddings are enabled by this policy.

Secrets, credentials and API keys are excluded from prompts, retrieval,
telemetry and Debug regardless of normal content consent; credentials used
for transport authentication are not model context. Retention, redaction,
cloud-policy representation and enforcement contracts require separate
review. Existing local/cloud configuration and corpus history are not proof
of consent or enforcement.

## Target durable proposals, execution and audit — not delivered

- Frappe owns durable, actor/site-bound proposal and approval state. Present
  the exact immutable payload/diff and intended target before approval;
  changed payloads require new confirmation. Enforce ownership, expiry,
  rejection and permission recheck at execution, not just at proposal time.
- Define restart recovery, concurrent approval/execution, idempotency,
  retries and uncertain-outcome reconciliation before production use. Do
  not blindly repeat a write whose outcome is unknown. Select the state
  machine and persistence guarantees through a future reviewed change.
- Keep privileged code/Git execution separate from business writes and
  inference. Executor placement and repository credentials/binding remain
  unresolved; existing root-scoping, tracked-file, clean-tree and confirmed
  atomic-commit requirements remain mandatory for that tool.
- Correlate AI requests, tool calls, permitted retrieval provenance,
  proposals, approvals/rejections/expiry, executions, failures and security
  events with authenticated actor/site and request/action identifiers.
  Evidence must account for failed and denied actions and audit-persistence
  failures, not only successful post-write appends.
- Minimize/redact audit content and enforce access and retention policy.
  Complete lifecycle audit does not mean retaining every prompt or raw
  result. Debug is separately role/policy-filtered: documents/fields used,
  permitted retrieval/raw results and generated queries only where they
  actually exist and disclosure is authorized. This adds no SQL tool.

`EVALUATION.md` defines future negative and failure-path proof obligations.
No target requirement here certifies current enforcement or authorizes a
runtime/security migration in this documentation-only change.

## Dependency hygiene

- Pin versions in `requirements.txt`.
- Don't install packages outside what `ARCHITECTURE.md`'s locked stack (and
  its per-phase additions) specifies without flagging the addition.
- Never trigger an `ollama pull` (generation model download) without
  confirming the model name and size with the user first — this is now
  hard-enforced by `opencode.json`'s permission settings, not just an
  instruction. The embedding model is exempt from this — it's small and
  safe to auto-download. See `AGENTS.md`'s "Model downloads" section.
