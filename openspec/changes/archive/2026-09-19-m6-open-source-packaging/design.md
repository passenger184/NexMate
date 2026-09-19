# Design: m6-open-source-packaging

## Context

See `proposal.md` (Why). M5 is closed (`c86fda5`, `20/20`, archived, `HEAD==origin/main`). The Frappe application is `frappe_app/erpnext_ai_copilot/` (`frappe_app/pyproject.toml` name `erpnext_ai_copilot`, `frappe_app/erpnext_ai_copilot/hooks.py` with `app_publisher/description/email/license`, `frappe_app/erpnext_ai_copilot/doctype/{4}`, `frappe_app/public/`). Host inference/service is `service/`, `rag/`, `tools/`, `config.py` (repo root), tested via `frappe_app/erpnext_ai_copilot/proposals.py` app-local imports (no `config/tools` in Frappe, proven by `tests/test_frappe_isolation.py`). The intended external-developer lifecycle is `bench get-app <repo> → bench --site <site> install-app erpnext_ai_copilot → bench --site <site> migrate → DocTypes → imports → runtime`, verified in `~/copilot/frappe_docker_copilot_test` via `docker cp` + `bench migrate` (Phase 3B, 4B-FIX), but **not** yet via a fresh `git clone` with no `~/ERPNext-AI` on `PYTHONPATH`. Whether `frappe_app/` subdirectory is directly consumable by `bench get-app`, and whether a root `pyproject.toml`/`setup.py` shim is required, is the investigation question.

## Goals / Non-Goals

**Goals:** Determine the Bench-compatible packaging model for the current monorepo (`frappe_app/` subdir vs repo-root app), choose the minimum viable fix only if evidence shows `bench get-app` cannot discover/install the app, keep `service/`/`rag/`/`tools/`/`evaluation/`/`ingestion/` outside the Frappe app (M5 hardening already decoupled), and prove fresh-clone install/migrate/import/runtime without developer-local paths (`~/ERPNext-AI`, WSL `172.30…`, `localhost:8081`, `frappe_docker_copilot_test` container names).

**Non-Goals:** Frappe control-plane, FastAPI, RAG, provider abstraction, security model, proposal/audit, site isolation, egress, production deployment, CI/CD, container publishing, cloud infra, MCP/Workbench, model training, M5 changes, general cleanup.

## Decisions

- **D0 — Investigation before structure (evidence-driven).** Run read-only `bench get-app` discovery checks (what Bench considers an app repo: `pyproject.toml`/`setup.py` at repo root, `apps.json` `directory` handling, `frappe --site` app list) and `grep` for hard-coded repo-root imports/paths before any move. If `bench get-app <repo>` with `frappe_app/` subdir fails to discover `erpnext_ai_copilot`, document exact error; only then choose structural change. *Alternative (assume monorepo is wrong)* rejected: violates minimum-change principle.

- **D1 — Preserve monorepo unless proven incompatible.** Option A (keep `NexMate/` with `frappe_app/` + `service/` + `rag/` + `tools/` + `evaluation/`) is preferred. Option B (move app to repo root, e.g., `pyproject.toml` at `~/ERPNext-AI/pyproject.toml` shim or `frappe_app/` → `./`) is only if `bench get-app` cannot consume `frappe_app/` directly. *Rationale:* `frappe_app/` already contains `pyproject.toml` (Flit, `project.name erpnext_ai_copilot`, `tool.bench.frappe-dependencies frappe>=15`) and `erpnext_ai_copilot/` package is self-contained (Phase 4A import isolation `PASS`); moving would churn imports, tests, Docker `COPY`, and docs without evidence.

- **D2 — Bench lifecycle boundary.** Fresh-clone verification is `git clone` (no `~/ERPNext-AI` on `PYTHONPATH`) → `bench get-app <clone>` (or `bench get-app file://<clone>` with `apps.json` `directory: frappe_app` if supported) → `bench new-site` → `bench --site <fresh-site> install-app erpnext_ai_copilot` → `bench --site <fresh-site> migrate` (creates 4 DocTypes) → `bench --site <fresh-site> execute` `import erpnext_ai_copilot.proposals` (no `config/tools`) → `bench --site <fresh-site> execute` `frappe.get_all("DocType", filters={"name":["like","NexMate%"]})` → runtime. *Alternative (skip fresh clone, reuse `~/copilot/frappe_docker_copilot_test`)* is `WARNING` (proves `docker cp` sync, not `bench get-app` portability).

- **D3 — Runtime location independence.** Frappe app must not import `config`, `tools`, `service`, `rag` (verified via `grep -rn "^import config"`). Fallback `NEXMATE_DURABLE_DIR` → `frappe.get_site_path("private","files","nexmate_durable")` → `app/private/durable_fallback` (no `~/ERPNext-AI`, no `/tmp/opencode`). `api.py` `_get_code_root` → `site_config nexmate_code_root` or `frappe.get_app_path` parent (never hardcoded `172.30…`/`localhost`). *Alternative (hardcode `PROJECT_ROOT=~/ERPNext-AI`)* rejected (fails fresh clone).

