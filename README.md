# ERPNext AI Copilot

A tool-using AI assistant for ERPNext developers, embedded in ERPNext as a
Desk sidebar panel. **Phase 1 scope:** pure RAG over public ERPNext/Frappe
documentation — ask developer questions, get answers grounded only in
retrieved documentation, every answer citing its source pages. When
retrieval can't find relevant material, it honestly says so instead of
guessing.

See `PROJECT.md` (product definition), `ARCHITECTURE.md` (system design),
`docs/PHASE_1_SPEC.md` (current-phase spec) and `progress/CURRENT.md`
(exact current state).

## Architecture in one paragraph

Docs are crawled once from `docs.frappe.io` (its official `{url}.md`
markdown alternates) into `data/raw_docs/`, split heading-wise into
~400-token chunks, embedded locally with `BAAI/bge-small-en-v1.5`, and
stored in a persistent Chroma collection (`data/chroma_db/`). At query
time, FastAPI retrieves top-k chunks via hybrid keyword+vector fusion
(best per document), gates them by
similarity score into `high | low | no_match`, and generates an answer via
litellm using ONLY those chunks — provider/model configured entirely
through `.env`.

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

Re-run `chunk_and_embed` anytime for a full rebuild (it drops and recreates
the collection).

## Run the service

```bash
uvicorn service.main:app --host 127.0.0.1 --port 8000
```

Binds localhost only. Test it:

```bash
curl -s http://127.0.0.1:8000/health
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

### Code tools (Phase 2)

```bash
curl -s http://127.0.0.1:8000/tools/read_file \
  -H 'Content-Type: application/json' \
  -d '{"path": "tools/pathsafe.py"}'
```

Tier-1 read tool: always-on, no confirmation. Every path is resolved
(symlinks included) against `PROJECT_ROOT` (`config.py`, overridable via
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

## Install the Desk sidebar (Frappe app)

On the machine running your ERPNext bench:

```bash
# copy this repo's frappe_app/ directory into the bench as an app
cp -r /path/to/repo/frappe_app $BENCH/apps/erpnext_ai_copilot
cd $BENCH/apps/erpnext_ai_copilot && pip install -e .

bench build --app erpnext_ai_copilot
bench --site yoursite.local install-app erpnext_ai_copilot

# point the sidebar at the FastAPI service (default http://localhost:8000):
bench --site yoursite.local set-config copilot_api_base "http://<service-host>:8000"
bench --site yoursite.local clear-cache
```

Then open the desk: a floating **AI** button sits bottom-right; it opens a
chat panel with a Sources list and confidence badges. The service address
reaches the client via `frappe.boot.copilot_settings` (`boot.py`).

> If the ERPNext site is served over HTTPS, browsers block calls to an
> `http://` service (mixed content). For development over plain HTTP this
> just works; put TLS or a same-origin proxy in front of FastAPI for
> production HTTPS setups.

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
rag/keyword_index.py          # in-house Okapi BM25 over the Chroma corpus
rag/generator.py              # THE one litellm call site (provider-agnostic)
service/main.py               # FastAPI: /ask, /tools/read_file|search|explain, /health
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
