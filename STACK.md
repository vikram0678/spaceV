# SpaceV Technology Stack

> Codebase map prepared on 2026-11-05. Versions below describe declared constraints or the build configuration; resolved package versions vary unless stated otherwise.

## Runtime

| Technology | Version / constraint | Purpose |
|---|---|---|
| Python | Docker image `3.11-slim`; Celesto requirement marker enables SDK at Python >=3.11 | Desktop assistant, control plane, orchestration, and tools |
| PyQt6 | `>=6.5.0` | Desktop GUI, tray, chat, and HUD |
| LangGraph | `>=0.2.0` | Agent workflow/state graph; source includes a native fallback graph implementation |
| Docker Compose | Compose plugin | Starts the ledger API and PostgreSQL |
| PostgreSQL | `16-alpine` image | Durable run ledger |

## Production and Runtime Dependencies

| Package(s) | Declared requirement | Purpose |
|---|---|---|
| `celesto` | `>=0.1.0`, only when Python >=3.11 | Celesto sandbox SDK and CLI dependency |
| `fastapi`, `uvicorn[standard]` | `>=0.110.0`, `>=0.28.0` | Control-plane HTTP API |
| `pydantic`, `pydantic-settings` | `>=2.6.0`, `>=2.0.0` | Request/configuration validation |
| `psycopg`, `psycopg-binary` | `>=3.1.0` | PostgreSQL connectivity |
| `requests`, `httpx` | `>=2.31.0`, `>=0.27.0` | HTTP and model/provider clients |
| `playwright` | `==1.64.0` | Browser automation |
| `pypdf` | `==6.21.4` | PDF text extraction |
| `psutil`, `pyautogui`, `pyperclip`, `Pillow`, `watchdog`, `pynput` | Minimum versions in `requirements.txt`; `pynput` is Windows-only | Host desktop interaction, clipboard, image handling, and file watching |
| `numpy`, `opencv-python-headless` | `>=1.24.0`, `>=4.8.0` | Numerical processing and vision/OCR support |
| `edge-tts`, `pygame` | `>=7.0.0`, `>=2.6.0` | Speech synthesis and audio playback |
| `onnxruntime`, `faster-whisper`, `SpeechRecognition` | Minimum versions in `requirements.txt` | Voice activity/model inference and speech recognition |
| `beautifulsoup4`, `markdownify` | Minimum versions in `requirements.txt` | Web extraction and content normalization |
| `magika` | `>=1.0.3` | File-type/content inspection |
| `pytest`, `pytest-asyncio` | `>=7.4.0`, `>=0.23.0` | Test and async-test execution |

The full, authoritative dependency list is [requirements.txt](requirements.txt). Most packages are specified with minimum versions, not exact pins, so builds may resolve newer releases.

## Infrastructure and Integrations

| Service / system | Type | Purpose and current state |
|---|---|---|
| Celesto | Python SDK / isolated computer service | The source supports local or Cloud provider selection; the checked-in Compose file currently selects local Firecracker. No Cloud computer run was verified in this map. |
| PostgreSQL | Docker service | Run ledger backing store; named volume retains database data |
| FastAPI + Uvicorn | Docker service | Trusted control-plane API on port 8080 |
| Ollama | Local HTTP service | Optional local model inference; default model names and URL are in `config.py` / `.env.example` |
| Hosted LLM or compatible proxy | HTTP API | Configurable through `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` |
| Playwright/browser | Browser automation library | Web interaction and testing tools |
| Windows desktop APIs and libraries | Host integration | PyQt, PyAutoGUI, keyboard/mouse, screen capture, and voice I/O for the interactive desktop app |

## Configuration

| Variable / file | Purpose | Required? |
|---|---|---|
| `CELESTO_PROVIDER` | Chooses `local` or `cloud` in the Celesto engine | Required for a specific intended backend; current defaults select `local` |
| `CELESTO_API_KEY` | Authenticates Celesto Cloud SDK calls | Required for Cloud; keep secret and do not commit |
| `CELESTO_BACKEND` | Local runtime backend setting | Local-only; Compose sets `firecracker` |
| `CELESTO_PROVIDER` | Selects `local`, `cloud`, or explicit `simulation` execution | `local` for your WSL Firecracker setup; Cloud requires a non-placeholder `CELESTO_API_KEY` |
| `DATABASE_URL` | PostgreSQL connection string | Compose supplies it to the API container |
| `API_PORT` | FastAPI port | Defaults to `8080` |
| `ENVIRONMENT` | Runtime environment label | Defaults to `production` in the control-plane configuration |
| `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | Main endpoint/provider/model configuration | Provider/key/model needs depend on local vs hosted endpoint |
| `OLLAMA_BASE_URL`, model variables | Local model service and role-specific models | Optional when using a remote LLM endpoint |
| `config/providers.yaml` | Optional provider/model/key-pool and role settings loaded by root `config.py` | Optional; keep real credentials out of tracked files |
| `.env.example` | Safe placeholder template | Reference only; contains no live key |
| `.env` | Local private configuration; ignored by `.gitignore` and excluded from the Docker build context | Optional and secret-bearing; never commit |

## Docker Deployment

- [Dockerfile](Dockerfile) uses `python:3.11-slim`, installs `curl`, `gcc`, and `libpq-dev`, installs `requirements.txt`, and starts `uvicorn spacev.control_plane.main:app`.
- [docker-compose.yml](docker-compose.yml) starts `spacev-api` and `spacev-ledger`, maps ports 8080 and 5432, and persists PostgreSQL data in `spacev_ledger_data`.
- The Dockerfile is a single-stage image despite its header comment. It copies the control-plane package and ledger artifacts, not the desktop assistant's `main.py`, `core/`, `tools/`, `ui/`, or `voice/` modules.
- Compose currently sets `CELESTO_PROVIDER=local` and `CELESTO_BACKEND=firecracker`; it does not pass a Cloud API key. A healthy API container is not evidence that Celesto Cloud is configured.

## Verification Notes

- User-provided logs show the Linux Docker image installed `celesto` and `celesto-core` successfully. Later outputs showed PostgreSQL healthy, `/health` returning HTTP 200, the seeded `GET /api/runs` row, and a valid `POST /api/runs` returning HTTP 201 with the inserted row visible in a subsequent GET.
- These observations verify dependency installation in the image and the reported ledger happy paths. They do not establish live sandbox creation, the cloud execution path, host containment, or the desktop agent's Docker deployment.
- No tests, LLM calls, or Celesto Cloud commands were run as part of this codebase map.