- **D4 — Portability vs developer convenience.** Existing `~/copilot/frappe_docker_copilot_test` (`pwd.yml` `frappe/erpnext:v16.33.0`, `sites:/home/frappe/frappe-bench/sites` volume, no `apps` mount) proves dev `docker cp` works, but fresh-clone must not depend on that `pwd.yml` or `172.30…` `OLLAMA_BASE_URL`. Docs must publish the `bench get-app` workflow that passed fresh-clone verification, not the dev `docker cp` shortcut.

## Risks / Trade-offs

- [Risk] `bench get-app` may not support `frappe_app/` subdirectory without `apps.json` `directory` or root shim → Mitigation: investigation will try both `bench get-app <repo>` and `bench get-app <repo> --branch` with subdirectory handling; if both fail, smallest fix is root `pyproject.toml` shim that re-exports `frappe_app` or moving `frappe_app/*` to root with import shims, tested via fresh clone.
- [Risk] Moving app to root churns `frappe_app/erpnext_ai_copilot` imports, `tests/test_frappe_isolation.py` `PYTHONPATH=frappe_app`, Docker `COPY frappe_app/`, and docs (`README`, `DEVELOPMENT`, `OPEN_SOURCE_LAUNCH_SPEC`). → Mitigation: prefer Option A (preserve) unless `bench get-app` evidence forces Option B; any move is a single commit with `git mv` and import fix, verified via `py_compile` + isolated import test.
- [Risk] Fresh-clone verification requires a clean filesystem and Bench (no `~/ERPNext-AI` on `PYTHONPATH`) → Mitigation: use `mktemp -d` + `git clone --depth 1` + `python -m venv` + `bench init` (or reuse `~/copilot/frappe_docker_copilot_test` with new site `test-fresh-clone` to avoid destroying `frontend`).

## Migration Plan

1. Investigation (read-only): `bench get-app` discovery, `pyproject.toml`/`setup.py` location, `apps.json` handling, `grep` for `~/ERPNext-AI`/`/tmp/opencode`/`172.30`/`localhost:8081`/`frappe_docker_copilot_test` in `frappe_app/`.
2. Decision: choose Option A or B with evidence; if Option B, specify exact structural change and affected paths.
3. Implementation: minimum packaging fix (shim or move), keep `service`/`rag`/`tools` outside app, update `pyproject.toml`/`MANIFEST.in`/`hooks.py`/`modules.txt` only if required, update `README`/`DEVELOPMENT` install instructions only after verification.
4. Verification: fresh `git clone` (no `~/ERPNext-AI`) → `bench get-app` → `install-app` → `migrate` → `DocTypes` → `import erpnext_ai_copilot.*` without repo root → runtime; record `frappe`/`erpnext`/`NexMate` versions, site name, commands, migration result, import result, logs, business-data `0` counts.
5. Rollback: `git restore` working tree (no commit yet); fresh-clone `mktemp` is deleted, no `frontend` site mutation beyond new `test-fresh-clone` site (which can be dropped).

## Open Questions

- Exact `bench get-app` support for `frappe_app/` subdirectory in the installed `frappe`/`bench` version (`v16.31.0`/`v16.33.0` in `~/copilot/frappe_docker_copilot_test`) — investigation will answer without changing specs/tasks.

## Decision Record (2026-09-19, apply phase)

- **Chosen: Option A — Preserve monorepo.** Evidence from 1.1–1.3 on this box: `bench` binary absent (`which bench` → not found), so plain `bench get-app <repo>` discoverability cannot be live-proven here; repo root has no `pyproject.toml`/`setup.py` (only `frappe_app/pyproject.toml` name `erpnext_ai_copilot`), so root-level discovery is not expected — the supported path is `apps.json` with `directory: frappe_app` for frappe_docker custom images plus `bench get-app <url>` followed by subdir handling where the Bench version supports it. `frappe_app/erpnext_ai_copilot` is self-contained (source `grep ^import config/tools/service/rag` → 0; isolated `PYTHONPATH=frappe_app` import of `proposals`+`audit` PASS; fallback `NEXMATE_DURABLE_DIR` → site private → app private, never `config.PROJECT_ROOT`; hard-coded path scan → 0 runtime hits, 1 allowed docstring mention). Metadata complete (`hooks.py` has all six app_* fields; `pyproject.toml` name correct; `modules.txt` present; 4 DocType dirs present). Moving the app to root would churn `tests/test_frappe_isolation.py` (`PYTHONPATH=frappe_app`), Docker `COPY frappe_app/`, and docs with no forcing evidence. Backward-compatibility: existing `docker cp` + `bench migrate` flow unchanged; `service/`/`rag/`/`tools/`/`config.py` stay outside the app (M5 boundary intact).
- **Option B status: N/A.** No `git mv`, no root shim, no `service`/`rag`/`tools` move. Minimal change set is `apps.json` (`directory: frappe_app`) + install docs only.
