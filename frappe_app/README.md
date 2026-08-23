# erpnext_ai_copilot

Minimal Frappe app providing the ERPNext AI Copilot Desk sidebar.

Files that matter:

- `hooks.py` — `app_include_js`/`app_include_css` (the sidebar bundle) and
  `extend_bootinfo` (exposes the service URL to the client)
- `boot.py` — reads `copilot_api_base` from `site_config.json`
- `public/js/copilot.bundle.js`, `public/css/copilot.css` — the UI

Install inside a bench (see the repository root `README.md`):

```bash
pip install -e apps/erpnext_ai_copilot
bench build --app erpnext_ai_copilot
bench --site <site> install-app erpnext_ai_copilot
bench --site <site> set-config copilot_api_base "http://<host>:8000"
bench --site <site> clear-cache
```

The FastAPI service itself lives in this repo's `service/` — run it with
uvicorn as described in the root README.
