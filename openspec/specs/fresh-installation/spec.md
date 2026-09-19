# fresh-installation Specification

## Purpose
An external developer can obtain NexMate from its public GitHub repository and install it on a fresh Bench/site via the normal Frappe lifecycle, without developer-local state.

## Requirements

### Requirement: Fresh-clone Bench lifecycle succeeds
A fresh `git clone` of `passenger184/NexMate` (no `~/ERPNext-AI` on `PYTHONPATH`) SHALL support `bench get-app <clone>` (or `file://` with `apps.json` directory handling) → `bench --site <fresh-site> install-app erpnext_ai_copilot` → `bench --site <fresh-site> migrate` → DocTypes `NexMate Tool Proposal`, `NexMate Audit Entry`, `NexMate Conversation`, `NexMate Conversation Turn` are present and `tabNexMate Tool Proposal` etc. have `0` rows before any test.

#### Scenario: Fresh site has NexMate DocTypes
- **WHEN** the fresh-clone lifecycle has completed `migrate`
- **THEN** `bench --site <fresh-site> execute 'frappe.get_all("DocType", filters={"name":["like","NexMate%"]})'` returns 4 rows and `SHOW TABLES LIKE 'tabNexMate%'` returns 4 tables

### Requirement: Fresh installation is location-independent
The fresh installation SHALL NOT depend on `~/ERPNext-AI`, `config.PROJECT_ROOT`, WSL `172.30.224.1`, `localhost:8081`, or `frappe_docker_copilot_test` container names at runtime. The Frappe application SHALL resolve its code root via `frappe.get_app_path` or `site_config` `nexmate_code_root`, never via a hard-coded developer path.

#### Scenario: No developer path in runtime
- **WHEN** the fresh site creates a durable proposal via `bench --site <fresh-site> execute erpnext_ai_copilot.api.create_tool_proposal`
- **THEN** the call succeeds without `ModuleNotFoundError: No module named 'config'` and the stored `expiry` is naive UTC (no `+00:00`)

### Requirement: Installation is documented and matches verification
The repository SHALL document the verified `bench get-app`/`install-app`/`migrate` workflow in `README.md`/`DEVELOPMENT.md`/`docs/OPEN_SOURCE_LAUNCH_SPEC.md` exactly as it was fresh-clone verified. The documentation SHALL NOT describe a `docker cp` shortcut as the supported open-source installation.

#### Scenario: Documentation matches verified workflow
- **WHEN** an external developer follows `README.md` installation steps
- **THEN** they obtain the same `DocTypes` and `bench list-apps` result as the fresh-clone verification without needing `~/ERPNext-AI`

### Requirement: Existing architecture remains intact
The packaging change SHALL NOT modify Frappe control-plane, FastAPI, RAG, provider, security, proposal/audit, site-isolation, or egress architectures. M5 remains closed.

#### Scenario: Architecture unchanged
- **WHEN** `git diff --stat` is inspected after the packaging change
- **THEN** no `service/`, `rag/`, `tools/`, `config.py`, `orchestrator.py`, or proposal/audit lifecycle files are modified beyond packaging adapters

### Requirement: M5 remains closed
M5 (`durable-tool-execution-audit`) SHALL remain `archived` and `M5 CLOSED` (commit `c86fda5`). Packaging is `M6` scope and SHALL NOT reopen `M5`.

#### Scenario: M5 still archived
- **WHEN** `openspec list --json` and `git log --oneline` are inspected after M6 proposal creation
- **THEN** `durable-tool-execution-audit` is in `openspec/changes/archive/` and `ROADMAP.md` active pointer is `M6`
