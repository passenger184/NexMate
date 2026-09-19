# NexMate — Your ERPNext AI Companion

A tool-using AI assistant for Frappe v16 / ERPNext v16, with a Desk sidebar
implementation and standalone browser preview. The current single-project
system includes cited public/company retrieval and legacy code/ERPNext tools.
The implemented `authenticated-frappe-control-plane` boundary makes Desk
chat-only through authenticated Frappe; legacy tools remain separate behind
the inference authentication gate. Conversations still use transitional
caller-selected JSON sessions, not authenticated ownership. Historical
Phases 1–8 acceptance is not production readiness; final boundary reviews
and real Bench/Desk integration remain pending.

See `PROJECT.md` (product definition), `ARCHITECTURE.md` (the sole canonical
HLD, current versus approved target), `ROADMAP.md` (historical acceptance
and future gates), and `progress/CURRENT.md` (evidence and limitations).
`docs/PHASE_1_SPEC.md` preserves historical requirements, not current scope.
NexMate is the documentation-facing name; historical "NexPilot" references
and technical identifiers such as `erpnext_ai_copilot` are not runtime renames.

## Retrieval overview

Docs are crawled once from `docs.frappe.io` (its official `{url}.md`
markdown alternates) into `data/raw_docs/`, split heading-wise into
~400-token chunks, embedded locally with `BAAI/bge-small-en-v1.5`, and
stored in a persistent Chroma collection (`data/chroma_db/`). At query
time, FastAPI retrieves top-k chunks via hybrid keyword+vector fusion
(best per document), gates them by
similarity score into `high | low | no_match`, and generates an answer via
litellm using ONLY those chunks — provider/model configured entirely
through `.env`. Retrieval is authorization-scoped: every chunk carries
`site`/visibility metadata, the gateway envelope carries a Frappe-derived
scope, and candidates are pre-filtered before fusion (see
`openspec/specs/acl-aware-retrieval/spec.md`). This coarse-grained layer
is not full ERPNext permission parity. Index state advances through
versioned generations (`rag/generations.py`); all provider calls pass a
deny-by-default egress boundary (`rag/egress.py`).

## Requirements

