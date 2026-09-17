# PROJECT.md — Product Definition

## What this is

An AI ERPNext Engineering & Support Assistant, embedded inside ERPNext as a
sidebar chat panel. Not a generic chatbot that happens to know ERPNext — a
tool-using assistant that understands this company's specific ERPNext
instance, its customizations, and its codebase.

## Product name

**NexMate** — "Your ERPNext AI Companion." This is the current product name
for UI and documentation-facing copy. Historical NexPilot quotations retain
their provenance; runtime/package identifiers are not renamed by this
documentation change. Remaining runtime naming drift is separate future work.

## Scope and authority

Target **Frappe v16 / ERPNext v16**, one project today. `ARCHITECTURE.md` is
the sole canonical HLD; `ROADMAP.md` preserves historical Phase 1–8
acceptance with exceptions. Post-roadmap work requires a user-approved
OpenSpec change, not a historical phase spec or an unresolved HLD option.

The accepted production direction is authenticated Frappe control/state
ownership with separate private inference, site-isolated private knowledge
and permission checks before retrieval/execution. It is not delivered
production readiness, selected tenancy/executor topology, cloud-data consent
or production-write approval. `SECURITY.md` governs those boundaries;
`DECISIONS.md` records approval provenance. Shared multi-workspace support,
MCP and the separate Developer Workbench remain deferred.

## Users

**Primary (now):** a developer doing ERPNext deployment and customization as
their day job — Developer/Admin mode.

**Employee/User audience:** non-technical ERP end users; the restricted
persona and orchestrated public-doc retrieval were implemented in Phase 7.
Wider deployment remains future work: caller-selected mode is not an
authenticated role, and real Bench/Desk integration remains unverified.

## Developer/Admin mode — representative questions

- How do I create a custom DocType?
- How does `frappe.whitelist` work?
- How do I override this ERPNext controller?
- How do I create a server script?
- Why am I getting this validation error?
- How do I migrate this customization safely?
- How do I create a custom app?
- How does this DocType work internally?
- Where is this functionality implemented?
- What hook should I use?
- How do I upgrade our ERPNext installation without breaking customizations?

## Employee/User mode — representative questions

- How do I create a Sales Invoice?
- How do I submit a Purchase Order?
- Why can't I submit this document?
- How do I create a customer?
- How do I check my outstanding invoices?
- How do I make a stock transfer?
- What does this button do?

## Non-negotiable qualities (every phase)

- **Version-aware** — answers reflect the actual installed ERPNext/Frappe
  version, never assume latest-version behavior.
- **Source-cited** — every answer traceable to a specific doc section, code
  location, or company document.
- **Honest about uncertainty** — no confident-sounding fabrication when
  retrieval doesn't have a good match. "I don't have a confident answer for
  this" is always an acceptable response; a wrong technical answer is not.

## Knowledge layering (full vision — built incrementally)

**Public knowledge:** ERPNext, Frappe, Python, Jinja, REST API, hooks,
database schema, framework documentation.

**Company knowledge:** this company's ERPNext configuration, custom
DocTypes/fields/workflows/scripts/apps, policies, procedures, integration
docs, deployment docs, troubleshooting guides, architecture docs.

Current implementation: one vector store with `source_type` metadata;
indexed types are `public_doc`, `company_doc`, `our_code`, `resolved_issue`.
`core_code` is reserved, not a delivered corpus. These tags distinguish
sources, not authenticated ACLs. Site isolation and per-user authorized
retrieval are target requirements; see `ARCHITECTURE.md` and `SECURITY.md`.
