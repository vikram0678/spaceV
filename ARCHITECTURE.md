# SpaceV Architecture

> Codebase map prepared on 2026-11-05 from the checked-out source. This describes code and configuration, not a claim that every path has been exercised live.

## Overview

SpaceV contains two related but distinct applications:

1. A Windows-oriented desktop assistant started by `main.py`. It combines a PyQt interface, voice input/output, an LLM orchestration loop, and a registry of desktop, browser, file, career, and sandbox tools.
2. A FastAPI control-plane and run-ledger service under `spacev/control_plane/`. Docker Compose runs this API with PostgreSQL. The current container is not the desktop assistant: its Dockerfile copies `spacev/`, `seeds/`, `reports/`, and `logs/`, but not `main.py`, `core/`, `tools/`, `ui/`, or `voice/`.

The Celesto code has a real SDK execution path selected by `CELESTO_PROVIDER` in `.env`. `local` selects the local backend, `cloud` requires a configured API key, and `simulation` explicitly disables real execution. A successful `/health` response proves the API process is serving health requests; it does not prove that a Celesto computer was created or that SpaceV's desktop agent is using Celesto Cloud.

## System Diagram

```text
User (voice or chat)
        |
        v
main.py / PyQt UI ---------------- Voice pipeline (VAD -> STT -> agent -> TTS)
        |
        v
core/brain_orchestrator.py + core/graph_engine.py
        |                 |
        |                 +--> Local Ollama and configured remote LLM clients
        v
tools/registry.py (schemas, scoped tool selection, dispatch)
        |
        +--> Desktop, files, browser, career, vision, and job tools
        +--> Repo clone tool (approval-gated source-only clone)
        +--> Sandbox tools (simulation by default; opt-in SDK command runner)
                                |
                                +--> Celesto SDK -> local or cloud computer (if configured)

Separate Docker Compose deployment:
FastAPI control plane (spacev/control_plane) <--> PostgreSQL ledger
        |                                      (health, list runs, create run)
        +--> Host-mounted seed/report/log paths
```

## Components

| Component | Purpose | Main locations |
|---|---|---|
| Desktop entry point | Builds the PyQt tray, chat, HUD, voice, and assistant lifecycle | `main.py`, `ui/` |
| Agent reasoning and orchestration | LLM conversation, LangGraph-style state flow, routing, memory, verification, retries, and clarification | `core/brain_orchestrator.py`, `core/graph_engine.py`, `core/grounded_agent.py`, `core/intent/`, `core/model_router.py` |
| Durable task evidence | Locally stores bounded, redacted tool outputs and completed chat turns so relevant findings can be recalled after conversation pruning or restart | `core/task_evidence.py`, `.spacev/task_evidence.sqlite3` |
| Tool interface | Defines tool schemas, maps names to implementations, scopes available tools, and dispatches calls | `tools/registry.py`, `tools/schemas.py` |
| Tool implementations | Desktop input, screen/vision, web/browser, file, career, scraping, repository, and sandbox actions | `tools/` |
| Voice and perception | VAD, speech recognition, TTS, audio streaming, screen capture, UI grounding, ambient signals | `voice/`, `core/screen_capture.py`, `core/vision_grounding.py`, `core/uia_grounding.py`, `spacev/web/` |
| Celesto fleet and safety | SDK computer lifecycle, command audit/safety checks, and workflow/recovery orchestration | `spacev/fleet/`, `spacev/safety/`, `tools/sandbox_tools.py` |
| Control plane and ledger | HTTP health and run-record endpoints, request validation, PostgreSQL access | `spacev/control_plane/` |
| Evaluation and evidence | Contract checks and JSON/JSONL reports for capabilities, reliability, containment, lifecycle, concurrency, and failure policy | `tests/`, `reports/`, `logs/`, `seeds/` |

## Data and Control Flow

1. `main.py` creates the desktop UI and assistant. Voice is handled by the modules in `voice/`; typed input enters through the chat UI.
2. `HybridBrainAgent` and the graph/orchestration modules manage conversation state, choose models, request tools, and synthesize responses. `config.py` selects a remote endpoint or local Ollama based on environment and provider configuration.
   Relevant prior task records are selected by topic/follow-up matching and added to the protected system context. Tool records retain source, status, timestamp, hash, and truncation state; chat records are labeled as unverified conversation.
3. `tools/registry.py` exposes function schemas and dispatches validated calls to tool implementations. Some tools operate on the user's host; sandboxing is not universal across the tool registry.
4. `tools/sandbox_tools.py` uses explicit simulation behavior by default. Its command runner can opt into the Celesto SDK path when configured; the diagnostic tool reports readiness without creating a VM.
5. `spacev/fleet/celesto_engine.py` creates a `celesto.Computer` when the provider and key are configured, runs commands through that object, and provides cleanup/snapshot/restore wrappers. This live path has not been verified against the currently installed Cloud SDK in this mapping.
6. Independently, Docker Compose runs `spacev.control_plane.main:app`. The API validates and stores run records in PostgreSQL, with an in-memory fallback in `spacev/control_plane/database.py` if database operations fail.

