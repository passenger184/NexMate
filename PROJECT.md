# PROJECT.md — Product Definition

## What this is

An AI ERPNext Engineering & Support Assistant, embedded inside ERPNext as a
sidebar chat panel. Not a generic chatbot that happens to know ERPNext — a
tool-using assistant that understands this company's specific ERPNext
instance, its customizations, and its codebase.

## Product name

**NexMate** — "Your ERPNext AI Companion." Use this name in the UI header,
any greeting/intro text the assistant gives, and README/docs-facing
copy — replacing generic placeholders like "ERPNext copilot" wherever
they currently appear in the sidebar and service.

## Users

**Primary (now):** a developer doing ERPNext deployment and customization as
their day job — Developer/Admin mode.

**Future:** the wider dev team, then non-technical ERP end users —
Employee/User mode.

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

## Employee/User mode — representative questions (future phase)

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

Implementation note: one vector store with a `source_type` metadata tag
(`public_doc`, `company_doc`, `our_code`, `core_code`), filtered at query
time — not two parallel systems. See `ARCHITECTURE.md`.
