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
uvicorn service.main:app --reload --port 8000
```

Do NOT install Ollama inside WSL if it's already installed and running on
Windows — see "Using Windows-hosted Ollama from WSL" below. Only run the
`curl ... ollama.com/install.sh` step if you specifically want a *second*,
WSL-local Ollama instance instead.

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

The documented Python discovery command is:

```bash
python -m unittest discover -s tests
```
