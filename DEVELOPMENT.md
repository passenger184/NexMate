# DEVELOPMENT.md — Environment & Workflow

Development runbook for NexMate. `ARCHITECTURE.md` is the sole canonical
HLD; `README.md` provides onboarding, `EVALUATION.md` defines acceptance,
and `progress/` records dated evidence. Commands below describe local
development, not a certified production deployment.

## Environment (WSL/Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy and edit the env file — sets which generation provider/model to use
cp .env.example .env

# Run the FastAPI service
uvicorn service.main:app --host 127.0.0.1 --reload --port 8000
```

Do NOT install Ollama inside WSL if it's already installed and running on
Windows — see "Using Windows-hosted Ollama from WSL" below. Only run the
`curl ... ollama.com/install.sh` step if you specifically want a *second*,
WSL-local Ollama instance instead.

## Authenticated boundary configuration

Configure the boundary before using the service commands above. These are
operator instructions, not evidence of installation or production approval.
The original configuration documentation did not inspect actual `.env` or
site settings. In the 2026-09-17 acceptance session, the operator shell read
the adjacent `frappe_docker` `.env` through name-filtered output; nonsecret
values were visible and are not reproduced here. The target repository's
actual `.env` was not read; no credentials were used or changed.

| Inference environment key | Default and behavior |
|---|---|
| `NEXMATE_ENV` | `production`; only exact `development` can enable the exemption. Unknown values emit a safe diagnostic and never enable it. |
| `NEXMATE_DEV_UNAUTHENTICATED` | `0`; only exact `1` together with `development` allows missing-header requests. |
| `NEXMATE_SERVICE_KEY` | Unset; required for protected production calls. Exactly 64 hexadecimal characters, non-repetitive, generated from at least 32 random bytes. Blank is invalid. |
| `NEXMATE_FRAPPE_SITE` | Unset; gateway calls require an exact match to the authoritative `frappe.local.site`. Not a public URL, tenant selector or repository mapping. |

| Server-side Frappe site configuration | Default and behavior |
|---|---|
| `nexmate_service_key` | No usable default; must be the identical inference credential. Missing/invalid values refuse even if inference development access is enabled. |
| `copilot_api_base` | Required by the gateway; trusted HTTP(S) service base, resolved from the Frappe server. No URL credentials, query or fragment. Gateway appends `/orchestrate`, does not forward browser targets and does not follow redirects. |
| `nexmate_developer_roles` | `[]`; a JSON list of explicit role names. Only a matching actual user role selects developer persona. Malformed mappings log a safe code and use employee. No implicit Administrator/System Manager elevation. |
| `nexmate_inference_timeout` | `300` seconds; finite JSON number strictly greater than 0 and at most 900. Strings, booleans and null are invalid. |

The gateway uses a 5-second HTTP connect timeout and the configured read
timeout. The read timeout limits waiting for response data, not total
request duration. It supplies neither cancellation nor retry semantics;
HTTP, timeout, transport, malformed/oversized-response and redirect failures
produce sanitized gateway errors with no unauthenticated or direct-browser
fallback. No automatic gateway retry is added. Upstream response size is
bounded to 1 MiB. Desk start-fresh does not cancel work already in progress.

### Provisioning, rotation and safe rollback

Provision a fresh secret through a trusted cryptographic random generator
and protected operator configuration workflow. Do not use a memorized value,
example/test credential or a repeated pattern. Runtime validation rejects
64-character hex strings composed of repeated blocks of length
1, 2, 4, 8, 16 or 32 (case-insensitive pattern check); this strength-shape
check cannot certify randomness. Credential comparison is constant-time over
exact bytes, so retain identical spelling/case on both servers.

Keep the credential only in protected inference environment configuration
and Frappe's server-side `site_config.json`. Do not print it in evidence,
command history, logs, prompts, boot data, browser storage or bundles; do
not stage/commit it. Use protected private transport and retain localhost
binding unless separately authorized network exposure is required. The
existing boot helper still exports the legacy address, not the key; Desk
ignores that address. The gateway has no address fallback from boot defaults.

Rotate both server settings during a controlled maintenance window and
reload the affected processes/configuration. There is one accepted key, no
secondary-key or unauthenticated fallback: a mismatch refuses service calls
and the gateway returns a sanitized failure. Review rollback by retaining
inference authentication and backend chat-only enforcement, or disabling
Desk chat. Never restore an unauthenticated inference deployment, send the
key to a browser or enable production development bypass. Source review and
synthetic mismatch/failure tests are not a performed deployment rollback.

### Explicit standalone development and health

For unauthenticated preview or the credential-free legacy examples in
README, enable BOTH settings on the local service:

```bash
NEXMATE_ENV=development NEXMATE_DEV_UNAUTHENTICATED=1 \
  uvicorn service.main:app --host 127.0.0.1 --port 8000
