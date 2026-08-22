# ARCHITECTURE.md — System Design

## Status

This describes the full target architecture across all phases. Only the
subset relevant to the current phase (see `ROADMAP.md`) should actually be
built right now.

## Full target architecture

```
                    Company ERPNext
                         │
                         │ API
                         ▼
                ┌─────────────────┐
                │  AI Assistant   │
                └─────────────────┘
                   │              │
             ┌─────┘              └──────┐
             ▼                            ▼
       Employee/User                 Developer
             │                            │
             └──────────────┬─────────────┘
                             ▼
                    ┌──────────────────┐
                    │   AI Interface   │
                    │  Chat / Sidebar  │
                    └────────┬─────────┘
                             ▼
                    ┌─────────────────────────┐
                    │     AI Orchestrator     │
                    │  Intent / Routing       │
                    │  Permissions            │
                    │  Conversation state     │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
        ┌──────────┐       ┌──────────┐       ┌──────────┐
        │   RAG    │       │ ERPNext  │       │  Code    │
        │  Engine  │       │   Tool   │       │ Search   │
        └────┬─────┘       └────┬─────┘       └────┬─────┘
             │                  │                  │
             ▼                  ▼                  ▼
        Vector DB          ERPNext API       Git / Source
             │              (read-only        (custom app +
             ▼               initially)        eventually core)
      ┌─────────────────┐
      │ Knowledge Base  │
      │  - ERPNext docs │
      │  - Frappe docs  │
      │  - Company docs │
      │  - Source code  │
      └─────────────────┘
                             │
                    ┌────────┴────────┐
                    │       LLM       │
                    │  Reasoning +    │
                    │  RAG + Tools    │
                    └─────────────────┘
```

## Components

- **AI Interface** — chat panel embedded in ERPNext (Frappe app, sidebar
  page).
- **AI Orchestrator** — intent routing, permission enforcement, conversation
  state. Only justified once there are 2+ tools to route between (Phase 5+).
  Do not build before then — with a single tool it's dead weight.
- **RAG Engine** — semantic search over the layered knowledge base.
- **ERPNext Tool** — read-only queries against the live instance (DocType
  schemas, field values, document status). Write actions are a separate,
  later, heavily-guarded capability (see Developer Agent, Phase 7).
- **Code Search** — becomes distinct from RAG only once the codebase is
  large enough that AST/structural search outperforms embeddings. Until
  then it is just RAG over embedded code chunks — do not build it as a
  separate service prematurely.
- **Developer Agent** — highest-risk, last-built. Multi-step actions
  (create a DocType, apply a fix) require confirmation steps and a
  staging-only policy before touching production.

## Models used, and why (confirm before any download — see AGENTS.md)

| Model | Role | Always needed? | Approx. size |
|---|---|---|---|
| `BAAI/bge-small-en-v1.5` (embedding) | Converts doc chunks and questions into vectors for similarity search/retrieval | Yes, regardless of generation provider choice | ~130MB |
| Ollama LLM (e.g. `llama3.1:8b`) | Generates the natural-language answer from retrieved chunks | Only if `GENERATION_PROVIDER=ollama` (local). Not downloaded at all if using `anthropic`/`openai` | 2–5GB depending on model |
| Cloud LLM (e.g. Claude, GPT) | Same generation role, hosted | Only if `GENERATION_PROVIDER=anthropic`/`openai` | No local download — API calls only |

## Locked tech stack (current phase)

All choices are free/open-source and run locally — no API keys, no billing,
no external accounts required.

| Layer | Choice | Why |
|---|---|---|
| Embeddings | `sentence-transformers` — `BAAI/bge-small-en-v1.5` (fallback `all-MiniLM-L6-v2`) | Free, local, strong retrieval quality for its size. |
| Vector store | Chroma, `PersistentClient` (local, persistent — not in-memory) | Free, embedded, no server process, first-class LlamaIndex support. |
| RAG glue | LlamaIndex | Purpose-built for RAG; less boilerplate than general agent frameworks for this job. |
| Document loading & chunking | LlamaIndex loaders; split by heading/section boundary, not fixed character windows | ERPNext/Frappe docs have clear structural sections. |
| LLM (generation) | Provider-agnostic via `litellm`, configured by env var — default `ollama/llama3.1:8b` (local), swappable to `anthropic/claude-*`, `openai/gpt-*`, or any other litellm-supported provider without code changes | User wants to choose cloud vs. local and switch models freely. `litellm` gives one call interface across providers so the swap is a config change, not a rewrite. See "Generation provider config" below. |
| Backend service | FastAPI | Lightweight, standard, easy for a Frappe app to call into. |
| Frontend / ERPNext integration | Custom Frappe app — desk page or sidebar widget, native Frappe JS, calling the FastAPI service | Keeps the AI service decoupled from the Frappe bench process. |
| Evaluation | RAGAS | Free, purpose-built to score faithfulness, answer relevancy, context precision. |
| Dependency management | `venv` + `requirements.txt` | Standard, unambiguous for anyone setting this up from scratch. |
| Version control | Git, incremental commits per milestone | Enables rollback if a later phase breaks something. |

### Generation provider config

The generation step must never hardcode a specific provider or model in
code. Read the provider and model from environment variables (`.env`,
not committed to git) at startup:

```
GENERATION_PROVIDER=ollama          # or: anthropic, openai, etc.
GENERATION_MODEL=llama3.1:8b        # or: claude-sonnet-4-5, gpt-4o-mini, etc.
OLLAMA_BASE_URL=http://<windows-host-ip>:11434   # only needed for local Ollama, see DEVELOPMENT.md
ANTHROPIC_API_KEY=...                # only needed if GENERATION_PROVIDER=anthropic
OPENAI_API_KEY=...                   # only needed if GENERATION_PROVIDER=openai
```

`rag/generator.py` calls `litellm.completion(model=f"{provider}/{model}", ...)`
— this is the one call site that changes behavior; nothing else in the
codebase should reference a provider name directly. Switching providers is
editing `.env` and restarting the service, not touching code.

### Explicitly deferred — do not install/use before their phase

- LangGraph — Phase 5 (orchestrator), not needed with a single tool.
- A paid LLM API is not the *default* (`GENERATION_PROVIDER=ollama` is), but
  it is a supported config choice from Phase 1 onward — the user may switch
  to it at any time via `.env`. What's still deferred is a paid *embeddings*
  API (see embeddings row above) and any automatic/implicit provider
  switching not explicitly requested by the user.
- `tree-sitter`/AST chunking — Phase 2 (source code ingestion).
- ERPNext live API client — Phase 4.
- Docker — introduce once running alongside the real ERPNext bench; not
  required to build/test the current phase locally.

### Hardware note

`llama3.1:8b` via Ollama needs roughly 8GB RAM available. If the dev
machine can't handle it comfortably, fall back to a smaller model and log
the substitution in `progress/JOURNAL.md` rather than struggling silently.

## Knowledge base layering

One vector store, metadata-tagged (`source_type: public_doc | company_doc |
our_code | core_code`), filtered at query time. Not two parallel systems —
see `PROJECT.md` for the reasoning.