- Linux or WSL2, Python **3.10+** (developed on 3.14)
- ~4 GB disk (embedding model ~130MB, crawled corpus + vector store small)
- A generation backend reachable over HTTP:
  - **Ollama** on any host (default config assumes Windows-hosted Ollama
    reached from WSL — see `DEVELOPMENT.md` "Using Windows-hosted Ollama
    from WSL"), **or**
  - any litellm-supported cloud provider (Anthropic/OpenAI/...) with an
    API key

## Setup (from a clean machine)

```bash
python3 -m venv .venv
source .venv/bin/activate

# Install CPU-only PyTorch FIRST to skip ~4GB of CUDA wheels you won't use:
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Then everything else (pinned):
pip install -r requirements.txt

# Configure the generation provider/model:
cp .env.example .env
$EDITOR .env
```

`.env` keys: `GENERATION_PROVIDER` (`ollama` default), `GENERATION_MODEL`,
`OLLAMA_BASE_URL` (only for ollama), plus `ANTHROPIC_API_KEY` /
`OPENAI_API_KEY` if using a cloud provider. Switching providers is a `.env`
edit + service restart — never a code change.

Verify your generation endpoint before first use:

```bash
curl $OLLAMA_BASE_URL        # should print: Ollama is running
```

## Ingest the documentation (once)

```bash
python -m ingestion.scrape_or_load_docs     # ~10 min, caches under data/raw_docs/
python -m ingestion.chunk_and_embed         # ~7 min, builds data/chroma_db/
```

Expected scale: ~1,836 sitemap URLs match the doc spaces; ~1,000 distinct
canonical pages survive dedupe; final index ≈ 7,410 chunks. The crawler
exits non-zero listing ~170 permanently-dead sitemap aliases in
`data/raw_docs/_failed_urls.txt` — that is expected (they're dead or moved
to other Frappe products), not a failure of the crawl itself.

`chunk_and_embed` drops and recreates the shared collection, including
company/resolution chunks added later. Treat this as a destructive rebuild,
not an incremental refresh; preserve and re-ingest the other corpora as
needed. See `ARCHITECTURE.md` for index freshness and rebuild limitations.

## Configure the authenticated boundary

Inference defaults to `NEXMATE_ENV=production` and
`NEXMATE_DEV_UNAUTHENTICATED=0`. Set `NEXMATE_SERVICE_KEY` to a
cryptographically random 32-byte secret represented as exactly 64 hexadecimal
characters. Blank, malformed and repetitive keys are rejected; shape checks
cannot prove randomness. Provision the identical value only in Frappe's
server-side `site_config.json` as `nexmate_service_key`. Never put it in
browser headers/storage, boot data, source control or diagnostic output.
See `DEVELOPMENT.md` for provisioning, rotation and fail-closed rollback.

Set `NEXMATE_FRAPPE_SITE` to exactly the authoritative `frappe.local.site`
identifier, not a guessed public hostname. Frappe also requires a trusted
server-configured `copilot_api_base`; the gateway appends `/orchestrate`.
`nexmate_developer_roles` defaults to `[]`: no implicit Administrator or
System Manager elevation. An explicit matching role selects developer
persona, not tool access or corpus permission. Optional
`nexmate_inference_timeout` is a finite JSON number in `(0, 900]` seconds,
default `300`; it is an HTTP read timeout, not total request duration,
cancellation or retry policy.

The example environment file contains a blank `NEXMATE_SERVICE_KEY=` line.
Replace it with a valid secret for authenticated operation. For the separate
unauthenticated local development workflow, remove that line entirely and
unset any inherited value, or configure a valid key. Blank is invalid, not
unset. Both exact development settings below are still required.

## Install the Frappe application (fresh Bench)

The Frappe application is `frappe_app/` (`frappe_app/pyproject.toml` name `erpnext_ai_copilot`). It is self-contained (`frappe_app/erpnext_ai_copilot` imports without `config`/`tools`, verified offline by `tests/test_frappe_isolation.py` and an isolated `PYTHONPATH=frappe_app` subprocess import). The repo root has no `pyproject.toml`/`setup.py`, so plain `bench get-app <repo-url>` against the repository root is not expected to discover the app; the supported path is the `apps.json` subdirectory method (frappe_docker custom image). For a fresh Bench/site (no `~/ERPNext-AI` on `PYTHONPATH`):

```bash
# apps.json (repo root; consumed by the frappe_docker custom-image build):
# {"apps": [{"url": "https://github.com/passenger184/NexMate", "branch": "main", "directory": "frappe_app"}]}

bench --site <fresh-site> install-app erpnext_ai_copilot
bench --site <fresh-site> migrate
# Verify DocTypes (no business writes):
bench --site <fresh-site> execute 'frappe.get_all("DocType", filters={"name":["like","NexMate%"]})'
# Expected: 4 rows (NexMate Tool Proposal, NexMate Audit Entry,
# NexMate Conversation, NexMate Conversation Turn) and 4 tables
# matching SHOW TABLES LIKE 'tabNexMate%'.
```

`frappe_app/` remains the monorepo subdirectory (`frappe_app/erpnext_ai_copilot/` + `frappe_app/public/` + `service/`/`rag/`/`tools/` outside the app). No `172.30.224.1`, `localhost:8081`, or `frappe_docker_copilot_test` container names are required. Verified live 2026-09-19 on site `test-fresh-clone` (bench 5.31.0, Frappe 16.31.0, app 0.1.0): `migrate` exit `0`, 4 DocTypes, 4 tables, `0` rows. Plain `bench get-app <repo-url>` does not discover the monorepo (bench expects root `setup.py`); use the `apps.json` method. (Note: `bench execute` takes a dotted method path or expression — bare `import x` statements are not valid `execute` input.)

## Run the service

```bash
uvicorn service.main:app --host 127.0.0.1 --port 8000
```

Bind to localhost unless separately authorized private-network access is
required. Exact `/health` is public and returns only `{"status":"ok"}` even
with missing/invalid authentication configuration. It is minimal liveness,
not readiness of authentication, the index, providers or ERPNext:

```bash
curl -s http://127.0.0.1:8000/health
```

All other paths, including direct APIs, assets, API docs, unknown paths and
OPTIONS, pass the credential gate. Trusted server callers supply
`X-NexMate-Key`; do not distribute that credential to browsers. The direct
curl examples below omit credentials and work only under the explicit local
development settings in the preview section. They are legacy operations,
not Desk requests or permission grants:

```bash
curl -s http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "How do I create a custom DocType?"}' | python3 -m json.tool
```

Response contract:

```json
{
  "answer": "...",
  "sources": [{"title": "...", "section": "...", "url_or_path": "..."}],
  "confidence": "high" | "low" | "no_match"
}
```

`no_match` means retrieval found nothing relevant: the answer is a fixed
honest refusal and `sources` is empty — the UI renders this distinctly.

### Legacy code tools (not available in Desk)

```bash
curl -s http://127.0.0.1:8000/tools/read_file \
  -H 'Content-Type: application/json' \
  -d '{"path": "tools/pathsafe.py"}'
```

Tier-1 read tool: no per-read confirmation after the service gate. Every path
is resolved (symlinks included) against `PROJECT_ROOT` (`config.py`, overridable via
`.env`) and anything resolving outside it is rejected with HTTP 400 and an
explanation — traversal, absolute escapes, and symlinked escapes all fail
loudly. Oversized reads (> `MAX_READ_FILE_BYTES`, default 1MB) are refused,
not truncated.

Search and explain round out Tier 1:

```bash
# grep-equivalent over project files (gitignore-aware via git ls-files):
curl -s http://127.0.0.1:8000/tools/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "resolve_in_project", "ignore_case": false}'

# locate code behind an error and explain the cause, grounded in it:
curl -s http://127.0.0.1:8000/tools/explain \
  -H 'Content-Type: application/json' \
  -d '{"description": "KeyError: path when parsing the /tools/read_file response"}'
```

`search` treats the query as a regex (falls back to literal when it
doesn't compile) and reports whether results were truncated. `explain`
derives search terms from the description, ranks files by specificity-
weighted matches, feeds excerpts to the generation model under the same
grounded-only rules as `/ask`, and cites `path` + line ranges; it declines
honestly when no matching code exists.

### Legacy direct orchestrator (not the Desk gateway)

```bash
curl -s http://127.0.0.1:8000/orchestrate \
  -H 'Content-Type: application/json' \
  -d '{"question": "What fields does Customer have?", "mode": "developer"}'
```

Conversational entry point with seven response routes: `rag`, `code`,
`erpnext`, `smalltalk`, `capability`, `clarify`, and `out_of_scope`
(`service/main.py:234`). Exact fast paths and NLU precede the three-way
task router; direct tool endpoints also remain available. Responses carry
`route`, `route_how`, and `version_info` (which can report unavailable).
`mode: "employee"` selects a public-docs persona and orchestration guards
against code/schema routes; it is caller-supplied, not authenticated
permission enforcement. Conversation threads are Frappe-owned records
(`NexMate Conversation`, bound to authenticated user + site); `ask()` takes
an optional owned `conversation_id` and is stateless without one.
A gateway envelope is different: authenticated service credentials plus
validated user/site/mode and exact `execution_scope="chat-only"` are required
before history or routing. Partial/invalid envelopes and site mismatch
refuse without legacy downgrade, even in development. Backend dispatch
blocks code and ERPNext handlers in both personas, including follow-ups and
degraded routing, and suppresses incidental live version calls. Retrieval
is authorization-scoped per the paragraph above; the gateway envelope also
carries the Frappe-derived scope, validated before history or routing.

## Standalone preview (explicit local development only)

The preview talks directly to the legacy inference API, unlike Desk. After
removing a blank key assignment as described above, enable BOTH settings:

```bash
NEXMATE_ENV=development NEXMATE_DEV_UNAUTHENTICATED=1 \
  uvicorn service.main:app --host 127.0.0.1 --port 8000
xdg-open http://127.0.0.1:8000/ui/preview.html
```

The browser receives no service key. Only missing-header requests with a
valid or unset configured key qualify; invalid supplied credentials or
invalid configured keys still refuse. One switch, localhost, request origin
or browser preview detection cannot enable the backend exemption. Never
use this development bypass to recover production access.

Click the **AI** button (bottom-right). What you can do:

| You type | What happens |
|---|---|
| `How do I create a Sales Invoice?` | RAG answer from public docs with citation pills + confidence badge |
| `What fields does Customer have?` | routed to your LIVE ERPNext instance (route badge `erpnext`, real schema) |
| `How does this project chunk documents?` | answered from this repo's own code/docs |
| `/explain <error description>` | locates the code behind an error in this repo |
| `/search <pattern>` · `/read <path>` | grep / read tools on this repo |
| `/edit path :: find :: replace :: reason` | shows a **unified-diff approval card** — Approve & Commit applies it as its own git commit |
| `/newdoc Customer {"customer_name": "...", "customer_type": "Individual", "customer_group": "Commercial"} :: reason` | shows an **ERPNext write card** — Approve creates the document live (staging!) |
| `/editdoc Customer <name> {"customer_name": "new"} :: reason` | same flow for updates |

In the preview only, the header switch selects **developer** or **employee**
legacy behavior, not privileges. Preview is stateless: start-fresh clears
locally with no server thread. The browser retains no conversation; the
visible transcript is not restored after reload. Preview tools retain their
existing confirmation/staging safeguards; preview access is not permission
to write. The preview is not Bench proof.

## Desk sidebar setup outline (unverified)

The app metadata lives under `frappe_app/pyproject.toml`, not at the repo
root. A root-repository `bench get-app <repo-url>` install is **not verified**;
neither the nested package layout nor asset discovery is certified here.
The following historical manual-copy outline is for controlled development
verification only, not a validated clean-machine installation recipe:

```bash
# copy this repo's frappe_app/ directory into the bench as an app
cp -r /path/to/repo/frappe_app $BENCH/apps/erpnext_ai_copilot
cd $BENCH/apps/erpnext_ai_copilot && pip install -e .

bench build --app erpnext_ai_copilot
bench --site yoursite.local install-app erpnext_ai_copilot

bench --site yoursite.local set-config copilot_api_base "http://<service-host>:8000"
bench --site yoursite.local clear-cache
```

Provision the remaining server settings in the authenticated-boundary
section before using chat. The destination is resolved from the Frappe
server, so localhost there means the Bench host. Use protected private
transport; a shared header alone does not encrypt the connection.

The implemented Desk bundle sends chat only to
`/api/method/erpnext_ai_copilot.api.ask`, with same-origin session credentials
and Frappe's CSRF token. The non-guest gateway constructs the envelope;
API/transport failures are sanitized and never trigger direct inference
fallback. The mode selector is disabled. File/business tools, slash commands,
proposals and approval/rejection actions are unavailable, including stale
cards. Desk start-fresh resets the owned server-side thread (or clears
locally when there is none) and starts a fresh owned conversation; the
transcript restores from the owner's thread on reload. Pending old responses
cannot restore the cleared UI; this does not cancel server work.

Boot still exposes the legacy address, but no credential; Desk no longer
uses that address (`frappe_app/erpnext_ai_copilot/boot.py:10`,
`frappe_app/public/js/copilot.bundle.js:360`). Source and stub-DOM checks do
not establish real Frappe authentication/CSRF integration, packaging or Desk
installation. No full G2/M2 or production-readiness claim is made.

Immediately after this bounded boundary is verified, the next milestone
requires the separately approved `frappe-owned-conversation-state` change:
Frappe-owned persistent records, authenticated user ownership, site
association, replacement of caller-controlled ownership and JSON storage,
and migration/compatibility. It is not implemented here. Fixed site binding
and role-derived persona do not establish session ownership, corpus ACLs or
private-data cloud consent.

Same-source Bench/Docker installation and update parity, compatibility,
patches/migrate, release and rollback checks are **future gates**, not
verified deployment support. See `DEVELOPMENT.md` and `ARCHITECTURE.md`.
The app declares Frappe `>=15`; the product target is v16, not a tested
compatibility matrix.

## Evaluate

RAGAS scoring runs in its own small venv (`.venv-eval`) because the pinned
ragas version needs Python ≤ 3.13, while the main project targets this
machine's newer Python:

```bash
pip install uv
uv venv --python 3.12 .venv-eval
.venv-eval/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-eval/bin/pip install "ragas==0.2.15" "langchain>=0.3,<0.4" \
  "langchain-community>=0.3,<0.4" "langchain-core>=0.3,<0.4" \
  "langchain-openai>=0.2,<0.4" "langchain-ollama>=0.2,<0.5" \
  "langchain-huggingface>=0.1,<0.2" sentence-transformers python-dotenv

# 1) generate answers through the real pipeline (main venv, ~4 min):
python -m evaluation.ragas_eval generate

# 2) score them with RAGAS (eval venv; makes many judge LLM calls):
.venv-eval/bin/python -m evaluation.ragas_eval score data/ragas_samples_<stamp>.json
```

The question set and quality bar live in `EVALUATION.md`; recorded baseline
scores in `progress/CURRENT.md`; raw scored runs land in `data/ragas_baseline_*.json`.
Note the judge model is currently the same local model that generates
answers — treat scores as comparative baselines, not absolutes.

## Repository layout

```
config.py                     # all tunables (paths, k, thresholds, PROJECT_ROOT)
ingestion/scrape_or_load_docs.py   # sitemap crawl -> data/raw_docs/
ingestion/chunk_and_embed.py       # heading chunks -> Chroma (cosine)
rag/retriever.py              # hybrid BM25+vector retrieval, confidence gate
rag/acl.py                    # coarse-grained scope model + pre-retrieval predicates
rag/generations.py            # versioned index generations, publish/rollback
rag/egress.py                 # deny-by-default provider-call boundary
rag/keyword_index.py          # in-house Okapi BM25 over the Chroma corpus
rag/generator.py              # THE one litellm call site (provider-agnostic)
service/main.py               # FastAPI: /ask, /tools/*, /health
tools/memory.py               # confirmed edits -> resolved_issue chunks
tools/pathsafe.py             # project-root path safety (the security primitive)
tools/files.py                # Tier-1 read_file tool
tools/search.py               # Tier-1 gitignore-aware code search
tools/explain.py              # Tier-1 locate + grounded explanation
evaluation/                   # reference answers + RAGAS runner + retrieval probe
tests/                        # stdlib-unittest suite (python -m unittest discover -s tests)
frappe_app/                   # minimal Frappe app: Desk sidebar UI
progress/CURRENT.md           # what works, what doesn't — read after setup
DECISIONS.md                  # ADRs explaining every consequential choice
```
