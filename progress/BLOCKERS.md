# progress/BLOCKERS.md — Open Blockers

List anything that stopped forward progress and needs a human decision.
Remove an entry once resolved, and note the resolution in
`progress/JOURNAL.md`.

## Open

(none yet)

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

