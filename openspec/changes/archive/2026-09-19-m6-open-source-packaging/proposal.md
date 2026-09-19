## Why

M5 is formally CLOSED (commit c86fda5, 20/20 tasks, hardened, archived), but the NexMate Frappe application still lives under `frappe_app/` as a monorepo subdirectory (`frappe_app/erpnext_ai_copilot/` + `frappe_app/public/` + `frappe_app/pyproject.toml`). An external developer cannot yet answer whether `bench get-app <repo>` alone will discover, install, and migrate the app on a fresh site without depending on the original `~/ERPNext-AI` working tree, WSL/Docker-specific paths, or manual `docker cp`. M6 must make that packaging/installation contract explicit and verifiable.

## What Changes

- **Investigation (read-only, before any structural change):** determine what Frappe/Bench considers an application repository, how `bench get-app` obtains and identifies an application, whether a repository with the app under `frappe_app/` can be consumed directly, whether a subdirectory-based app can be installed via a supported workflow (e.g., `apps.json` `directory` field or `bench get-app <repo> --branch` with subdir), whether current metadata (`hooks.py` app_publisher/description/email/license, `pyproject.toml` name `erpnext_ai_copilot`, `modules.txt`) is sufficient, whether `frappe_app/erpnext_ai_copilot` is internally self-contained (no `config/tools/service/rag` imports, no `~/ERPNext-AI` or `/tmp/opencode` paths), and whether restructuring would break existing Docker `docker cp` + `bench migrate` flow.
- **Decision (evidence-driven, minimum-viable):** evaluate **Option A — Preserve monorepo** (`NexMate/` with `frappe_app/` + `service/` + `rag/` + `tools/` + `evaluation/` + `ingestion/`) vs **Option B — Change repository/app layout** (e.g., move Frappe app to repo root or add root shim `pyproject.toml`/`setup.py` that re-exports `frappe_app`). Choose only if evidence shows current layout prevents normal `bench get-app`/`install-app`/`migrate`/`DocTypes`/`imports`/`runtime` without developer-specific paths. Document affected imports, tests, Docker/runtime paths, docs, and backward-compatibility.
- **Implementation (minimum required packaging changes only):** apply the chosen packaging fix (e.g., add root `pyproject.toml` shim, or `apps.json` directory handling, or `frappe_app/` → repo-root move with import shims) and update `hooks.py`/`pyproject.toml`/`MANIFEST.in`/`modules.txt` only if required. Keep Frappe control-plane, FastAPI, RAG, provider, security, proposal/audit, and site-isolation architectures intact.
- **Verification (fresh-clone):** fresh `git clone passenger184/NexMate` on a clean filesystem (no `~/ERPNext-AI` on `PYTHONPATH`) → `bench get-app`/`install-app`/`migrate` → `DocTypes` (`NexMate Tool Proposal`, `NexMate Audit Entry`, `NexMate Conversation`, `NexMate Conversation Turn`) → `python -c "import erpnext_ai_copilot.proposals"` without repo root → runtime start → no dependency on `~/ERPNext-AI`, WSL, Docker names, or hard-coded paths. Distinguish offline, controlled Frappe, and fresh-clone levels.
- **Documentation:** publish the verified external-developer installation workflow (clone → bench lifecycle → DocTypes → imports → runtime) and record remaining limitations.

## Capabilities

### New Capabilities
- `frappe-app-packaging`: Frappe application packaging, Python package discovery, app metadata, Bench-compatible repository layout, and fresh-clone installation contract.
- `fresh-installation`: Bench lifecycle for a fresh site (`get-app` → `install-app` → `migrate` → `DocTypes` → `imports` → `runtime`) without developer-local paths.

### Modified Capabilities
- `frappe-api-gateway`: installation/packaging changes must not regress gateway authentication, site binding, or proposal/audit flows (no requirement text change, but packaging verification must not break this capability).

## Impact
- **Frappe app:** `frappe_app/` layout, `pyproject.toml`/`setup.py`/`MANIFEST.in`/`hooks.py`/`modules.txt` only if evidence requires; no `service/`/`rag/`/`tools/`/`config` move into app beyond already-decoupled M5.
- **Bench/Docker:** `bench get-app`/`install-app`/`migrate`/`build` flow, `apps.txt`/`sites/` handling, `frappe_docker` custom image `apps.json` handling; no `compose.yaml`/`Dockerfile` redesign, no `localhost:8081`/`172.30.224.1` hardcoding.
- **Docs:** `README.md`/`DEVELOPMENT.md`/`docs/OPEN_SOURCE_LAUNCH_SPEC.md` installation instructions only after verified workflow.
- **Out of scope:** production deployment redesign, CI/CD, container publishing, cloud infra, MCP/Workbench, model training, RAG redesign, M5 changes (M5 remains closed).
