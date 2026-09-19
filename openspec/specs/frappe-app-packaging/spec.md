# frappe-app-packaging Specification

## Purpose
NexMate is distributed as a normal Frappe application from its public GitHub repository, installable via standard Bench tooling without developer-local paths.

## Requirements

### Requirement: Repository is a Bench-discoverable Frappe application
The NexMate repository SHALL be discoverable as a Frappe application via standard `bench get-app` tooling. The repository SHALL contain `pyproject.toml` (or `setup.py`) with `project.name` `erpnext_ai_copilot` and `tool.bench.frappe-dependencies` at a location that `bench get-app` can identify without requiring a developer-local `~/ERPNext-AI` path, WSL-specific address, or Docker-specific mount.

#### Scenario: Bench discovers the application
- **WHEN** an external developer runs `bench get-app <NexMate repository URL>` (or `bench get-app file://<fresh clone>` with `apps.json` `directory` handling where supported) on a clean Bench
- **THEN** Bench reports the application `erpnext_ai_copilot` as recognized and clones it without requiring `~/ERPNext-AI` on `PYTHONPATH`

### Requirement: Application metadata is complete and valid
The Frappe application SHALL declare `app_name`, `app_title`, `app_publisher`, `app_description`, `app_email`, `app_license` in `frappe_app/erpnext_ai_copilot/hooks.py` and `project.name`/`dynamic version` in `frappe_app/pyproject.toml` such that `frappe.utils.change_log.get_versions` and `bench --site <site> list-apps` succeed after `bench --site <site> install-app` and `bench --site <site> migrate`.

#### Scenario: Versions are readable after install
- **WHEN** `bench --site <fresh-site> migrate` has completed
- **THEN** `bench --site <fresh-site> execute 'frappe.utils.get_installed_apps_info()'` returns `erpnext_ai_copilot` with `app_title` and `app_description` without `TypeError: 'NoneType' object is not subscriptable`

### Requirement: Frappe application is self-contained
The Frappe application `frappe_app/erpnext_ai_copilot/` (including `api.py`, `proposals.py`, `audit.py`, `debug.py`, `conversations.py`, `boot.py`, `hooks.py`, `erpnext_ai_copilot/doctype/*`, `public/`) SHALL import without requiring repository-root `config.py`, `tools/`, `service/`, `rag/`, `evaluation/`, `ingestion/`, or developer-local absolute paths. Its fallback durable storage (when `NEXMATE_DURABLE_FALLBACK` is set) SHALL be app-local (`NEXMATE_DURABLE_DIR` or `frappe.get_site_path("private","files","nexmate_durable")` or `<app>/private/durable_fallback`), never `config.PROJECT_ROOT`/`/tmp/opencode`.

#### Scenario: Isolated import
- **WHEN** a fresh clone is checked with `PYTHONPATH` containing only `frappe_app` (not repo root) and `frappe` stubbed
- **THEN** `import erpnext_ai_copilot.proposals` and `import erpnext_ai_copilot.audit` succeed without `ModuleNotFoundError: No module named 'config'` or `tools`

### Requirement: No developer-local runtime paths in the Frappe application
The Frappe application SHALL NOT contain hard-coded `~/ERPNext-AI`, `/home/passenger/`, `172.30.224.1`, `localhost:8081`, `/tmp/opencode`, Docker container names (`frappe_docker_copilot_test`), or `frontend` as a hard-coded production site name. Any site-specific values SHALL be operator configuration (`site_config.json`, `NEXMATE_FRAPPE_SITE`, `copilot_api_base`).

#### Scenario: Path scan
- **WHEN** `grep -r` scans `frappe_app/erpnext_ai_copilot/*.py` for `~/ERPNext-AI`, `172.30`, `localhost:8081`, `/tmp/opencode`, `frappe_docker`
- **THEN** no matches are found (comments mentioning the mirror are allowed, imports are not)

### Requirement: Python package discovery is correct
The repository SHALL ensure `frappe_app/pyproject.toml` is at the location expected by the chosen `bench get-app` workflow (either repo root shim or `frappe_app/` subdirectory with `apps.json` `directory` handling). After `bench get-app`, `python -m py_compile frappe_app/erpnext_ai_copilot/*.py` and `bench --site <site> execute 'import erpnext_ai_copilot.api'` SHALL succeed without `PYTHONPATH` manipulation.

#### Scenario: Package discovery after get-app
- **WHEN** the application has been obtained via the documented `bench get-app` workflow
- **THEN** `bench --site <site> execute 'import erpnext_ai_copilot.api; print(api.__file__)'` prints a path under `apps/erpnext_ai_copilot/` and not under `~/ERPNext-AI`
