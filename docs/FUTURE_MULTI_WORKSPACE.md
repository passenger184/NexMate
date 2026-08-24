# docs/FUTURE_MULTI_WORKSPACE.md — Deferred Direction, Not Current Scope

**Status: not on the active roadmap. Do not build any of this until the
user explicitly reopens it.** This exists so the reasoning already worked
through isn't lost, not as something to start on.

## The eventual idea

Once the single-project system (RAG + live code agent + company knowledge)
is mature and the user is happy with it, expand to support multiple
projects: the user runs several separate local Frappe/ERPNext projects
(Docker'd benches/sites) and wants the tool to become installable/portable
— one shared service that knows about multiple **workspaces**, each
representing one project, auto-detecting which one it's currently talking
to.

## The shape it would take, when it's time

- **Public knowledge** (ERPNext/Frappe docs) indexed once, shared read-only
  across all workspaces — never re-scraped or re-embedded per project.
- **Workspace knowledge** (a project's custom app source, company docs)
  gets its own Chroma collection per `workspace_id`, registered via a
  setup step — not auto-discovered.
- Every request carries a `workspace_id`; the service combines shared
  public knowledge with that workspace's collection at query time.
- The Frappe sidebar app derives `workspace_id` automatically from the site
  it's running on (e.g. `frappe.local.site`).
- One shared service instance, not one per project — avoids duplicating
  the public knowledge index and duplicate port/instance management.
- The live code read/edit agent's project-root scoping (see `SECURITY.md`)
  extends naturally to workspace-root scoping — same principle, just keyed
  by workspace instead of a single fixed root.

## Why deferred rather than built now

The user chose to keep this to one project until the core system (RAG
quality, live code editing, company knowledge) is proven. Building
multi-workspace support now would mean adding routing/registry complexity
before there's a single well-working instance to generalize from.
