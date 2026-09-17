# NexMate Frappe sidebar

Frappe app source for the NexMate Desk sidebar. The technical package/app
identifier remains `erpnext_ai_copilot`; this is not a runtime rename.
`ARCHITECTURE.md` at the repo root is the sole canonical HLD;
`docs/UI_SPEC.md` owns interaction structure and
`docs/UI_VISUAL_SPEC_updated.md` is the canonical blue visual reference
(superseding historical amber `docs/UI_VISUAL_SPEC.md`).

Real Bench installation, package/asset discovery and Desk integration
remain unverified. The standalone FastAPI preview is not proof of them.

Files that matter:

- `hooks.py` — `app_include_js`/`app_include_css` (the sidebar bundle) and
  `extend_bootinfo` (exposes the service URL to the client)
- `boot.py` — reads `copilot_api_base` from `site_config.json`
- `public/js/copilot.bundle.js`, `public/css/copilot.css` — the UI

Historical development setup outline, only after arranging the app source
in the Bench (see root `README.md`); not a verified installation recipe.
Metadata is nested at `frappe_app/pyproject.toml`; do not assume
`bench get-app <repo-url>` against the repository root works:

```bash
pip install -e apps/erpnext_ai_copilot
bench build --app erpnext_ai_copilot
bench --site <site> install-app erpnext_ai_copilot
bench --site <site> set-config copilot_api_base "http://<host>:8000"
bench --site <site> clear-cache
```

The FastAPI service lives in this repo's `service/`; local development
uses uvicorn as described in the root README. Currently the boot URL is
browser-visible and the bundle calls FastAPI directly, not through an
authenticated Frappe control plane. That boundary, Frappe-owned history,
streaming/realtime and same-source Bench/Docker release parity are targets,
not delivered features. `pyproject.toml` declares Frappe `>=15` and dynamic
app versioning (`0.1.0` currently); the v16 product target is not a verified
multi-version support claim.