```

Before starting, remove the blank `NEXMATE_SERVICE_KEY=` line copied from
`.env.example` and unset any inherited environment value, or supply a valid
key. Merely leaving the line blank is invalid; merely unsetting the shell
variable is insufficient if dotenv reloads a blank assignment. The exemption
requires no credential header and a valid or genuinely unset key. Supplied
invalid/empty/duplicate/nonmatching credentials still refuse in development;
a supplied header with an unset key cannot authenticate. Origin, Host,
forwarded headers, browser path and localhost never enable this exemption.

Exact `/health` always returns only `{"status":"ok"}`, including with
missing/invalid key configuration. It is public minimal liveness, not
readiness: it does not test providers, ERPNext, authorization or indexes.
The ordinary service startup still loads the index. Every other HTTP path
passes authentication, including `/ask`, `/orchestrate`, all current
`/tools/*`, `/ui` assets, API docs, unknown paths and OPTIONS; `/health/` and
other prefix matches are not exempt.

### Desk scope and transitional state

Desk uses only authenticated Frappe `erpnext_ai_copilot.api.ask`, relying on
standard non-guest authentication and session CSRF checks. The server
constructs user/site/mode, the retrieval authorization scope, and exact
`execution_scope="chat-only"`; inference requires service authentication
and validates the complete envelope and fixed site before history/routing/
retrieval. Partial or invalid envelopes cannot downgrade to legacy mode,
even under development exemption.

Backend request-local `chat_only` enforcement denies code and ERPNext
handlers before entry in both personas, including natural-language,
troubleshooting, rewritten follow-ups and degraded routing. Incidental
ERPNext version lookups are suppressed; versions report unavailable.
Existing conversational/cited cached RAG continues, not live file tools.
Retrieval is authorization-scoped (site/visibility/roles pre-filtered
before fusion), not full ERPNext permission parity. There are no gateway
tool/proposal/approval/reset operations. The disabled Desk mode selector
cannot override server persona.

Desk slash commands and stale approval/rejection cards are unavailable.
Desk start-fresh resets the owned server-side thread (local clear only when
there is none) and starts a fresh owned conversation; the transcript
restores from the owner's thread on reload. Old responses are ignored
locally, not cancelled remotely. Caller-owned `session_id` continuity is
retired: legacy identifiers are refused explicitly, and the JSON session
store is removed (leftover files are never read; preview is stateless).
Preview retains tool behavior behind the dual opt-in, never as Desk fallback.

This increment is not full G2/M2, production readiness, a corpus permission
grant, release/production-write approval or private-data cloud consent.
On 2026-09-17 the user explicitly authorized the handoff (task 7.3) despite
pending Bench verification (6.3). The next milestone requires a separately
approved `frappe-owned-conversation-state` change: Frappe-owned persistent
records, authenticated user ownership, site association, persistence across
inference restarts, removal of caller-controlled session ownership, explicit
migration/compatibility and eventual removal of the JSON store. This is a
handoff only, not successor creation or implementation; remaining HLD
contracts and real Bench/Desk evidence stay open.

## Using Windows-hosted Ollama from WSL

Ollama on Windows listens on `127.0.0.1:11434` by default, which is
Windows' own loopback address — WSL2 is a separate lightweight VM and
cannot reach `127.0.0.1` on Windows through that address by default (this
is different from the reverse direction: Windows *can* reach WSL2 services
via `localhost` automatically). Two things need to happen:

1. **Make Ollama listen on all interfaces, not just localhost.** On
   Windows, set an environment variable and restart Ollama:
   - Open "Edit environment variables for your account" (Windows search),
     add a new variable `OLLAMA_HOST` with value `0.0.0.0`.
   - Quit Ollama fully (check the system tray) and reopen it so it picks up
     the new setting.

2. **Find the address WSL should use to reach Windows**, and try in this
   order:
   - First just try `http://localhost:11434` from WSL (`curl
     http://localhost:11434` ) — recent WSL versions with "mirrored"
     networking mode make this work directly. If you get a response, use
     `OLLAMA_BASE_URL=http://localhost:11434` in `.env` and you're done.
   - If that fails, get the Windows host IP from inside WSL:
     ```bash
     cat /etc/resolv.conf | grep nameserver
     ```
     Use that IP as `OLLAMA_BASE_URL=http://<that-ip>:11434` in `.env`.
   - Verify with `curl http://<that-ip>:11434` from WSL — you should get
     Ollama's "Ollama is running" response.

Once `OLLAMA_BASE_URL` in `.env` points at a reachable address, `litellm`
will use it automatically for `GENERATION_PROVIDER=ollama` — no code
changes needed.

## Switching the generation provider/model

Edit `.env` and restart the service — nothing else changes:

```bash
# Local, via your existing Windows Ollama install
GENERATION_PROVIDER=ollama
GENERATION_MODEL=llama3.1:8b
OLLAMA_BASE_URL=http://localhost:11434   # or the host IP, see above

# OR: cloud, via Claude
GENERATION_PROVIDER=anthropic
GENERATION_MODEL=claude-sonnet-4-5
ANTHROPIC_API_KEY=sk-ant-...

# OR: cloud, via OpenAI
GENERATION_PROVIDER=openai
GENERATION_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

To try a different local Ollama model, pull it once (on Windows, since
that's where Ollama runs): `ollama pull mistral:7b`, then set
`GENERATION_MODEL=mistral:7b` in `.env` and restart the service. No
reinstall of Ollama itself is ever needed to change or add models.

## Coding standards

- Python: type hints on public functions, docstrings on modules and
  non-trivial functions.
- No bare `except:` — catch specific exceptions, log and surface failures
  per `AGENTS.md`'s "fail loud" principle.
- Config (model names, chunk size, k, file paths) lives in one place
  (`config.py` or `.env`), not scattered as magic numbers.
- Commit incrementally per milestone (ingestion working, retrieval working,
  API working, UI working) — not one giant commit at the end.

## Project structure

Historical phase specs preserve their original layouts, not current work
prohibitions. The accepted sequence was public RAG, code tools, company
knowledge, memory, ERPNext reads, orchestration, employee mode, and ERPNext
writes (Phases 1–8). Follow `ROADMAP.md` and the approved OpenSpec change
for post-roadmap scope; `ARCHITECTURE.md` alone defines the HLD.

## Release and deployment lifecycle — target, not delivered

The approved direction is one NexMate application source for ordinary Bench
and Docker, with authenticated Frappe control/state ownership and separate
private inference. Docker packaging, root-repository Bench installation,
real Desk assets and install/update parity remain unverified; a proxy is
not a substitute for the target authorization boundary.

Future release gates: Git source -> packaged Frappe app -> tests/lint and
compatibility checks -> Bench/Docker install/update plus patches/migrate ->
backup/restore and rollback verification -> explicitly approved release.
These are future checks, not commands run or gates passed by this document.
`frappe_app/pyproject.toml` currently uses dynamic versioning from
`frappe_app/erpnext_ai_copilot/__init__.py` (`0.1.0`) and declares Frappe
`>=15`, while the product targets v16. The supported version matrix,
versioning policy and monorepo-to-Bench packaging path remain unresolved;
normal Frappe patches/migrate are the target migration mechanism.
See `EVALUATION.md` for acceptance and `docs/OPEN_SOURCE_LAUNCH_SPEC.md`
for the future launch checklist. Release approval does not authorize
production writes; `SECURITY.md` still governs them.

## Running the test set

See `EVALUATION.md` for the question set, historical phase acceptance and
future production gates. Test results must identify their date and scope;
mocked routing or stub-DOM checks are not real Bench/Desk verification.

Use the configured project `.venv`, not an unrelated system interpreter.
The documented Python discovery command after activating it is:

```bash
python -m unittest discover -s tests
```

The existing Node harness and bundle syntax check are:

```bash
node frappe_app/public/js/copilot.bundle.test.js
node --check frappe_app/public/js/copilot.bundle.js
```

## Index generations and egress grants (operator runbook)

Retrieval serves one active index generation (`data/generations/`, pointer
`active.json`); the pre-generation store is `gen-0-legacy`. The steps below
are operator actions from the repo root with the project `.venv` (never from
Bench containers):

```bash
# 1. Backfill ACL metadata onto the live collection (vectors untouched),
#    keeping a JSONL metadata backup for rollback:
.venv/bin/python -c "
from rag import generations
generations.backfill_acl_metadata('erpnext_docs', 'frontend',
    backup_path='/tmp/gen1-metadata-backup.jsonl')"

# 2. Seed a staged copy, write its manifest, verify, and publish:
.venv/bin/python -c "
from rag import generations
from rag.retriever import current_fingerprint
fp = current_fingerprint()
generations.seed_staged_from('erpnext_docs--gen-2', None)  # or drop corpora
generations.write_manifest('gen-2', parent='gen-1-m4', sources={...},
    fingerprint=fp, acl_schema_version=1,
    counts=generations.count_by_source(generations._client().get_collection('erpnext_docs--gen-2')))
generations.publish_generation('gen-2',
    lambda: generations.verify_generation('gen-2', fp))"
```

Scoped rebuilds drop corpora in `seed_staged_from`, then run the matching
pipeline with `--collection <staged>` (`ingestion/chunk_and_embed.py`,
`ingestion/ingest_project.py --site <site>`). Rollback reactivates the
parent generation (`rollback_generation()`); a generation retired by
`revoke_generation()` refuses both rollback-to and republication. The
running service picks up pointer changes on the next retrieval without a
restart; verify with per-corpus counts plus the fixture suites in
`tests/test_acl_retrieval.py`.

Egress grants default to the configured generation provider's standard
purposes plus local embeddings/eval; anything else is denied until
explicitly granted. Production cloud grants remain a `DECISIONS.md`
approval — never infer them from configuration, and never authorize a paid
call by testing (the marker harness uses mocked transports only).

For the boundary's offline verification, dotenv loading must be disabled
(`PYTHON_DOTENV_DISABLED=1`) and model/network integrations kept mocked;
these commands do not authorize live model or deployment checks. Reported
2026-09-17 results and remaining review gates are in `progress/CURRENT.md`.
The user-supplied 2026-09-17 tooling inspection covered root/nested
pyproject/package metadata, Makefiles, tasks, CI, scripts and documentation.
`frappe_app/pyproject.toml` contains packaging only; `.opencode` package
dependencies are agent tooling, not application lint/typecheck tooling.

| Application check | Configuration status |
|---|---|
| Python lint | Not configured |
| Python typecheck | Not configured |
| JavaScript lint | Not configured |
| JavaScript typecheck | Not configured |

## Durable tool execution and audit ledger — M5 cutover (operator runbook)

Durable execution replaces process-local RAM proposals with Frappe-owned
`NexMate Tool Proposal` records (DocTypes `NexMate Tool Proposal` and
`NexMate Audit Entry`, plus `data/durable_proposals/` and `data/audit_ledger/`
fallback for offline tests). The cutover below is an operator action from the
repo root with the project `.venv` (never from Bench containers); it does
not authorize a live Bench migration, restart, or production-write approval.

```bash
# 1. Verify the new DocTypes and fallback stores are present (no DB write yet)
ls frappe_app/erpnext_ai_copilot/erpnext_ai_copilot/doctype/nexmate_tool_proposal/
ls frappe_app/erpnext_ai_copilot/erpnext_ai_copilot/doctype/nexmate_audit_entry/
ls tools/contracts.py  # explicit tool contracts frozen

# 2. In a Bench with the app installed, migrate the DocTypes (creates tables)
bench --site <site> migrate
# or: bench --site <site> --force migrate  # only if the site is already on current

# 3. Seed the audit ledger fallback (no production grants changed)
#    No separate seed step is required: the ledger is append-only via
#    proposals/audit modules. Verify fallback is writable:
.venv/bin/python -c "from frappe_app.erpnext_ai_copilot import proposals, audit; proposals.clear_fallback(); audit.clear_fallback(); print('fallback ready')"

# 4. Verify durable lifecycle offline (dotenv disabled, mocked transports):
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m unittest tests.test_durable tests.test_audit_ledger tests.test_debug_transparency tests.test_legacy_replacement tests.test_contracts
# Expected: 35 tests OK (1 skipped due to dirty tree when the working tree is not clean)

# 5. Legacy RAM proposals are not migrated — they become durably expired on first
#    restart after cutover. The prior JSONL `data/erpnext_writes.jsonl` remains
#    readable for history, not authoritative. No silent carryover.
```

Legacy RAM proposals are not imported; they are treated as `expired` and
re-proposed via the durable path, preserving the immutable-payload guarantee.
Retention and repair are Frappe-owned: audit entries are redacted and
retention/deletion per policy is enforced via the `NexMate Audit Entry`
DocType; a proposal that succeeds but whose audit cannot persist is marked
`audit_pending` and reconciled by a repair job before claiming a complete
transaction. The confined code/Git executor remains the only path that can
write a file and commit (root-contained, tracked-not-ignored, clean-tree,
per-edit atomic commit for exactly the approved diff); inference never
acquires ambient write authority. No production grants, MCP, Workbench, or
search-engine changes are part of this cutover.

Per explicit user acceptance, task 6.1 is complete with these four checks
reported as **not configured**, not passed. Do not invent/install a tooling
stack or request commands again for this acceptance. Syntax checks are not
lint/typecheck. Supplied offline evidence: 191 Python tests OK in 1.628s,
64 Node checks pass (26 preview + 38 Desk), and `node --check` passes for
both bundle and harness. Python emitted a Starlette/httpx deprecation
warning; no dependencies were changed. Exact command and evidence limitations
are recorded in `progress/CURRENT.md`; no tests were rerun by this docs pass.

### Bench verification limitation — 2026-09-17

User-supplied inspection found a Bench at
`/home/passenger/projects/frappe_docker/development/frappe-bench`, with apps
`crm`, `erpnext`, `frappe`, `hrms` and `sites/development.localhost`, but no
`erpnext_ai_copilot` app directory. `bench`, `chromium` and `google-chrome`
were absent from PATH. The observed `ss` output showed only DNS listeners,
not app listeners; the bounded no-proxy curl to `http://127.0.0.1:8081`
returned exit 7, connection refused, HTTP 000. Docker ps/version/compose
could not execute `/usr/bin/docker` (Input/output error), so container
status cannot be determined from that CLI; this is not evidence of no
containers globally.

Task 6.3 remains unchecked: all real authentication/CSRF, Desk actions,
assets, preview and minimal-health integration checks remain unverified.
Synthetic tests do not substitute. No install, start, configuration change,
migration, login, browser, model or ERP data action was performed. The
user-authorized acceptance/handoff records 20/21 tasks complete, with only
6.3 open; it does not pass full G2/M2 or production readiness.