## API and Infrastructure

| Service | Endpoints / role | Configuration |
|---|---|---|
| SpaceV ledger API | `GET /health`, `GET /api/runs`, `POST /api/runs` | FastAPI/Uvicorn, port 8080 |
| PostgreSQL | Persistent run ledger, seeded from `seeds/` | PostgreSQL 16 Alpine, port 5432, named Docker volume |
| Celesto computer | Isolated execution target for the opt-in SDK runner | `CELESTO_PROVIDER`, `CELESTO_API_KEY`; Compose currently sets provider `local` and backend `firecracker` |
| LLM endpoint | Remote provider/proxy or local Ollama | `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`; additional provider pools are read from environment and `config/providers.yaml` |

## Tests and Evidence

- `tests/` contains unit, integration, contract, voice, tool, orchestration, sandbox, and run-ledger tests. The hackathon-style contracts are grouped in `tests/test_reports.py`; Celesto-related suites include `tests/test_phase5_celesto_sandbox.py`, `tests/test_phase6_containment.py`, and `tests/test_phase7_run_ledger.py`.
- `reports/` contains declared evidence artifacts. Their presence and schema do not by themselves prove that the recorded runs came from live Celesto computers.
- User-provided Docker output showed PostgreSQL healthy, `GET /health` returning HTTP 200 with `{"status":"ok"}`, `GET /api/runs` returning the seeded `sbx-seeddemo1` row, and a valid `POST /api/runs` returning HTTP 201 followed by a `GET` that showed the new row persisted. This verifies the reported ledger happy paths at that time; the health route itself is static and does not query Celesto.

## Technical Debt and Verification Gaps

- **Desktop agent is not in the Docker image.** The present Dockerfile only packages the control-plane API and its data files. Running Compose does not start `main.py` or the full tool registry.
- **Cloud is not selected by the current Compose configuration.** It explicitly sets `CELESTO_PROVIDER=local` and `CELESTO_BACKEND=firecracker`, and does not pass `CELESTO_API_KEY` to the API service. This is not the Windows-to-Celesto-Cloud configuration.
- **Simulation remains a separate path.** Set `CELESTO_PROVIDER=simulation` to use the in-memory simulator. The sandbox workflow and containment demonstrations explicitly identify themselves as simulations. They are not real isolation evidence.
- **SDK integration is not yet empirically verified.** The engine references SDK snapshot/restore methods and lifecycle behavior, but no live Cloud run was demonstrated during this mapping. Confirm API signatures, backend provisioning, cleanup, and audit evidence with a small Cloud smoke run before relying on it.
- **Ledger health is shallow.** `/health` returns `{"status":"ok"}` without checking PostgreSQL. Ledger reads/writes can fall back to process-local memory on database errors, which can hide loss of persistence unless callers inspect logs/health details.
- **Evidence claims need provenance.** README and report files describe fresh runs, fast snapshots, containment, and host integrity. The current source explicitly labels several sandbox flows as simulations. Regenerate and retain evidence from actual Cloud runs before presenting those claims as verified.
- **Container build description is stale.** The Dockerfile header says multi-stage, but the file has one `FROM` stage. It installs the full requirements list even though the image only runs the API, increasing image size and coupling API builds to desktop/voice dependencies.
- **Dependency reproducibility is limited.** Most requirements use open-ended minimum versions rather than a lockfile; the Docker build can therefore resolve different versions over time.
- **Tool boundaries vary.** The registry contains host desktop/file/browser tools in addition to sandbox actions. The sandbox execution guarantee applies only when a task is routed through the Celesto runner, not to every registered tool.
- **Sandbox proposals require concrete inputs.** SpaceV rejects common unresolved prompt-template markers such as `[Paste the issue text here]` before proposing or starting a VM, with a second guard on sandbox-session creation.
- **Issue-test verdicts are evidence-gated.** SpaceV labels captured sandbox test output conservatively; a non-zero exit is not a reproduced bug unless the target test output contains the issue-derived expected signal. `git status --short` snapshots are reported as path classifications and must be compared with the pre-edit baseline.
- **Durable context is local and bounded.** `.spacev/task_evidence.sqlite3` keeps at most 500 redacted records; individual tool outputs and transcripts are capped, and recalled excerpts are labeled with provenance and truncation. This improves follow-up recall but does not reconstruct records from before the feature was enabled.

## Conventions

- Python modules are grouped by responsibility (`core/`, `tools/`, `voice/`, `ui/`, and `spacev/`).
- Tool definitions and schemas are centralized in `tools/registry.py` and `tools/schemas.py`.
- Environment configuration is loaded by `config.py` for the desktop agent and `spacev/config.py` for the control plane/fleet components. `.env.example` is the placeholder template; `.env` is ignored by Git.
- Docker Compose owns the API/database development deployment. Pytest tests live under `tests/` plus several root-level test scripts.
