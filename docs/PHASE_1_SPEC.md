# PHASE_1_SPEC.md — Historical Phase 1 Requirements

**Historical reference, not current build scope.** Phase 1 was accepted
2026-08-24 with exceptions recorded in `ROADMAP.md` and `EVALUATION.md`;
real Bench/Desk verification remains outstanding. `ARCHITECTURE.md` is the
sole canonical HLD. Post-roadmap work requires a user-approved OpenSpec
change; the original requirements below do not prohibit maintaining later
implemented features or authorize new work, tests or provider changes.
`SECURITY.md` remains standing policy, including private-data cloud consent.

The original public-only scope, API shape and tuning defaults below record
Phase 1 intent, not today's full implementation. The restored 2026-08-23
crawl-source and hybrid-chunking ADRs in `DECISIONS.md` explain changes to
the original source preference and chunking approach.

## Original requirements

## Goal

A working RAG pipeline, embedded in ERPNext as a sidebar chat panel, that
answers developer questions about ERPNext and Frappe using only public
documentation, with correct source citations and honest "I don't know"
responses when retrieval doesn't have a good match. Developer mode only. No
live ERPNext API access, no code search, no orchestrator, no employee mode.

## Data sources

- ERPNext documentation: https://docs.erpnext.com (prefer the doc source in
  the `frappe/erpnext` / `frappe/docs` repos if scraping the live site is
  impractical — repo source is cleaner to parse)
- Frappe framework documentation: https://frappeframework.com/docs (or the
  `frappe/frappe` repo's doc source)
- If a data source is blocked or its terms are unclear, log the blocker in
  `progress/BLOCKERS.md` and ask rather than guessing at a workaround.

## Chunking approach

Split by document heading/section structure (H1/H2/H3), not fixed character
windows. Target ~300–500 tokens per chunk with ~50-token overlap between
adjacent chunks. Store per-chunk metadata: source document title, section
heading, source URL/path, `source_type: public_doc`.

## Retrieval + generation behavior

- Top-k retrieval, start k=5, tune based on manual testing against
  `EVALUATION.md`'s test set.
- Answers must be grounded only in retrieved chunks — never answer from the
  model's own training knowledge about ERPNext when retrieval is weak.
- Low similarity/relevance on top results → respond that the knowledge base
  doesn't have a confident answer, rather than guessing.
- Every answer lists which document(s)/section(s) it drew from.

## Generation provider

Do not hardcode a provider or model. Read `GENERATION_PROVIDER` and
`GENERATION_MODEL` (plus provider-specific settings like
`OLLAMA_BASE_URL` or an API key) from `.env` via `litellm`. The user
already has Ollama running on Windows (not WSL) — do NOT install or run a
second Ollama instance inside WSL. See `DEVELOPMENT.md`'s "Using
Windows-hosted Ollama from WSL" section for the exact networking setup, and
ask the user to confirm `OLLAMA_BASE_URL` works (via a `curl` health check)
before building generation logic on top of it. The user must be able to
switch to a cloud provider (Anthropic/OpenAI) or a different local model
purely by editing `.env` — never by editing code.

## API contract (FastAPI service)

```
POST /ask
{ "question": "How do I create a custom DocType?" }

Response:
{
  "answer": "...",
  "sources": [{"title": "...", "section": "...", "url_or_path": "..."}],
  "confidence": "high" | "low" | "no_match"
}
```

Field names can be adjusted, but the shape — answer + sources + confidence
signal — is required; the UI depends on all three.

## Frappe sidebar UI (minimal)

Single page or sidebar panel in the Frappe desk interface. Text input,
submit action, response area with a visibly separate "Sources" list. No
chat history/threading required yet. A "no confident answer" response must
be visually distinct, not printed as normal text.

## Deliverable structure

```
erpnext-ai-copilot/
├── (this doc set)
├── requirements.txt
├── .env.example             # template: GENERATION_PROVIDER, GENERATION_MODEL, etc.
├── .env                      # gitignored, actual local config
├── ingestion/
│   ├── scrape_or_load_docs.py
│   └── chunk_and_embed.py
├── rag/
│   ├── retriever.py
│   └── generator.py
├── service/
│   └── main.py            # FastAPI app
├── frappe_app/             # minimal custom Frappe app for the sidebar UI
└── data/
    └── chroma_db/          # persisted vector store (gitignored)
```

## Definition of Done

See `EVALUATION.md` for the full checklist and test question set. Do not
report this phase complete until every item there is verified true.
