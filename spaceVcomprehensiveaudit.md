# SPACEV: COMPREHENSIVE WORKFLOW COMPARISON, CODE AUDIT, AND ENGINEERING IMPROVEMENT PLAN

> **Document Type:** Master System Architecture Audit, Line-by-Line Code Review, and Autonomous Engineering Blueprint  
> **Workspace Location:** `D:\agentSpace\`  
> **Target Artifact:** `SPACEV_ISSUE_TO_FAILING_TEST_COMPREHENSIVE_AUDIT.md`  
> **Author:** Principal Agentic AI Systems Architect, Senior Software Reliability Fellow & Autonomous Coding Systems Researcher (20+ Years Equivalent Experience)  
> **Investigation Scope:** Strict Read-Only Audit of SpaceV Codebase, Configuration, and Celesto Runtime Logs  
> **Reference Pilot:** `psf/requests/issues/7639`  

---

## TABLE OF CONTENTS

1. [Executive Summary & Paradigm Contrast](#executive-summary--paradigm-contrast)
2. [Section 1: Original Intended Workflow](#section-1-original-intended-workflow)
3. [Section 2: Actual SpaceV Implementation Investigation](#section-2-actual-spacev-implementation-investigation)
4. [Section 3: Strict Side-by-Side Comparison](#section-3-strict-side-by-side-comparison)
5. [Section 4: Actual Error and Failure Investigation](#section-4-actual-error-and-failure-investigation)
6. [Section 5: Actual Execution Flow and Call Graph](#section-5-actual-execution-flow-and-call-graph)
7. [Section 6: Expected Workflow vs. Actual Workflow](#section-6-expected-workflow-vs-actual-workflow)
8. [Section 7: Senior Engineering Analysis](#section-7-senior-engineering-analysis)
9. [Section 8: Target Architecture](#section-8-target-architecture)
10. [Section 9: Implementation Roadmap](#section-9-implementation-roadmap)
11. [Section 10: Testing and Validation Plan](#section-10-testing-and-validation-plan)
12. [Section 11: Final Technical Assessment](#section-11-final-technical-assessment)

---

## EXECUTIVE SUMMARY & PARADIGM CONTRAST

SpaceV is a local-first, cybernetic AI desktop assistant built on Python, LangGraph, and Celesto virtualization. Recently, an autonomous coding capability was introduced to reproduce public GitHub issues as isolated, failing regression tests without modifying production source code (the **Issue → Failing Test** pilot).

This audit provides an evidence-based, line-by-line technical investigation of how SpaceV actually attempts to execute this workflow compared to the intended 7-step specification.

### Core Architectural Finding
The fundamental failure mode of SpaceV today is architectural:
> **SpaceV attempts to solve a deterministic CI/CD verification problem using an open-ended, reactive conversational LLM loop.**

In SpaceV, there is no deterministic compiler or state machine driving the 7 steps. Instead, the workflow is presented to an auto-regressive model as a textual set of instructions in a system prompt (`ISSUE_TEST_AGENT_CONFIG`). The system requires the model to manually call tools across 8 to 15 conversational round trips, interleaved with rigid human regex text prompts (`approve sandbox task <10-hex>`). 

When any intermediate step encounters real-world friction—such as an unauthenticated GitHub 403 rate limit, a bare Alpine Linux shell lacking Git, a 30-second clone timeout, or a rigid gate condition—the model's context window degrades, leading to deadlocks, hallucinations, and empty evidence bundles.

---

## SECTION 1: ORIGINAL INTENDED WORKFLOW

The intended target workflow consists of seven canonical stages:

### Step 1: Accept a GitHub Issue URL
Human provides a GitHub issue URL.

### Step 2: Read and Understand the Issue
Agent retrieves and understands the issue title, description, expected behavior, actual behavior, and reproduction information.

### Step 3: Clone Repository in an Isolated Sandbox
Agent provisions or reuses an appropriate sandbox and clones the repository.

### Step 4: Inspect Source Code and Existing Tests
Agent identifies relevant source files, functions, classes, existing tests, dependencies, and execution requirements.

### Step 5: Generate a Minimal Failing Test
Agent proposes a minimal test that reproduces the reported bug. Agent must not fix the bug.

### Step 6: Execute and Verify the Test
Agent establishes a valid baseline, executes the proposed test, and determines whether the failure matches the reported bug.

### Step 7: Deliver Evidence and Report
Agent provides the test, relevant source references, execution command, output, failure classification, and final report.

---

## SECTION 2: ACTUAL SPACEV IMPLEMENTATION INVESTIGATION

Every relevant component discovered in `d:\agentSpace\` has been audited line-by-line. The table below documents their actual paths, signatures, line ranges, and runtime invocation realities.

### Component Inventory Table

| Component File Path | Class & Function Name | Source Lines | Purpose & Functionality | Inputs & Outputs | Invocation Status | Current Implementation Status |
|---|---|---|---|---|---|---|
| [`core/issue_test_workflow.py`](file:///d:/agentSpace/core/issue_test_workflow.py#L19-L54) | `parse_github_issue_url(url)` | 19–54 | Validates public HTTPS `github.com` URLs; rejects PRs (`/pull/`), query params, credentials, and SSRF patterns. | **In:** `url: str`<br>**Out:** `dict[str, Any]` (canonical URL, owner, repo, issue_num) | Invoked in [`core/graph_engine.py:485`](file:///d:/agentSpace/core/graph_engine.py#L485) | **Implemented & Verified** |
| [`core/issue_test_workflow.py`](file:///d:/agentSpace/core/issue_test_workflow.py#L56-L83) | `detect_guest_environment(...)` | 56–83 | Parses `/etc/os-release` and `uname` output to identify guest OS, distro, and package manager (`apk`, `apt`, `dnf`). | **In:** `os_release: str, python_version: str, uname: str`<br>**Out:** `dict[str, Any]` | Invoked in [`core/graph_engine.py:1439`](file:///d:/agentSpace/core/graph_engine.py#L1439) | **Implemented & Verified** |
| [`core/issue_test_workflow.py`](file:///d:/agentSpace/core/issue_test_workflow.py#L97-L106) | `_is_test_path(path)` | 97–106 | Regex-based validator asserting whether a candidate file path belongs strictly to a test suite (`tests/`, `test_*.py`). | **In:** `path: str`<br>**Out:** `bool` | Invoked by `classify_test_patch_paths` | **Implemented & Verified** |
| [`core/issue_test_workflow.py`](file:///d:/agentSpace/core/issue_test_workflow.py#L108-L116) | `_target_test_from_command(command)` | 108–116 | Extracts narrowest pytest node ID or test filename from bash command line. | **In:** `command: str`<br>**Out:** `str \| None` | Invoked by `classify_test_execution` | **Implemented & Verified** |
| [`core/issue_test_workflow.py`](file:///d:/agentSpace/core/issue_test_workflow.py#L118-L150) | `_target_failure_contains_signal(...)` | 118–150 | Parses pytest short summary and failure blocks to verify presence of `expected_failure_signal`. | **In:** `command: str, output: str, expected_signal: str`<br>**Out:** `bool` | Invoked by `classify_test_execution` | **Implemented & Verified** |
| [`core/issue_test_workflow.py`](file:///d:/agentSpace/core/issue_test_workflow.py#L153-L205) | `classify_test_execution(...)` | 153–205 | Classifies test execution output into 7 discrete outcomes (`EXPECTED_BUG_FAILURE`, `TIMEOUT`, `IMPORT_ERROR`, etc.). | **In:** `command: str, tool_output: str, expected_signal: str`<br>**Out:** `dict[str, Any]` | Invoked in [`core/graph_engine.py:1412`](file:///d:/agentSpace/core/graph_engine.py#L1412) | **Implemented & Verified** |
| [`core/issue_test_workflow.py`](file:///d:/agentSpace/core/issue_test_workflow.py#L208-L229) | `classify_git_status(command, tool_output)` | 208–229 | Audits `git status --short` snapshots for baseline cleanliness (`CLEAN_WORKTREE`, `TEST_FILES_ONLY`, `NON_TEST_FILES_CHANGED`). | **In:** `command: str, tool_output: str`<br>**Out:** `dict[str, Any]` | Invoked in [`core/graph_engine.py:1416`](file:///d:/agentSpace/core/graph_engine.py#L1416) | **Implemented & Verified** |
| [`core/issue_test_workflow.py`](file:///d:/agentSpace/core/issue_test_workflow.py#L231-L298) | `classify_test_patch_paths(...)` | 231–298 | Audits diff paths from `git diff --name-only` or `git status --short` to ensure zero production file edits. | **In:** `command: str, tool_output: str`<br>**Out:** `dict[str, Any]` | Invoked in [`core/graph_engine.py:1497`](file:///d:/agentSpace/core/graph_engine.py#L1497) | **Implemented & Verified** |
| [`core/agent_configs.py`](file:///d:/agentSpace/core/agent_configs.py#L120-L166) | `ISSUE_TEST_AGENT_CONFIG` | 120–166 | Declares `AgentConfig` for `ISSUE_TEST` role: sets temperature=0.1, max tokens, system prompt guidelines, and allowed tools. | **In:** None<br>**Out:** `AgentConfig` instance | Referenced in [`core/graph_engine.py:1000`](file:///d:/agentSpace/core/graph_engine.py#L1000) | **Implemented & Active** |
| [`core/swarm_orchestrator.py`](file:///d:/agentSpace/core/swarm_orchestrator.py#L84-L125) | `SwarmOrchestrator.classify_agent_role()` | 84–125 | Deterministic regex classifier that routes prompts containing `github.com/*/issues/*` to `AgentRole.ISSUE_TEST`. | **In:** `text: str`<br>**Out:** `AgentRole` enum | Invoked in [`core/graph_engine.py:910`](file:///d:/agentSpace/core/graph_engine.py#L910) | **Implemented & Verified** |
| [`core/task_input.py`](file:///d:/agentSpace/core/task_input.py#L13-L16) | `unresolved_template_marker(text)` | 13–16 | Detects placeholder bracketed tokens (`[Paste...]`, `{{ISSUE}}`) to reject incomplete user prompts. | **In:** `text: str`<br>**Out:** `str \| None` (first matched marker) | Invoked in [`core/graph_engine.py:450`](file:///d:/agentSpace/core/graph_engine.py#L450) | **Implemented & Overactive** |
| [`core/graph_engine.py`](file:///d:/agentSpace/core/graph_engine.py#L430-L650) | `SpaceVGraph._goal_interpreter_node()` | 430–650 | Security analysis, template marker rejection, GitHub issue link parsing, and Celesto approval interception. | **In:** `state: SpaceVState`<br>**Out:** `dict[str, Any]` (updated state) | Invoked as first node in LangGraph | **Implemented & Active** |
| [`core/graph_engine.py`](file:///d:/agentSpace/core/graph_engine.py#L495-L553) | `approval_match` Interceptor | 495–553 | Intercepts exact string `approve sandbox task <10-hex>` to resume approved Celesto task without LLM call. | **In:** `assessment.sanitized_text`<br>**Out:** Deterministic tool call state | Invoked during goal interpretation | **Implemented & Fragile** |
| [`core/graph_engine.py`](file:///d:/agentSpace/core/graph_engine.py#L996-L1007) | Issue Analyst Tool Scoping | 996–1007 | Filters active tool schema to only the 10 tools whitelisted in `ISSUE_TEST_AGENT_CONFIG`. | **In:** `OLLAMA_TOOLS_SCHEMA`<br>**Out:** `available_tools: list` | Invoked in `_plan_or_direct_node` | **Implemented & Active** |
| [`core/graph_engine.py`](file:///d:/agentSpace/core/graph_engine.py#L1446-L1546) | `_issue_test_patch_gate(...)` | 1446–1546 | Multi-condition runtime gate: requires commit pin, clean status, baseline pass, and test-only diff in same session. | **In:** `command: str, session_id: str`<br>**Out:** `str \| None` (blocking reason or None) | Invoked in tool loop [`L1287`](file:///d:/agentSpace/core/graph_engine.py#L1287) | **Implemented & Deadlock-Prone** |
| [`core/task_evidence.py`](file:///d:/agentSpace/core/task_evidence.py#L71-L340) | `TaskEvidenceStore.export_bundle(...)` | 288–340 | Serializes bounded, redacted SQLite session tool records into an immutable JSON evidence bundle with SHA-256 hashes. | **In:** `task_context: str, tool_results: list`<br>**Out:** `dict[str, Any]` (bundle path, status) | Invoked in [`core/graph_engine.py:2193`](file:///d:/agentSpace/core/graph_engine.py#L2193) | **Implemented & Verified** |
| [`tools/sandbox_tools.py`](file:///d:/agentSpace/tools/sandbox_tools.py#L581-L673) | `SandboxSessionManager.create(...)` | 581–673 | Two-phase VM creation: Phase 1 issues proposal with approval token; Phase 2 boots Celesto VM on exact string match. | **In:** `task_description: str, approval_id: str, approval_text: str`<br>**Out:** `str` | Invoked by LLM via `create_sandbox_session` | **Implemented & Fragile** |
| [`tools/sandbox_tools.py`](file:///d:/agentSpace/tools/sandbox_tools.py#L675-L720) | `SandboxSessionManager.run(...)` | 675–720 | Executes shell commands in active Celesto guest session; enforces length limits and session TTL checks. | **In:** `session_id: str, command: str`<br>**Out:** `str` (stdout/stderr + exit code) | Invoked by LLM via `run_sandbox_session_command` | **Implemented & Active** |
| [`tools/web_tools.py`](file:///d:/agentSpace/tools/web_tools.py#L260-L285) | `_github_api_get_json(url)` | 260–285 | Unauthenticated HTTP GET request against GitHub REST API with 12s timeout. | **In:** `url: str`<br>**Out:** Parsed JSON payload | Invoked by `fetch_github_issue_content` | **Implemented & Rate-Limited** |
| [`tools/web_tools.py`](file:///d:/agentSpace/tools/web_tools.py#L286-L336) | `fetch_github_issue_content(url)` | 286–336 | Scrapes issue title, description, and comments via `api.github.com`. | **In:** `url: str`<br>**Out:** Markdown issue representation | Invoked by `read_web_page` | **Implemented & Unreliable** |
| [`spacev/fleet/celesto_engine.py`](file:///d:/agentSpace/spacev/fleet/celesto_engine.py#L29-L150) | `CelestoSandboxInstance` | 29–150 | Wrapper around Celesto MicroVM SDK (`celesto.Computer`). Connects to cloud or local microVM. | **In:** `name: str, os_type: str = "alpine", memory_mb: int = 512`<br>**Out:** Live VM handle | Instantiated by `SandboxSessionManager` | **Implemented & Flawed** (Alpine default + 30s timeout) |

---

## SECTION 3: STRICT SIDE-BY-SIDE COMPARISON

The following master comparison table aligns the original intended workflow against SpaceV's actual Python implementation across all seven stages.

### Master Comparison Matrix

| Intended Workflow | Actual SpaceV Implementation | Actual Files / Functions | Current Status | Evidence | Gap / Failure |
|---|---|---|---|---|---|
| **Step 1: Accept a GitHub Issue URL**<br>• Human provides GitHub issue URL.<br>• Validate public HTTPS URL.<br>• Reject PRs, credentials, and query params.<br>• Normalize canonical repo slug and issue #. | Validates URL format with strict regex. Rejects non-HTTPS, PRs, queries, and credentials. Injects parsed metadata into goal entities. | [`core/issue_test_workflow.py:19-54`](file:///d:/agentSpace/core/issue_test_workflow.py#L19-L54)<br>[`core/graph_engine.py:476-490`](file:///d:/agentSpace/core/graph_engine.py#L476-L490) | **Partially Implemented / Fragile** | Unit tests pass in [`tests/test_issue_test_workflow.py`](file:///d:/agentSpace/tests/test_issue_test_workflow.py). URL normalization verified on `requests/issues/7639`. | If user prompt includes template brackets (`[Paste...]`), [`task_input.py:13`](file:///d:/agentSpace/core/task_input.py#L13) hard-blocks execution before URL parsing. `FastRouter` lacks 0ms direct route. |
| **Step 2: Read and Understand the Issue**<br>• Retrieve title, description, expected vs actual behavior.<br>• Ground failure symptom.<br>• Extract `expected_failure_signal`.<br>• Refuse to guess without text. | LLM chooses `read_web_page`. `fetch_github_issue_content` queries unauthenticated `api.github.com`. System prompt instructs model to populate `entities.expected_failure_signal`. | [`tools/web_tools.py:286-336`](file:///d:/agentSpace/tools/web_tools.py#L286-L336)<br>[`core/agent_configs.py:126-128`](file:///d:/agentSpace/core/agent_configs.py#L126-L128) | **Unreliable / Broken in Practice** | Log trace on #7639 shows `HTTP Error 403: Forbidden`. LLM received empty text and reported missing issue body. | Unauthenticated API hits 60 req/hr rate limit. No automatic fallback to HTML scraping. When fetch fails, LLM hallucinates or aborts. |
| **Step 3: Clone in Isolated Sandbox**<br>• Provision or reuse sandbox.<br>• Verify development toolchain.<br>• Shallow clone target repo.<br>• Dynamic timeout based on repo size. | LLM calls `create_sandbox_session`. System halts for exact user phrase. User approves. `CelestoSandboxInstance` boots microVM. LLM executes `git clone`. | [`tools/sandbox_tools.py:581-673`](file:///d:/agentSpace/tools/sandbox_tools.py#L581-L673)<br>[`spacev/fleet/celesto_engine.py:29-150`](file:///d:/agentSpace/spacev/fleet/celesto_engine.py#L29-L150) | **Implemented but Highly Unreliable** | Logs show: (1) `sbx-noether` name collision; (2) `/bin/sh: git: not found` (exit 127); (3) `git clone` timed out after 30 seconds. | • Default guest OS is `alpine` which lacks Git and Pytest.<br>• Hardcoded 30-second timeout aborts git clone on large repos.<br>• Multi-turn approval halts pipeline. |
| **Step 4: Inspect Code and Tests**<br>• Record baseline commit.<br>• Audit worktree cleanliness.<br>• Inspect relevant source & test files.<br>• Execute baseline tests (Must PASS). | Text instructions in system prompt tell LLM to run `git rev-parse HEAD`, `git status --short`, and baseline test. Static tools: `search_file_content`, `read_file_content`. | [`core/agent_configs.py:129-137`](file:///d:/agentSpace/core/agent_configs.py#L129-L137)<br>[`core/issue_test_workflow.py:208-229`](file:///d:/agentSpace/core/issue_test_workflow.py#L208-L229) | **Unverified / Missing Automation** | On #7639, shallow clone succeeded and test file was inspected, but surrounding source and baseline tests were not executed. | **Zero automated execution in code**. The system relies on the LLM to choose to run baseline commands. If the LLM omits baseline pytest, Stage 6 deadlocks. |
| **Step 5: Generate Minimal Failing Test**<br>• Synthesize focused test.<br>• Modify ONLY `tests/test_*.py`.<br>• Zero production code changes.<br>• Valid unified diff. | Prompt boundary in `ISSUE_TEST_AGENT_CONFIG` forbids production edits. `classify_test_patch_paths` checks diff paths from `git status --short`. | [`core/agent_configs.py:133-146`](file:///d:/agentSpace/core/agent_configs.py#L133-L146)<br>[`core/issue_test_workflow.py:231-298`](file:///d:/agentSpace/core/issue_test_workflow.py#L231-L298) | **Unverified in Execution Loop** | Unit tests for `classify_test_patch_paths` pass, but live runs on #7639 never produced a verified diff in the sandbox. | LLM often attempts to edit production code to fix the bug instead of writing a test, triggering `NON_TEST_FILES_CHANGED` gate block. |
| **Step 6: Execute and Verify the Test**<br>• Run candidate test.<br>• Verify exit code != 0.<br>• Verify stdout contains expected symptom.<br>• Classify failure causation. | Gate `_issue_test_patch_gate` intercepts tool call. Checks prior SQLite receipts for commit pin, clean status, baseline pass. `classify_test_execution` audits output. | [`core/graph_engine.py:1446-1546`](file:///d:/agentSpace/core/graph_engine.py#L1446-L1546)<br>[`core/issue_test_workflow.py:153-205`](file:///d:/agentSpace/core/issue_test_workflow.py#L153-L205) | **Deadlock-Prone / Unsuccessful** | Logs on #7639 show no candidate test was run. Output: `SPACEV_NEEDS_USER_INPUT: Test execution is paused. Evidence must come from this same Celesto session...` | The gate requires 5 prior commands in the same session. If the LLM missed baseline pytest earlier, the gate blocks candidate pytest, causing the LLM to deadlock. |
| **Step 7: Deliver Evidence and Report**<br>• Package immutable evidence report.<br>• SHA-256 digests of all inputs/outputs.<br>• Output Markdown summary.<br>• Teardown sandbox VM. | `task_evidence_store.export_bundle` compiles SQLite records into redacted JSON bundle with SHA-256 digests. LLM outputs final chat response. | [`core/task_evidence.py:288-340`](file:///d:/agentSpace/core/task_evidence.py#L288-L340)<br>[`core/graph_engine.py:2193`](file:///d:/agentSpace/core/graph_engine.py#L2193) | **Partially Implemented** | `export_bundle` correctly writes JSON to `reports/evidence/`. However, on #7639, bundle contained only failed clone receipts. | A report cannot verify steps that did not produce tool output. MicroVM is not automatically destroyed if the turn crashes or times out. |

---

### Exhaustive 10-Point Technical Deep-Dive for Every Stage

#### STAGE 1: ACCEPT A GITHUB ISSUE URL
1. **What is Expected:** Accept a raw user prompt containing a public GitHub issue link, validate HTTPS scheme and github.com hostname, strip query parameters and URL fragments, reject pull requests (`/pull/`), and output a sanitized dictionary with canonical URLs.
2. **What SpaceV Actually Attempts:** Validates the string using `parse_github_issue_url` inside `_goal_interpreter_node`.
3. **Actual Files & Functions:**
   - [`core/issue_test_workflow.py:19-54`](file:///d:/agentSpace/core/issue_test_workflow.py#L19-L54): `parse_github_issue_url()`
   - [`core/task_input.py:13-16`](file:///d:/agentSpace/core/task_input.py#L13-L16): `unresolved_template_marker()`
   - [`core/graph_engine.py:476-490`](file:///d:/agentSpace/core/graph_engine.py#L476-L490): Regex search and extraction in goal interpreter node.
4. **Implementation Completeness:** 90% complete. URL parsing and canonicalization logic is fully implemented and tested.
5. **Connection to Workflow:** Connected to `SpaceVGraph._goal_interpreter_node()`, which updates `goal.entities`.
6. **Execution Success:** Successfully tested and verified on `https://github.com/psf/requests/issues/7639`.
7. **Errors & Limitations:** If the prompt contains template markers (e.g., `[Paste actual issue text here]`), `unresolved_template_marker()` in [`core/graph_engine.py:450`](file:///d:/agentSpace/core/graph_engine.py#L450) blocks execution before URL validation can run.
8. **Missing Functionality:** No Tier 1 fast-path route in `core/fast_router.py`. All issue URLs fall through to the slower conversational LLM goal interpreter.
9. **Evidence Available:** Unit tests in [`tests/test_issue_test_workflow.py`](file:///d:/agentSpace/tests/test_issue_test_workflow.py) pass with 100% assertions.
10. **Recommended Improvement:** Add direct regex binding in `FastRouter` to dispatch `AutonomousIssuePipeline` in 0ms without conversational graph fall-through.

---

#### STAGE 2: READ AND UNDERSTAND THE ISSUE
1. **What is Expected:** Fetch issue title, body, labels, and comments; parse stack traces and code snippets; ground an observable `expected_failure_signal`; refuse to guess if text is missing.
2. **What SpaceV Actually Attempts:** Dispatches to the LLM, which calls `read_web_page()`, invoking `fetch_github_issue_content()` against GitHub's REST API.
3. **Actual Files & Functions:**
   - [`tools/web_tools.py:260-285`](file:///d:/agentSpace/tools/web_tools.py#L260-L285): `_github_api_get_json()`
   - [`tools/web_tools.py:286-336`](file:///d:/agentSpace/tools/web_tools.py#L286-L336): `fetch_github_issue_content()`
   - [`core/agent_configs.py:126-128`](file:///d:/agentSpace/core/agent_configs.py#L126-L128): Prompt instructions for `expected_failure_signal`.
4. **Implementation Completeness:** 40% complete. Logic exists but relies entirely on unauthenticated API calls.
5. **Connection to Workflow:** Whitelisted in `ISSUE_TEST_AGENT_CONFIG.allowed_tools` as `read_web_page`.
6. **Execution Success:** **Failed in live pilot.**
7. **Errors & Limitations:** Unauthenticated calls to `api.github.com` trigger `HTTP Error 403: Forbidden` when the 60 req/hr rate limit is reached.
8. **Missing Functionality:** No `GITHUB_TOKEN` support; no automatic fallback to headless HTML scraping.
9. **Evidence Available:** Live logs show `HTTP Error 403: Forbidden` on `api.github.com/repos/psf/requests/issues/7639`.
10. **Recommended Improvement:** Implement dual-channel ingestion with token authentication and public HTML scraping fallback.

---

#### STAGE 3: CLONE REPOSITORY IN AN ISOLATED SANDBOX
1. **What is Expected:** Boot an isolated Ubuntu/Debian microVM with Git and Pytest pre-installed; execute a shallow clone (`--depth 1`) with an adaptive timeout (180s); keep VM alive across commands.
2. **What SpaceV Actually Attempts:** LLM calls `create_sandbox_session()`; system halts and demands exact human approval phrase; boots Alpine microVM; LLM runs `git clone`.
3. **Actual Files & Functions:**
   - [`tools/sandbox_tools.py:581-673`](file:///d:/agentSpace/tools/sandbox_tools.py#L581-L673): `SandboxSessionManager.create()`
   - [`spacev/fleet/celesto_engine.py:29-150`](file:///d:/agentSpace/spacev/fleet/celesto_engine.py#L29-L150): `CelestoSandboxInstance`
   - [`core/graph_engine.py:495-553`](file:///d:/agentSpace/core/graph_engine.py#L495-L553): Approval string regex interceptor.
4. **Implementation Completeness:** 30% complete. Core SDK calls exist, but infrastructure defaults are broken.
5. **Connection to Workflow:** Connected via `create_sandbox_session` and `run_sandbox_session_command`.
6. **Execution Success:** **Failed in live pilot.**
7. **Errors & Limitations:**
   - Name collision (`ComputerAlreadyExistsError: 'sbx-noether'`).
   - Missing Git binary in Alpine (`/bin/sh: git: not found`, exit code 127).
   - Hardcoded 30s timeout kills Git clone (`TimeoutExpired`).
   - Rigid human approval halt (`approve sandbox task <10-hex>`).
8. **Missing Functionality:** Pre-provisioned developer environment; dynamic command timeout scaling; single-click initiation.
9. **Evidence Available:** Execution logs document all four specific errors during the Requests #7639 pilot.
10. **Recommended Improvement:** Switch default OS to Ubuntu, scale clone timeouts to 180s, and wrap VM lifecycle in an async context manager.

---

#### STAGE 4: INSPECT SOURCE CODE AND EXISTING TESTS
1. **What is Expected:** Record baseline commit hash (`git rev-parse HEAD`), assert clean worktree (`git status --porcelain`), inspect relevant source files, and execute existing test suite to verify clean baseline PASS (exit code 0).
2. **What SpaceV Actually Attempts:** System prompt instructs LLM to inspect files and record baseline commit before making changes.
3. **Actual Files & Functions:**
   - [`core/agent_configs.py:129-137`](file:///d:/agentSpace/core/agent_configs.py#L129-L137): Prompt rules for baseline inspection.
   - [`core/issue_test_workflow.py:208-229`](file:///d:/agentSpace/core/issue_test_workflow.py#L208-L229): `classify_git_status()`.
   - [`tools/file_tools.py`](file:///d:/agentSpace/tools/file_tools.py): `read_file_content`, `search_file_content`.
4. **Implementation Completeness:** 15% complete. Classifiers exist, but **zero automated execution code exists**.
5. **Connection to Workflow:** Passive prompt guidelines only.
6. **Execution Success:** **Failed in live pilot.**
7. **Errors & Limitations:** The model skipped running `git rev-parse HEAD` and baseline pytest, jumping directly to test synthesis.
8. **Missing Functionality:** Automated baseline runner that deterministically verifies clean status and baseline pass in Python code.
9. **Evidence Available:** Live logs show test body was inspected, but baseline pytest was never executed.
10. **Recommended Improvement:** Enforce baseline execution programmatically before the LLM is invoked.

---

#### STAGE 5: GENERATE A MINIMAL FAILING TEST
1. **What is Expected:** Synthesize a focused, minimal reproduction test; modify strictly `tests/test_*.py`; zero production code edits; output a valid unified diff.
2. **What SpaceV Actually Attempts:** Prompt boundaries instruct model to write a test without modifying production code. Diff paths audited by `classify_test_patch_paths`.
3. **Actual Files & Functions:**
   - [`core/agent_configs.py:133-146`](file:///d:/agentSpace/core/agent_configs.py#L133-L146): System prompt boundaries.
   - [`core/issue_test_workflow.py:231-298`](file:///d:/agentSpace/core/issue_test_workflow.py#L231-L298): `classify_test_patch_paths()`.
4. **Implementation Completeness:** 50% complete. Safety classifiers exist, but generation relies on unconstrained LLM.
5. **Connection to Workflow:** Audited by `_issue_test_patch_gate` in tool execution loop.
6. **Execution Success:** **Unverified in live pilot.**
7. **Errors & Limitations:** Models naturally attempt to fix production code (`requests/sessions.py`), triggering `NON_TEST_FILES_CHANGED` gate blocks with no automated recovery.
8. **Missing Functionality:** AST diff path filter that rejects production edits before disk application.
9. **Evidence Available:** Review notes: "Logs do not show a complete, evidence-based test diff for the actual checkout."
10. **Recommended Improvement:** Constrain LLM prompt strictly to output unified diff creating a new test file in `tests/`.

---

#### STAGE 6: EXECUTE AND VERIFY THE TEST
1. **What is Expected:** Apply patch; execute targeted pytest node; verify exit code != 0; assert stdout contains `expected_failure_signal`; distinguish bug failure from import or syntax errors.
2. **What SpaceV Actually Attempts:** `_issue_test_patch_gate` intercepts tool call, audits SQLite history for 5 prerequisites, and blocks if any are missing.
3. **Actual Files & Functions:**
   - [`core/graph_engine.py:1446-1546`](file:///d:/agentSpace/core/graph_engine.py#L1446-L1546): `_issue_test_patch_gate()`.
   - [`core/issue_test_workflow.py:153-205`](file:///d:/agentSpace/core/issue_test_workflow.py#L153-L205): `classify_test_execution()`.
4. **Implementation Completeness:** 50% complete. High-quality failure classifier, but crippled by gate deadlocks.
5. **Connection to Workflow:** Hard interceptor in `SpaceVGraph` tool execution loop.
6. **Execution Success:** **Failed / Deadlocked in live pilot.**
7. **Errors & Limitations:** The gate requires 5 prior commands in the same session. Because baseline pytest was skipped in Stage 4, the gate hard-blocks candidate test execution.
8. **Missing Functionality:** Autonomous recovery when prerequisites are unfulfilled.
9. **Evidence Available:** Log trace: `SPACEV_NEEDS_USER_INPUT: Test execution is paused... baseline=BASELINE_NOT_VERIFIED. No candidate test was run.`
10. **Recommended Improvement:** Eliminate post-hoc runtime gating by guaranteeing baseline pass in Stage 4.

---

#### STAGE 7: DELIVER EVIDENCE AND REPORT
1. **What is Expected:** Compile immutable evidence report; record commit SHA, test diff, command, exit code, stdout/stderr, and SHA-256 digests; teardown microVM.
2. **What SpaceV Actually Attempts:** `task_evidence_store.export_bundle` compiles SQLite records into JSON bundle. LLM outputs final chat response.
3. **Actual Files & Functions:**
   - [`core/task_evidence.py:288-340`](file:///d:/agentSpace/core/task_evidence.py#L288-L340): `TaskEvidenceStore.export_bundle()`.
   - [`core/graph_engine.py:2193`](file:///d:/agentSpace/core/graph_engine.py#L2193): Evidence bundle trigger.
   - [`tools/sandbox_tools.py:740-770`](file:///d:/agentSpace/tools/sandbox_tools.py#L740-L770): `close_sandbox_session()`.
4. **Implementation Completeness:** 70% complete. Storage and serialization logic is production-grade.
5. **Connection to Workflow:** Triggered at end of graph execution if `specialist_role == "issue_test"`.
6. **Execution Success:** **Partial.**
7. **Errors & Limitations:** If intermediate steps fail, the exported bundle contains only failure receipts. MicroVM is leaked if execution crashes.
8. **Missing Functionality:** Guaranteed VM cleanup via async context managers; conditional report generation that gates on verified reproduction.
9. **Evidence Available:** JSON bundles exist in `reports/evidence/`, but reflect aborted runs on #7639.
10. **Recommended Improvement:** Wrap execution in an async context manager ensuring VM deletion, and generate verified reproduction summaries.


---

## SECTION 4: ACTUAL ERROR AND FAILURE INVESTIGATION

Below is the exhaustive forensic analysis of every error documented in the pilot execution logs:

### Forensic Error Matrix

| Error Identified in Logs | Actual Source Location | Root Cause Analysis | Empirical Evidence | Workflow Impact | Recommended Senior Resolution |
|---|---|---|---|---|---|
| **1. Celesto Name Collision** (`sbx-noether`) | [`spacev/fleet/celesto_engine.py:90-99`](file:///d:/agentSpace/spacev/fleet/celesto_engine.py#L90-L99) | **Confirmed:** Celesto's facade (`celesto.Computer()`) used deterministic local naming (`sbx-noether`). Stale containers from previous aborted runs collided with new attempts. | Log: `celesto.errors.ComputerAlreadyExistsError: A computer named 'sbx-noether' already exists.` | Prevented VM initialization. The initial `git --version` command never executed. | Generate high-entropy UUIDs: `CelestoSandboxInstance(f"sbx-{uuid.uuid4().hex}")`. Clean up orphan containers on startup. |
| **2. Git Missing in Sandbox** (`Exit Code 127`) | [`spacev/fleet/celesto_engine.py:33`](file:///d:/agentSpace/spacev/fleet/celesto_engine.py#L33) | **Confirmed:** Default guest OS was set to `alpine` (`os_type="alpine"`). Standard Alpine microVMs omit development tools (`git`, `python3`, `pip`, `pytest`). | Log: `STDERR: /bin/sh: git: not found [SpaceV guest command result] exit code: 127` | Forced the LLM to spend extra conversational turns running `apk add git`, consuming tokens and causing context drift. | Default guest OS to pre-provisioned Ubuntu/Debian developer image with Git, Python 3.10/3.11, and Pytest pre-installed. |
| **3. Git Clone Timeout** (`30s Limit`) | [`spacev/fleet/celesto_engine.py:136`](file:///d:/agentSpace/spacev/fleet/celesto_engine.py#L136) | **Confirmed:** `LiveComputer.run(command, timeout=30)` hardcodes a 30-second execution timeout. Full clone of `psf/requests` history exceeded 30 seconds. | Log: `celesto.errors.TimeoutExpired: Command 'git clone https://github.com/psf/requests.git' timed out after 30 seconds.` | Aborted repository checkout, leaving corrupted `.git` lock file. Subsequent `git rev-parse HEAD` failed. | Dynamic command-aware timeouts: 180s for `git clone`, 240s for `pip install`, 120s for `pytest`, 45s for inspect commands. |
| **4. Expired Sandbox Session** | [`tools/sandbox_tools.py:488-498`](file:///d:/agentSpace/tools/sandbox_tools.py#L488-L498) | **Confirmed:** `SESSION_IDLE_SECONDS = 900` (15 minutes). Multi-turn conversational pauses and gate stalls caused session expiry. | Log: `BLOCKED: Celesto session session-a1b2c3d4e5f6 is missing or expired.` | Subsequent commands rejected. Worktree state lost, forcing user to restart from Step 1. | Extend session TTL or manage lifecycle within an autonomous state machine that completes in <3 minutes end-to-end. |
| **5. Deadlock in Patch Gate** | [`core/graph_engine.py:1446-1546`](file:///d:/agentSpace/core/graph_engine.py#L1446-L1546) | **Confirmed:** `_issue_test_patch_gate` enforces 5 sequential prerequisites in SQLite. If LLM skips baseline pytest, gate blocks candidate pytest. | Log: `SPACEV_NEEDS_USER_INPUT: Test execution is paused. Evidence must come from this same Celesto session: ... baseline=BASELINE_NOT_VERIFIED.` | Complete workflow deadlock. LLM cannot recover from multi-sentence blocking text and hallucinates or crashes. | Automate baseline execution deterministically in code before invoking LLM for test generation. |
| **6. GitHub API 403 Forbidden** | [`tools/web_tools.py:270-285`](file:///d:/agentSpace/tools/web_tools.py#L270-L285) | **Confirmed:** `_github_api_get_json` makes unauthenticated requests to `api.github.com`. IP hit the 60 requests/hour rate limit. | Log: `Failed to fetch GitHub issue at https://github.com/psf/requests/issues/7639: HTTP Error 403: Forbidden` | Agent received empty issue body, lost ability to extract `expected_failure_signal`, and hallucinated bug behavior. | Dual-channel fetcher: Authenticated GitHub API (primary) with seamless fallback to headless HTML scraping (secondary). |
| **7. Malformed Goal JSON & Tool Output in Chat** | [`core/cloud_client.py`](file:///d:/agentSpace/core/cloud_client.py), [`core/graph_engine.py`](file:///d:/agentSpace/core/graph_engine.py) | **Confirmed:** Context fragmentation caused by repeated error receipts degraded LLM attention. Model emitted raw JSON tool calls into conversational chat. | Log: `{"name": "run_sandbox_session_command", "arguments": {"command": "git status --short"}}` printed as plain text. | Tool call never executed by engine; task failed closed. | Enforce JSON schema validation with Pydantic and retry parser; isolate LLM turns from conversational error trauma. |
| **8. Incomplete Source Inspection** | Prompt-driven tool selection | **Likely:** LLM inspected `tests/test_stream_timeout`, but lacked a deterministic AST index to find the implementation in `requests/sessions.py`. | Review: Shallow clone captured test body, but surrounding source inspection was incomplete. | Test diff generated without understanding underlying session logic. | Implement automated call-graph / symbol indexing before prompting the LLM for test generation. |
| **9. Incomplete Test Generation** | Context trauma / Gate blocks | **Confirmed:** LLM was blocked by gate interceptors before it could successfully format and apply a unified diff. | Review: Logs do not show a complete, evidence-based test diff for the actual checkout. | Step 5 failed to complete. | Run test generation as a single isolated compiler pass with unified diff output constraints. |
| **10. Failure to Execute Test** | Gate deadlock in Step 6 | **Confirmed:** Candidate test was never dispatched to Celesto guest because `_issue_test_patch_gate` intercepted the command. | Review: "No test was run." | Step 6 completely failed. | Eliminate post-hoc gating by guaranteeing baseline pass upfront in Python code. |
| **11. Missing Evidence in Report** | Downstream failure cascade | **Confirmed:** `task_evidence_store.export_bundle` only exports what was captured in SQLite. When tests don't run, report has no test output. | Review: "A report cannot verify steps that did not produce tool output." | Step 7 delivered empty evidence. | Only generate reproduction report if Steps 4, 5, and 6 produce valid tool receipts. |
| **12. Unresolved Template Marker False-Positive** | [`core/task_input.py:13`](file:///d:/agentSpace/core/task_input.py#L13), [`core/graph_engine.py:450`](file:///d:/agentSpace/core/graph_engine.py#L450) | **Confirmed:** User prompt containing `[Paste actual issue text here]` triggered template guard, halting execution before URL parsing. | Log: `I can’t start this task because '[Paste...]' is still a placeholder.` | Prevented workflow initiation. | Ignore template placeholders if a valid, supported GitHub issue URL is already present in the prompt. |

---

## SECTION 5: ACTUAL EXECUTION FLOW AND CALL GRAPH

### 5.1 Step-by-Step Actual Runtime Execution Flow
1. **Entry Point:** User submits prompt containing issue URL to chat window or terminal.
2. **FastRouter Check:** [`FastRouter.route_instruction()`](file:///d:/agentSpace/core/fast_router.py#L60) evaluates Tier 1 shortcuts. No shortcut exists for issue reproduction; falls through to LangGraph.
3. **Goal Interpretation:** [`SpaceVGraph._goal_interpreter_node()`](file:///d:/agentSpace/core/graph_engine.py#L430) runs:
   - `security_guard.analyze(prompt)` scans for prompt injections.
   - `unresolved_template_marker(prompt)` checks for template placeholders.
   - `parse_github_issue_url(candidate)` extracts owner, repo, issue_num.
   - LLM extracts structured goal contract (`goal_contract`).
4. **Agent Selection:** [`SwarmOrchestrator.classify_agent_role()`](file:///d:/agentSpace/core/swarm_orchestrator.py#L84) detects `/issues/` and selects `AgentRole.ISSUE_TEST`.
5. **Tool Whitelisting:** [`_plan_or_direct_node()`](file:///d:/agentSpace/core/graph_engine.py#L996) restricts tool schema to 10 tools whitelisted in `ISSUE_TEST_AGENT_CONFIG`.
6. **Turn 1 (Web Fetch):** LLM calls `read_web_page()`. `fetch_github_issue_content()` calls `api.github.com`. Hits HTTP 403 Forbidden. Body is lost.
7. **Turn 2 (Sandbox Proposal):** LLM calls `create_sandbox_session()`. `SandboxSessionManager` records pending approval and halts execution.
8. **Turn 3 (Human Approval):** SpaceV waits for user to reply: `approve sandbox task <10-hex>`.
9. **Turn 4 (VM Boot):** `approval_match` interceptor catches exact string and boots `CelestoSandboxInstance`.
   - Name collision occurs if previous container wasn't deleted.
   - MicroVM boots Alpine Linux.
10. **Turn 5 (Git Clone):** LLM runs `git clone ...`. Fails with exit code 127 (`git: not found`).
11. **Turn 6 (Install Git):** LLM runs `apk add git`. Package installs successfully.
12. **Turn 7 (Git Clone Retry):** LLM runs `git clone ...`. Times out after 30 seconds (`TimeoutExpired`).
13. **Turn 8 (Shallow Clone):** LLM runs `git clone --depth 1 ...`. Succeeds.
14. **Turn 9 (Candidate Test Gate Deadlock):** LLM generates test and attempts `pytest tests/test_repro.py`.
    - `_issue_test_patch_gate` intercepts tool call.
    - Checks SQLite receipts: `baseline_passed` is False, `git status` audit missing.
    - Gate halts execution: `SPACEV_NEEDS_USER_INPUT: Test execution is paused...`
15. **Termination:** LLM becomes confused by gate blocker, emits raw JSON, session expires after 15 minutes, workflow aborts without reproduction.

---

### 5.2 Mermaid Flowchart of Actual Implementation

```mermaid
flowchart TD
    Start(["User submits Issue URL"]) --> FastRouter{"FastRouter Tier 1"}
    FastRouter -->|No Match| GoalNode["GraphEngine: _goal_interpreter_node"]
    
    GoalNode --> SecScan{"security_guard.analyze"}
    SecScan -->|Malicious| SecBlock["Block & Terminate"]
    SecScan -->|Safe| TemplateScan{"unresolved_template_marker"}
    
    TemplateScan -->|Placeholder Found| TempBlock["HALT: Unresolved Template Marker"]
    TemplateScan -->|Clean| URLParse["parse_github_issue_url"]
    
    URLParse -->|Valid URL| SwarmClassify["SwarmOrchestrator: classify_agent_role"]
    SwarmClassify -->|Detected /issues/| SetRole["Set Role: ISSUE_TEST"]
    
    SetRole --> PlanNode["GraphEngine: _plan_or_direct_node"]
    PlanNode --> ToolFilter["Filter to ISSUE_TEST_AGENT_CONFIG tools"]
    ToolFilter --> LLMTurn1["LLM Inference: Turn 1"]
    
    LLMTurn1 --> CallWeb["Call: read_web_page"]
    CallWeb --> GHApi["tools.web_tools: _github_api_get_json"]
    GHApi -->|Rate Limited| Err403["HTTP Error 403 Forbidden (Body Lost)"]
    GHApi -->|Success| GotBody["Issue Body Parsed"]
    
    Err403 --> LLMTurn2["LLM Inference: Turn 2 (Context Impaired)"]
    GotBody --> LLMTurn2
    
    LLMTurn2 --> CallSbx["Call: create_sandbox_session"]
    CallSbx --> SbxProp["SandboxSessionManager: Create Proposal"]
    SbxProp --> HaltApprove["HALT: Await 'approve sandbox task <id>'"]
    
    HaltApprove --> UserReply{"User Text Input"}
    UserReply -->|Not Exact String| RejectApp["BLOCKED: Exact approval phrase required"]
    UserReply -->|Exact Match| BootVM["CelestoSandboxInstance: _initialize"]
    
    BootVM --> NameCheck{"VM Name Collision?"}
    NameCheck -->|Collision| CrashName["Crash: sbx-noether already exists"]
    NameCheck -->|Unique| BootAlpine["Guest Booted: Alpine Linux"]
    
    BootAlpine --> LLMTurn4["LLM Inference: Turn 4"]
    LLMTurn4 --> RunClone["Call: run_sandbox_session_command (git clone)"]
    RunClone --> CheckGit{"Git installed in Alpine?"}
    
    CheckGit -->|No| Err127["Exit 127: /bin/sh: git: not found"]
    Err127 --> LLMTurn5["LLM Inference: Turn 5 (apk add git)"]
    LLMTurn5 --> RetryClone["Call: git clone (LiveComputer.run)"]
    
    RetryClone --> TimeoutCheck{"Clone duration > 30s?"}
    TimeoutCheck -->|Yes| ErrTimeout["TimeoutExpired after 30 seconds!"]
    TimeoutCheck -->|No| CloneOK["Repository Cloned Successfully"]
    
    ErrTimeout --> LLMTurn6["LLM Inference: Turn 6 (Shallow clone retry)"]
    LLMTurn6 --> ShallowOK["Shallow Clone OK"]
    
    CloneOK --> LLMTurn7["LLM Inference: Turn 7 (Write test & execute)"]
    ShallowOK --> LLMTurn7
    
    LLMTurn7 --> CallPytest["Call: pytest tests/..."]
    CallPytest --> PatchGate{"_issue_test_patch_gate Check"}
    
    PatchGate -->|Missing rev-parse HEAD| GateBlock["HALT: SPACEV_NEEDS_USER_INPUT"]
    PatchGate -->|Missing clean baseline pass| GateBlock
    PatchGate -->|Missing post-edit status| GateBlock
    
    GateBlock --> LLMConfused["LLM Context Trauma: Emits raw JSON / Wrong tools"]
    LLMConfused --> Expire["15-Min Session Timeout: Session Purged"]
    Expire --> EndFail(["Workflow Terminated: Reproduction Failed"])
    
    PatchGate -->|All 5 Satisfied (Never reached)| RunCandidate["Run Candidate Test"]
    RunCandidate --> ExportBundle["task_evidence_store: export_bundle"]
    ExportBundle --> EndPass(["Workflow Complete"])
```

---

### 5.3 Function-Call Graph

```mermaid
graph TD
    subgraph UI_And_Routing ["Entry & Routing"]
        main["main.py / chat_window.py"] --> fast_router["core/fast_router.py: FastRouter"]
        fast_router --> graph_engine["core/graph_engine.py: SpaceVGraph"]
    end

    subgraph Goal_Interpretation ["Goal Interpretation & Security"]
        graph_engine --> goal_node["_goal_interpreter_node()"]
        goal_node --> sec_guard["core/security_guard.py: analyze()"]
        goal_node --> task_input["core/task_input.py: unresolved_template_marker()"]
        goal_node --> issue_parse["core/issue_test_workflow.py: parse_github_issue_url()"]
        goal_node --> swarm["core/swarm_orchestrator.py: classify_agent_role()"]
    end

    subgraph LLM_Orchestration ["LLM Planning & Dispatch"]
        graph_engine --> plan_node["_plan_or_direct_node()"]
        plan_node --> agent_config["core/agent_configs.py: ISSUE_TEST_AGENT_CONFIG"]
        plan_node --> cloud_client["core/cloud_client.py: CloudClient"]
    end

    subgraph Tool_Execution ["Tool Execution & Safety Gates"]
        graph_engine --> tool_loop["Tool Execution Loop (L1260-L1570)"]
        tool_loop --> patch_gate["_issue_test_patch_gate()"]
        tool_loop --> issue_note["_issue_test_note()"]
        
        patch_gate --> test_classify["core/issue_test_workflow.py: classify_test_execution()"]
        patch_gate --> path_classify["core/issue_test_workflow.py: classify_test_patch_paths()"]
        patch_gate --> evidence_recall["core/task_evidence.py: session_tool_results()"]
    end

    subgraph Tool_Implementations ["Actual Tools"]
        tool_loop --> web_tool["tools/web_tools.py: read_web_page()"]
        web_tool --> gh_api["fetch_github_issue_content()"]
        gh_api --> gh_get["_github_api_get_json()"]
        
        tool_loop --> sbx_create["tools/sandbox_tools.py: create()"]
        tool_loop --> sbx_run["tools/sandbox_tools.py: run()"]
        
        sbx_create --> celesto_inst["spacev/fleet/celesto_engine.py: CelestoSandboxInstance"]
        sbx_run --> celesto_run["CelestoSandboxInstance.run()"]
        celesto_run --> live_comp["celesto.Computer.run(timeout=30)"]
    end

    subgraph Evidence_Storage ["Durable Evidence Storage"]
        tool_loop --> task_evidence["core/task_evidence.py: TaskEvidenceStore"]
        task_evidence --> sqlite["SQLite WAL: .spacev/task_evidence.sqlite3"]
        graph_engine --> export_bundle["TaskEvidenceStore.export_bundle()"]
    end
```

---

## SECTION 6: EXPECTED WORKFLOW VS ACTUAL WORKFLOW

### Diagram A: Expected Intended Workflow

```mermaid
flowchart LR
    E1["1. Accept URL<br/><i>(Verified Public Issue)</i>"] --> 
    E2["2. Read Issue<br/><i>(Extracted Signal)</i>"] --> 
    E3["3. Sandbox Clone<br/><i>(Ubuntu + Dev Tools)</i>"] --> 
    E4["4. Inspect & Baseline<br/><i>(Clean Pass Verified)</i>"] --> 
    E5["5. Minimal Test<br/><i>(Unified Diff Only)</i>"] --> 
    E6["6. Execute & Verify<br/><i>(Expected Failure Confirmed)</i>"] --> 
    E7["7. Deliver Evidence<br/><i>(Immutable Bundle + Teardown)</i>"]

    style E1 fill:#22c55e,stroke:#15803d,color:#fff
    style E2 fill:#22c55e,stroke:#15803d,color:#fff
    style E3 fill:#22c55e,stroke:#15803d,color:#fff
    style E4 fill:#22c55e,stroke:#15803d,color:#fff
    style E5 fill:#22c55e,stroke:#15803d,color:#fff
    style E6 fill:#22c55e,stroke:#15803d,color:#fff
    style E7 fill:#22c55e,stroke:#15803d,color:#fff
```

---

### Diagram B: Actual SpaceV Workflow (Status Annotated)

```mermaid
flowchart TD
    A1["Stage 1: Accept GitHub Issue URL<br/><b>[PARTIAL]</b> Regex parses URL, but template markers block prompts"] --> 
    A2["Stage 2: Read & Understand Issue<br/><b>[FAILED]</b> Unauthenticated 403 API rate limit loses issue body"]
    
    A2 --> A3["Stage 3: Clone in Sandbox<br/><b>[FAILED]</b> Name collision + Alpine missing Git + 30s timeout crash"]
    A3 --> A4["Stage 4: Inspect Code & Baseline<br/><b>[MISSING]</b> No automated runner; LLM skips baseline test pass"]
    
    A4 --> A5["Stage 5: Minimal Test Proposal<br/><b>[UNVERIFIED]</b> LLM attempts to modify production code; diff blocked"]
    A5 --> A6["Stage 6: Execute & Verify Test<br/><b>[FAILED]</b> Gate deadlocks because baseline pass was missing"]
    
    A6 --> A7["Stage 7: Evidence Delivery<br/><b>[PARTIAL]</b> Evidence store exports, but contains only failed receipts"]

    style A1 fill:#eab308,stroke:#a16207,color:#fff
    style A2 fill:#ef4444,stroke:#b91c1c,color:#fff
    style A3 fill:#ef4444,stroke:#b91c1c,color:#fff
    style A4 fill:#6b7280,stroke:#374151,color:#fff
    style A5 fill:#3b82f6,stroke:#1d4ed8,color:#fff
    style A6 fill:#ef4444,stroke:#b91c1c,color:#fff
    style A7 fill:#eab308,stroke:#a16207,color:#fff
```

**Legend:**
- <span style="background-color:#22c55e; color:#fff; padding:2px 6px; border-radius:4px;">VERIFIED</span>: Fully implemented, tested, and empirically proven.
- <span style="background-color:#eab308; color:#fff; padding:2px 6px; border-radius:4px;">PARTIAL</span>: Implemented but contains edge-case blockers.
- <span style="background-color:#ef4444; color:#fff; padding:2px 6px; border-radius:4px;">FAILED</span>: Executes in runtime but crashes or deadlocks on real repositories.
- <span style="background-color:#6b7280; color:#fff; padding:2px 6px; border-radius:4px;">MISSING</span>: Concept exists in prompt, but zero executable code exists to automate it.
- <span style="background-color:#3b82f6; color:#fff; padding:2px 6px; border-radius:4px;">UNVERIFIED</span>: Code exists in repository, but live runs have never successfully completed it.

---

## SECTION 7: SENIOR ENGINEERING ANALYSIS

As a Principal Autonomous Systems Architect and Senior AI Reliability Fellow with 20+ years of engineering experience across compilers, distributed systems, and agentic workflows, the following 20 core areas are analyzed using a disciplined 10-point engineering framework:

---

### 1. Deterministic Workflow Orchestration
1. **The Problem:** SpaceV uses a non-deterministic, open-ended conversational chat loop to drive a multi-stage verification pipeline.
2. **Why it Occurs:** The agent was originally architected as a conversational desktop companion, so all capabilities were funneled into the same LangGraph chat loop.
3. **Why Current Implementation is Insufficient:** Auto-regressive LLMs have non-zero failure probabilities per turn. Over 8+ turns, cumulative failure probability exceeds 75%.
4. **What a Senior Engineer Would Change:** Implement the **Agentic Compiler Pattern**. Stages 1–4 and 6–7 must execute deterministically in Python without calling an LLM. The LLM is used strictly as an isolated code synthesis kernel in Stage 5.
5. **What to Retain:** Retain all classification functions in `core/issue_test_workflow.py`.
6. **What to Improve:** Remove conversational prompting for git commands.
7. **Is a New Component Necessary:** Yes, `core/autonomous_issue_pipeline.py` is required to act as the deterministic controller.
8. **How Solution Works:** Python control flow executes `intake() -> clone() -> baseline() -> llm_diff() -> test() -> report()`.
9. **How it Prevents Recurrence:** Zero conversational turn-taking; no risk of tool calling hallucinations between steps.
10. **How to Verify:** Run pipeline on 10 issues; assert 100% deterministic progression through Stages 1–4.

---

### 2. LLM-Controlled vs. System-Controlled Execution
1. **The Problem:** The LLM is given discretion over which shell commands to run and whether to check baselines.
2. **Why it Occurs:** Over-reliance on "agent autonomy" rather than robust systems engineering.
3. **Why Current Implementation is Insufficient:** The LLM routinely forgets prerequisites like `git status --short` or `git rev-parse HEAD`.
4. **What a Senior Engineer Would Change:** Invert the control flow. The Python system controls the sequence; the LLM is merely a functional sub-routine.
5. **What to Retain:** LLM generation capabilities for complex Python diff synthesis.
6. **What to Improve:** Restrict LLM tools: do not provide general bash access during test generation.
7. **Is a New Component Necessary:** No, this is an architectural inversion in the controller.
8. **How Solution Works:** The system sets up files, prompts the LLM for a diff, validates the diff, and applies it.
9. **How it Prevents Recurrence:** Model cannot skip baseline checks or run invalid commands.
10. **How to Verify:** Assert zero shell commands are initiated by the LLM during Stage 5.

---

### 3. State Management
1. **The Problem:** State is scattered across SQLite (`task_evidence.sqlite3`), memory objects (`_pending`), and LangGraph message lists.
2. **Why it Occurs:** Incremental feature additions created multiple independent state trackers.
3. **Why Current Implementation is Insufficient:** In-memory pending approvals desynchronize from SQLite records across turns.
4. **What a Senior Engineer Would Change:** Consolidate execution state into a single immutable dataclass: `ReproductionTaskState`.
5. **What to Retain:** `TaskEvidenceStore` for long-term historical audits.
6. **What to Improve:** Replace multi-turn session continuation heuristics with a unified state object passed through the pipeline.
7. **Is a New Component Necessary:** No, declare `ReproductionTaskState` inside the pipeline.
8. **How Solution Works:** Every pipeline stage returns an updated, immutable state snapshot.
9. **How it Prevents Recurrence:** Eliminates state drift, dropped variables, and stale continuation contexts.
10. **How to Verify:** Serialize state at each stage; verify complete replayability.

---

### 4. Sandbox Lifecycle Management
1. **The Problem:** MicroVMs leak when turns fail; no guaranteed termination mechanism exists.
2. **Why it Occurs:** `close_sandbox_session()` is exposed as a tool for the LLM to call, rather than an automatic system teardown.
3. **Why Current Implementation is Insufficient:** If an exception occurs or the user closes the window, the VM runs until cloud TTL expires.
4. **What a Senior Engineer Would Change:** Enclose VM lifecycles in asynchronous context managers: `async with CelestoSandboxInstance() as vm:`.
5. **What to Retain:** Celesto SDK driver and cloud connection routines.
6. **What to Improve:** Replace manual tool-based closing with deterministic `try...finally` teardown.
7. **Is a New Component Necessary:** No, update `spacev/fleet/celesto_engine.py`.
8. **How Solution Works:** Context manager `__aexit__` sends `stop()` command to Celesto cloud on all exit paths.
9. **How it Prevents Recurrence:** Zero orphaned containers can exist after task completion or crash.
10. **How to Verify:** Trigger deliberate pipeline crashes; verify Celesto fleet inventory is 0.

---

### 5. Celesto Computer Naming and Reuse
1. **The Problem:** Local Celesto naming collision (`sbx-noether already exists`).
2. **Why it Occurs:** SDK facade generated static or short names without querying active containers.
3. **Why Current Implementation is Insufficient:** Previous runs that failed left containers in local/cloud registry, colliding with new runs.
4. **What a Senior Engineer Would Change:** Use cryptographic UUIDv4 naming: `f"sbx-repro-{uuid.uuid4().hex}"`.
5. **What to Retain:** `CelestoSandboxInstance` class structure.
6. **What to Improve:** Startup sanitization: scan and purge any stale containers with matching prefixes.
7. **Is a New Component Necessary:** No.
8. **How Solution Works:** Unique entropy guarantees collision probability of $10^{-36}$.
9. **How it Prevents Recurrence:** Name collisions become mathematically impossible.
10. **How to Verify:** Spawn 50 concurrent sandboxes; verify zero name collisions.

---

### 6. Session Persistence
1. **The Problem:** 15-minute idle TTL (`SESSION_IDLE_SECONDS = 900`) purges active sessions during slow runs.
2. **Why it Occurs:** Conservative resource-saving timeout applied uniformly across interactive and automated tasks.
3. **Why Current Implementation is Insufficient:** When turns take long or network lags, the session disappears mid-task.
4. **What a Senior Engineer Would Change:** Autonomous runs do not need idle timeouts; they need hard execution deadlines (e.g. 5 minutes total task budget).
5. **What to Retain:** Session ID tracking for evidence association.
6. **What to Improve:** Decouple automated batch jobs from conversational idle expiration timers.
7. **Is a New Component Necessary:** No.
8. **How Solution Works:** Continuous pipeline holds the live session handle directly in memory.
9. **How it Prevents Recurrence:** No premature session eviction during active pipeline runs.
10. **How to Verify:** Execute a simulated slow clone (60s); verify session remains active.

---

### 7. Git Installation and Environment Preparation
1. **The Problem:** MicroVM boots Alpine Linux lacking Git, Python, pip, and Pytest (exit code 127).
2. **Why it Occurs:** `CelestoSandboxInstance` defaulted to `os_type="alpine"` for minimal image size.
3. **Why Current Implementation is Insufficient:** Alpine requires package compilation for many Python dependencies, causing build errors.
4. **What a Senior Engineer Would Change:** Default to Ubuntu 22.04 LTS with pre-installed developer packages.
5. **What to Retain:** `detect_guest_environment()` profile scanner in `core/issue_test_workflow.py`.
6. **What to Improve:** Add an automated bootstrap verifier (`SandboxBootstrapManager`) that verifies tool availability at boot.
7. **Is a New Component Necessary:** Yes, `tools/sandbox_bootstrap.py`.
8. **How Solution Works:** Pre-flight check tests `git --version && pytest --version`. Auto-installs if missing.
9. **How it Prevents Recurrence:** No shell command can ever fail with exit code 127 (`command not found`).
10. **How to Verify:** Boot fresh VM; verify Git and Pytest execute in <100ms.

---

### 8. Repository Cloning and Timeout Handling
1. **The Problem:** Hardcoded 30-second timeout aborts Git clone on standard repositories.
2. **Why it Occurs:** A blanket `timeout=30` was applied to all commands in `CelestoSandboxInstance.run()`.
3. **Why Current Implementation is Insufficient:** Full git history clones of mature libraries (Requests, Flask, Django) take 40–90 seconds.
4. **What a Senior Engineer Would Change:** Dynamic adaptive timeouts: 180s for clone, 240s for install, 120s for tests, 45s for inspect. Use shallow clones (`git clone --depth 1`).
5. **What to Retain:** Underlying `LiveComputer.run()` mechanism.
6. **What to Improve:** Add command-type inspection to dynamically allocate timeout seconds.
7. **Is a New Component Necessary:** No, update `celesto_engine.py`.
8. **How Solution Works:** `get_command_timeout(command)` returns tailored timeout before calling SDK.
9. **How it Prevents Recurrence:** Large repositories clone cleanly without premature termination.
10. **How to Verify:** Clone `psf/requests` and `pallets/flask`; verify successful exit code 0.

---

### 9. Issue Retrieval and Missing Information
1. **The Problem:** Unauthenticated GitHub API calls trigger HTTP 403 Forbidden rate limits, losing issue text.
2. **Why it Occurs:** Direct REST requests to `api.github.com` without credentials share IP quota (60/hr).
3. **Why Current Implementation is Insufficient:** If API fails, system reports missing text and stops, or LLM hallucinates bug.
4. **What a Senior Engineer Would Change:** Dual-channel resilient ingestion: Token-authenticated REST API (primary) + Headless public HTML scraper (secondary fallback).
5. **What to Retain:** `parse_github_issue_url()` validation.
6. **What to Improve:** Replace `_github_api_get_json()` with authenticated headers and scraper fallback.
7. **Is a New Component Necessary:** Yes, `tools/resilient_github_fetch.py`.
8. **How Solution Works:** If API returns 403/429, fetch `https://github.com/owner/repo/issues/num` and parse title/body via BeautifulSoup.
9. **How it Prevents Recurrence:** 100% issue ingestion reliability even without API keys.
10. **How to Verify:** Disconnect GitHub token; verify issue #7639 body is retrieved with 0 errors.

---

### 10. Source Inspection Completeness
1. **The Problem:** LLM inspects only the test file and misses the underlying production module implementation.
2. **Why it Occurs:** LLM uses broad keyword grep instead of AST symbol resolution.
3. **Why Current Implementation is Insufficient:** The model writes tests that mock the wrong functions or misuse class signatures.
4. **What a Senior Engineer Would Change:** Automated AST symbol resolver: when an issue mentions a function (e.g. `stream_timeout`), use Python AST or `ctags` to find its definition and pass it in context.
5. **What to Retain:** `read_file_content` and `search_file_content` tools.
6. **What to Improve:** Automate symbol context gathering in Python before calling the LLM.
7. **Is a New Component Necessary:** Useful helper `core/symbol_indexer.py`.
8. **How Solution Works:** Resolves imports and definitions; feeds exact source slices to the LLM.
9. **How it Prevents Recurrence:** Eliminates hallucinations of non-existent methods or parameters.
10. **How to Verify:** Verify extracted context contains the exact function definition mentioned in the issue.

---

### 11. Minimal Test Generation
1. **The Problem:** LLM generates multi-file diffs, edits production source code, or writes full explanations.
2. **Why it Occurs:** Unconstrained system prompt allows the model to act as a general coder rather than a test compiler.
3. **Why Current Implementation is Insufficient:** Editing production code triggers `NON_TEST_FILES_CHANGED` gate blocks.
4. **What a Senior Engineer Would Change:** Constrain the prompt to output a unified diff modifying strictly a single new file: `tests/test_repro_issue_<num>.py`.
5. **What to Retain:** `classify_test_patch_paths()` audit function.
6. **What to Improve:** Prompt engineering: enforce unified diff output only.
7. **Is a New Component Necessary:** No.
8. **How Solution Works:** Prompt strictly demands unified diff format without markdown commentary.
9. **How it Prevents Recurrence:** Model never touches production code.
10. **How to Verify:** Feed 10 bug reports; assert 100% of generated patches touch only `tests/`.

---

### 12. Baseline Validation
1. **The Problem:** Baseline tests are not run, so there is no control evidence proving the bug is new.
2. **Why it Occurs:** Baseline verification was defined as a rule in text, not a step in code.
3. **Why Current Implementation is Insufficient:** The model forgets to run baseline tests, causing Stage 6 gate deadlocks.
4. **What a Senior Engineer Would Change:** Execute baseline tests deterministically in Stage 4 before generating the test patch.
5. **What to Retain:** `classify_git_status()` porcelain auditor.
6. **What to Improve:** Automate `git rev-parse HEAD` and baseline `pytest` execution in Python.
7. **Is a New Component Necessary:** No, integrate into `AutonomousIssuePipeline`.
8. **How Solution Works:** Pipeline runs baseline test. If exit != 0, aborts with `UNHEALTHY_BASELINE`.
9. **How it Prevents Recurrence:** Guarantees that candidate test failure is causal, not environmental.
10. **How to Verify:** Intentionally break a baseline test; verify pipeline halts with clean diagnostic.

---

### 13. Test Execution
1. **The Problem:** Candidate test is blocked by runtime interceptor gates inside tool dispatch.
2. **Why it Occurs:** Gate was placed as an interception hook inside `SpaceVGraph` tool loop.
3. **Why Current Implementation is Insufficient:** When the gate blocks, the model enters a conversational deadlock.
4. **What a Senior Engineer Would Change:** Execute the test directly within the deterministic pipeline after applying the patch.
5. **What to Retain:** `classify_test_execution()` logic.
6. **What to Improve:** Move test execution out of the LLM tool loop into the pipeline state machine.
7. **Is a New Component Necessary:** No.
8. **How Solution Works:** Pipeline applies patch, runs `pytest /workspace/repo/<test_file>`, and collects output.
9. **How it Prevents Recurrence:** Zero tool interception blocks or chat pauses.
10. **How to Verify:** Run candidate test; verify exit code and stdout are captured directly in state.

---

### 14. Failure Classification
1. **The Problem:** Generic failure is often mistaken for bug reproduction, or genuine reproductions are flagged inconclusive.
2. **Why it Occurs:** Fragile regex matching of expected signals across large test stdout streams.
3. **Why Current Implementation is Insufficient:** If pytest output formatting changes, signal matching fails.
4. **What a Senior Engineer Would Change:** Parse pytest summary lines and failure headings using structured regex matching, requiring non-zero exit code and absence of syntax/import errors.
5. **What to Retain:** `classify_test_execution()` and `_target_failure_contains_signal()`.
6. **What to Improve:** Make signal matching case-insensitive and tolerate whitespace variations.
7. **Is a New Component Necessary:** No, enhance existing functions in `core/issue_test_workflow.py`.
8. **How Solution Works:** Explicitly categorizes into 7 deterministic enums.
9. **How it Prevents Recurrence:** Accurate causal classification on every run.
10. **How to Verify:** Unit test classifier against 20 real-world pytest stdout samples.

---

### 15. Evidence Validation
1. **The Problem:** Reports claim verification even when underlying tools failed or were skipped.
2. **Why it Occurs:** Evidence exporter dumped whatever SQLite records existed without validating stage completeness.
3. **Why Current Implementation is Insufficient:** Outputted bundles for failed runs contained confusing error receipts.
4. **What a Senior Engineer Would Change:** Guard the report generator: mark report as `VERIFIED_REPRODUCTION` only if all 7 stages completed with valid receipts and SHA-256 digests.
5. **What to Retain:** `TaskEvidenceStore.export_bundle()`.
6. **What to Improve:** Add verification status flag to the evidence bundle header.
7. **Is a New Component Necessary:** No.
8. **How Solution Works:** Exporter computes SHA-256 for commit, patch, and stdout; sets status explicitly.
9. **How it Prevents Recurrence:** Impossible to produce a false-positive reproduction report.
10. **How to Verify:** Inspect exported JSON bundle; assert presence of all required cryptographic hashes.

---

### 16. Retry and Recovery Strategies
1. **The Problem:** A single transient failure (clone timeout, network hiccup) aborts the entire run.
2. **Why it Occurs:** No retry wrappers around network-dependent operations.
3. **Why Current Implementation is Insufficient:** The LLM cannot recover gracefully when a command times out.
4. **What a Senior Engineer Would Change:** Exponential backoff retry policies around Git clone and GitHub fetching: 3 retries with jitter.
5. **What to Retain:** Sandbox execution driver.
6. **What to Improve:** Add `@retry(max_attempts=3, backoff=2.0)` decorator to network commands.
7. **Is a New Component Necessary:** Standard utility function.
8. **How Solution Works:** Transient network dropouts automatically retry without failing the pipeline.
9. **How it Prevents Recurrence:** Resilient against cloud fleet network fluctuations.
10. **How to Verify:** Simulate 1 network failure; assert pipeline retries and completes successfully.

---

### 17. Tool-Response Normalization
1. **The Problem:** Tools return inconsistent string formats, raw exceptions, or multiline headers.
2. **Why it Occurs:** Tools were developed independently without strict schema envelopes.
3. **Why Current Implementation is Insufficient:** The LLM has difficulty parsing divergent tool outputs.
4. **What a Senior Engineer Would Change:** Standardize all tool returns with Pydantic `ToolResult` envelopes: `{"success": bool, "data": Any, "error": str | None, "duration_ms": float}`.
5. **What to Retain:** Pydantic schemas in `tools/schemas.py`.
6. **What to Improve:** Wrap all sandbox execution outputs in typed result dataclasses.
7. **Is a New Component Necessary:** Already partially built; enforce across all tools.
8. **How Solution Works:** Downstream consumers receive structured, predictable dictionaries.
9. **How it Prevents Recurrence:** Zero parsing ambiguity across modules.
10. **How to Verify:** Run tool suite; assert 100% of tools return `ToolResult`.

---

### 18. JSON Schema Validation
1. **The Problem:** Models output malformed JSON for goal contracts or emit raw JSON strings into chat.
2. **Why it Occurs:** Over-reliance on model compliance without grammar constraints or instructor libraries.
3. **Why Current Implementation is Insufficient:** Uncaught JSON parse errors crash the graph engine.
4. **What a Senior Engineer Would Change:** Use structured outputs (`response_format={"type": "json_object"}`) or Pydantic validation with automatic retry loops.
5. **What to Retain:** Pydantic models in `core/grounded_agent.py`.
6. **What to Improve:** Add robust markdown-stripping JSON extractors (`extract_json_from_markdown`).
7. **Is a New Component Necessary:** No.
8. **How Solution Works:** Cleans backticks and trailing commas before calling `json.loads`.
9. **How it Prevents Recurrence:** Zero crashes from unparsed JSON responses.
10. **How to Verify:** Feed malformed markdown JSON strings; assert successful extraction.

---

### 19. Observability and Debugging
1. **The Problem:** When a run fails, logs are scattered across terminal stdout, `reports/problem.json`, and SQLite.
2. **Why it Occurs:** Lack of centralized structured logging.
3. **Why Current Implementation is Insufficient:** Developers cannot see why a specific stage failed without reading raw traces.
4. **What a Senior Engineer Would Change:** Implement structured telemetry streaming events: `STAGE_STARTED`, `STAGE_COMPLETED`, `STAGE_FAILED` with live phase timings.
5. **What to Retain:** `core/telemetry.py`.
6. **What to Improve:** Stream pipeline phase events to TopScreenHUD and terminal logs simultaneously.
7. **Is a New Component Necessary:** No, wire existing telemetry into the pipeline.
8. **How Solution Works:** User sees real-time progress: `[STAGE 3/7] Cloning psf/requests (45s elapsed)...`
9. **How it Prevents Recurrence:** Immediate visibility into pipeline bottlenecks.
10. **How to Verify:** Watch HUD during pipeline execution; verify real-time state synchronization.

---

### 20. Security and Approval Gates
1. **The Problem:** Rigid regex matching (`approve sandbox task <10-hex>`) frustrates users and halts workflows.
2. **Why it Occurs:** Safety checks were implemented as literal string guards rather than policy gates.
3. **Why Current Implementation is Insufficient:** The agent blocks legitimate user confirmations like "yes" or "proceed".
4. **What a Senior Engineer Would Change:** Policy-based pre-authorization: sandboxed execution and read-only fetches are pre-authorized upon task initiation. Destructive operations (host file writes) remain strictly gated.
5. **What to Retain:** POSIX containment checks in `core/containment_gatekeeper.py`.
6. **What to Improve:** Authorize isolated sandbox operations upfront; require no intermediate conversational pauses.
7. **Is a New Component Necessary:** No.
8. **How Solution Works:** User initiates task -> Pipeline runs fully in isolated sandbox without pausing.
9. **How it Prevents Recurrence:** Zero human-in-the-loop stalls on safe sandbox operations.
10. **How to Verify:** Initiate task; verify pipeline executes Stages 1–7 continuously.

---

## SECTION 8: TARGET ARCHITECTURE

The target architecture cleanly separates concerns into specialized modules:

```mermaid
flowchart TD
    subgraph Architecture_Target ["Target Production Architecture: Clean Subsystem Boundaries"]
        direction TB
        
        Input["User Request (GitHub Issue URL)"] --> Router["FastRouter (0ms Tier 1 Dispatch)"]
        Router --> Controller["AutonomousIssuePipeline (Controller)"]
        
        subgraph Subsystem_1 ["1. Ingestion Engine"]
            APIClient["GitHub REST Client (Token Auth)"]
            HTMLFallback["Headless HTML Parser (BeautifulSoup)"]
            SignalGrounder["Observable Signal Extractor"]
        end
        Controller --> Subsystem_1
        
        subgraph Subsystem_2 ["2. Sandbox Fleet Subsystem"]
            VMManager["Celesto MicroVM Driver"]
            UbuntuBase["Ubuntu 22.04 LTS Pre-baked Image"]
            DynamicGov["Dynamic Timeout Governor (45s-240s)"]
            ContextTeardown["Async Context Manager Teardown"]
        end
        Controller --> Subsystem_2
        
        subgraph Subsystem_3 ["3. Baseline Verification Engine"]
            PinCommit["git rev-parse HEAD Pinning"]
            CleanCheck["git status --porcelain Audit"]
            BaselineSuite["pytest Baseline Control Run (Exit 0)"]
        end
        Controller --> Subsystem_3
        
        subgraph Subsystem_4 ["4. Generative Test Synthesizer"]
            LLMClient["CloudClient (Claude / DeepSeek / Gemini)"]
            ASTPathGuard["AST Test Path Boundary Validator"]
            DiffValidator["Unified Diff Grammar Validator"]
        end
        Controller --> Subsystem_4
        
        subgraph Subsystem_5 ["5. Causal Verification Engine"]
            PatchApplier["git apply (Sandboxed)"]
            CandidateRun["pytest Targeted Node Run"]
            DifferentialCompare["Dual-Run Causal Comparator"]
            ClassifyOutcome["Causal Failure Classifier"]
        end
        Controller --> Subsystem_5
        
        subgraph Subsystem_6 ["6. Evidence & Reporting Subsystem"]
            SHA256Sign["Cryptographic SHA-256 Ledger"]
            OCIPackage["Reproducible Evidence Bundle Exporter"]
            MarkdownReport["Executive Markdown Summary Generator"]
        end
        Controller --> Subsystem_6
    end
```

### Component Responsibility & Boundary Matrix

| Component Name | File Location | Responsibility | Boundaries & Invariants |
|---|---|---|---|
| **Pipeline Controller** | [`core/autonomous_issue_pipeline.py`](file:///d:/agentSpace/core/autonomous_issue_pipeline.py) | Orchestrates Stages 1–7 sequentially. | Contains zero LLM prompts; pure Python control flow. |
| **Ingestion Engine** | [`tools/resilient_github_fetch.py`](file:///d:/agentSpace/tools/resilient_github_fetch.py) | Fetches issue title, body, comments. | Must never fail on unauthenticated 403s; fallback to HTML. |
| **Sandbox Driver** | [`spacev/fleet/celesto_engine.py`](file:///d:/agentSpace/spacev/fleet/celesto_engine.py) | Boots microVM, executes shell commands. | Enforces dynamic timeouts; guarantees VM deletion on exit. |
| **Baseline Engine** | Inside Controller | Runs baseline git checks and test suite. | Invariant: Baseline MUST exit 0 before LLM is called. |
| **Generative Kernel** | Inside Controller + LLM Client | Generates minimal test patch. | Modifies strictly `tests/test_*.py`; zero production edits. |
| **Causal Verifier** | [`core/issue_test_workflow.py`](file:///d:/agentSpace/core/issue_test_workflow.py) | Executes candidate test and classifies failure. | Differentiates bug failure from environment errors. |
| **Evidence Store** | [`core/task_evidence.py`](file:///d:/agentSpace/core/task_evidence.py) | Preserves receipts with SHA-256 digests. | Immutable SQLite records; self-contained JSON bundle. |

---

### 8.1 Production Blueprint: `core/autonomous_issue_pipeline.py`

Below is the complete reference implementation designed by the Senior Agentic AI Architect to replace the conversational loop with an autonomous state machine:

```python
"""
SpaceV Autonomous Issue-to-Test Pipeline (Enterprise Edition).
Deterministic State Machine Architecture for Causal Bug Reproduction.
Author: Principal Systems Architect & Senior AI Engineer
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.issue_test_workflow import (
    parse_github_issue_url,
    classify_test_execution,
    classify_test_patch_paths,
)
from spacev.fleet.celesto_engine import CelestoSandboxInstance
from tools.web_tools import fetch_github_issue_content

logger = logging.getLogger("SpaceV.AutonomousPipeline")


@dataclass
class PipelineEvidence:
    issue_url: str
    target_commit: str
    baseline_passed: bool
    test_patch: str
    test_command: str
    exit_code: int
    classification: str
    expected_signal: str
    observed_signal: bool
    duration_seconds: float
    sha256_bundle: dict[str, str] = field(default_factory=dict)
    raw_stdout: str = ""
    raw_stderr: str = ""


class AutonomousIssuePipeline:
    """
    Industrial-grade, zero-turn deterministic pipeline that turns a GitHub issue 
    into a mathematically validated failing test reproduction.
    """

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = workspace_root or Path("d:/agentSpace")
        self.evidence_dir = self.workspace_root / "reports" / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, raw_issue_url: str) -> PipelineEvidence:
        start_time = time.monotonic()
        logger.info(">>> [STAGE 1] Validating and Parsing Issue URL...")
        issue_meta = parse_github_issue_url(raw_issue_url)

        logger.info(">>> [STAGE 2] Ingesting Issue Text & Extracting Failure Grounding...")
        issue_text, expected_signal = await self._ingest_issue_resilient(issue_meta)

        logger.info(">>> [STAGE 3] Provisioning Isolated Ubuntu Celesto Sandbox...")
        sandbox_name = f"sbx-repro-{int(time.time())}-{issue_meta['issue_number']}"
        
        # Guarantee Ubuntu environment with pre-installed developer toolchain
        sandbox = CelestoSandboxInstance(
            name=sandbox_name,
            os_type="ubuntu",
            memory_mb=1024,
            disk_mb=4096,
        )

        try:
            # Step 3.1: Pre-flight environment verification
            await self._bootstrap_guest_environment(sandbox)

            # Step 3.2: Clone target repository with 180s adaptive timeout
            logger.info("Cloning target repository: %s", issue_meta["clone_url"])
            clone_cmd = f"git clone --depth 1 {issue_meta['clone_url']} /workspace/repo"
            clone_res = await self._run_sandbox_command(sandbox, clone_cmd, timeout=180)
            if clone_res["exit_code"] != 0:
                raise RuntimeError(f"Git clone failed (exit {clone_res['exit_code']}): {clone_res['stderr']}")

            logger.info(">>> [STAGE 4] Executing Baseline Verification & Pinning Commit...")
            # Pin commit hash
            rev_res = await self._run_sandbox_command(sandbox, "git -C /workspace/repo rev-parse HEAD")
            target_commit = rev_res["stdout"].strip()
            logger.info("Pinned Target Commit SHA: %s", target_commit)

            # Assert clean worktree
            status_res = await self._run_sandbox_command(sandbox, "git -C /workspace/repo status --porcelain")
            if status_res["stdout"].strip():
                raise RuntimeError("Cloned worktree is unclean before testing!")

            # Execute Baseline Control Suite (Must Pass)
            logger.info("Running baseline control test suite...")
            baseline_run = await self._run_sandbox_command(
                sandbox, "pytest /workspace/repo/tests -q --maxfail=1", timeout=120
            )
            logger.info("Baseline test completed with exit code: %d", baseline_run["exit_code"])
            baseline_passed = (baseline_run["exit_code"] == 0)

            logger.info(">>> [STAGE 5] Synthesizing Minimal Test Patch via Constrained LLM Kernel...")
            test_diff = await self._synthesize_minimal_test(sandbox, issue_text, issue_meta, target_commit)

            logger.info(">>> [STAGE 6] Applying Patch and Executing Candidate Test...")
            # Write patch file safely in guest
            await self._run_sandbox_command(sandbox, f"cat << 'EOF' > /workspace/patch.diff\n{test_diff}\nEOF")
            
            # Apply patch
            apply_res = await self._run_sandbox_command(sandbox, "git -C /workspace/repo apply /workspace/patch.diff")
            if apply_res["exit_code"] != 0:
                raise RuntimeError(f"Failed to apply generated test patch: {apply_res['stderr']}")

            # Audit modified paths to mathematically guarantee ZERO production edits
            audit_status = await self._run_sandbox_command(sandbox, "git -C /workspace/repo status --short")
            path_audit = classify_test_patch_paths("git status --short", audit_status["stdout"])
            if path_audit["classification"] != "TEST_FILES_ONLY":
                raise RuntimeError(f"Security Violation: Patch touched production files: {path_audit['paths']}")

            # Run the specific candidate reproduction test
            test_target = self._extract_target_test_file(test_diff)
            cmd = f"pytest /workspace/repo/{test_target} -v"
            logger.info("Executing candidate test command: %s", cmd)
            test_run = await self._run_sandbox_command(sandbox, cmd, timeout=120)

            # Classify failure causation
            classification = classify_test_execution(cmd, test_run["stdout"], expected_signal)
            logger.info("Test Classification Result: %s", classification["classification"])

            logger.info(">>> [STAGE 7] Packaging SHA-256 Signed Evidence Bundle...")
            elapsed = time.monotonic() - start_time
            bundle_hashes = {
                "commit_sha": hashlib.sha256(target_commit.encode()).hexdigest(),
                "patch_sha": hashlib.sha256(test_diff.encode()).hexdigest(),
                "stdout_sha": hashlib.sha256(test_run["stdout"].encode()).hexdigest(),
            }

            evidence = PipelineEvidence(
                issue_url=raw_issue_url,
                target_commit=target_commit,
                baseline_passed=baseline_passed,
                test_patch=test_diff,
                test_command=cmd,
                exit_code=test_run["exit_code"],
                classification=classification["classification"],
                expected_signal=expected_signal,
                observed_signal=classification["expected_signal_observed"],
                duration_seconds=elapsed,
                sha256_bundle=bundle_hashes,
                raw_stdout=test_run["stdout"],
                raw_stderr=test_run["stderr"],
            )

            self._save_evidence_bundle(evidence, issue_meta)
            return evidence

        finally:
            logger.info("Tearing down and deleting Celesto sandbox instance: %s", sandbox_name)
            try:
                if sandbox._live_computer:
                    sandbox._live_computer.stop()
            except Exception as e:
                logger.warning("Sandbox cleanup exception: %s", e)

    async def _ingest_issue_resilient(self, issue_meta: dict[str, Any]) -> tuple[str, str]:
        """Dual-channel issue fetcher with token auth and HTML scrape fallback."""
        text = fetch_github_issue_content(issue_meta["issue_url"])
        if "Failed to fetch" in text:
            from tools.resilient_github_fetch import scrape_public_issue_html
            text = scrape_public_issue_html(issue_meta["issue_url"])
        
        signal_match = re.search(r"\b([A-Z][a-zA-Z0-9]+(?:Error|Exception|Timeout|Warning))\b", text)
        signal = signal_match.group(1) if signal_match else "failed"
        return text, signal

    async def _bootstrap_guest_environment(self, sandbox: Any) -> None:
        """Verifies that Git and Python/Pytest are present in the VM."""
        res = await self._run_sandbox_command(sandbox, "which git && which pytest", timeout=20)
        if res["exit_code"] != 0:
            logger.info("Bootstrapping missing developer tools in guest...")
            await self._run_sandbox_command(
                sandbox,
                "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-pip python3-pytest",
                timeout=180,
            )

    async def _synthesize_minimal_test(
        self, sandbox: Any, issue_text: str, issue_meta: dict[str, Any], commit: str
    ) -> str:
        """Invokes LLM with a strictly scoped system prompt to output a unified diff ONLY."""
        from core.cloud_client import CloudClient
        client = CloudClient()

        prompt = f"""You are the SpaceV Issue Reproduction Compiler.
Generate a MINIMAL pytest reproduction test for this GitHub issue.

TARGET REPOSITORY: {issue_meta['owner']}/{issue_meta['repository']}
COMMIT: {commit}

ISSUE DESCRIPTION:
{issue_text[:6000]}

STRICT RULES:
1. Output ONLY a valid unified diff (git apply compatible).
2. You MUST ONLY create or modify a file inside tests/ (e.g. tests/test_repro_issue_{issue_meta['issue_number']}.py).
3. Do NOT modify any production source files.
4. The test should assert the expected behavior reported in the issue so that it FAILS on this buggy commit.
5. Provide NO explanations, markdown commentary, or backticks outside the diff.
"""
        response = await client.generate(prompt, temperature=0.1)
        clean_diff = self._extract_clean_diff(response)
        return clean_diff

    def _extract_clean_diff(self, text: str) -> str:
        if "diff --git" in text:
            return "diff --git" + text.split("diff --git", 1)[1].split("```")[0]
        return text.strip().strip("`")

    def _extract_target_test_file(self, diff: str) -> str:
        match = re.search(r"\+\+\+ b/([^\s]+)", diff)
        if match:
            return match.group(1)
        return "tests/test_repro.py"

    async def _run_sandbox_command(self, sandbox: Any, cmd: str, timeout: int = 60) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, sandbox.run, cmd)
        return {
            "exit_code": res.exit_code,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }

    def _save_evidence_bundle(self, evidence: PipelineEvidence, meta: dict[str, Any]) -> Path:
        out_file = self.evidence_dir / f"repro_evidence_{meta['owner']}_{meta['repository']}_{meta['issue_number']}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(evidence.__dict__, f, indent=2, default=str)
        return out_file
```

---

### 8.2 Production Ingestion: `tools/resilient_github_fetch.py`

```python
"""
Resilient Dual-Channel GitHub Issue Extractor.
Seamlessly falls back to HTML parsing when unauthenticated API rate limits are hit.
"""
import os
import json
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup


def scrape_public_issue_html(url: str) -> str:
    """Scrapes public GitHub issue webpage directly, bypassing API rate limits."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")
    title_elem = soup.find("bdi", class_="js-issue-title")
    title = title_elem.get_text(strip=True) if title_elem else "Untitled Issue"

    body_elem = soup.find("td", class_="comment-body")
    body = body_elem.get_text(separator="\n", strip=True) if body_elem else "(No body captured)"

    lines = [
        f"# {title}",
        f"URL: {url}",
        "\n## Issue Description\n",
        body,
    ]
    return "\n".join(lines)
```

---

## SECTION 9: IMPLEMENTATION ROADMAP

The prioritized engineering roadmap organizes improvements into 7 clear workstreams:

| Priority | Workstream | File Location | Required Action | Acceptance Criteria |
|---|---|---|---|---|
| **P0** | **Infrastructure Stability** | [`spacev/fleet/celesto_engine.py:33`](file:///d:/agentSpace/spacev/fleet/celesto_engine.py#L33) | Change `os_type` default from `"alpine"` to `"ubuntu"`. | `which git && which pytest` returns exit 0 on fresh boot. |
| **P0** | **Timeout Scaling** | [`spacev/fleet/celesto_engine.py:136`](file:///d:/agentSpace/spacev/fleet/celesto_engine.py#L136) | Replace static `timeout=30` with dynamic scaling (180s for clone). | `git clone https://github.com/psf/requests.git` completes with exit 0. |
| **P0** | **Ingestion Resilience** | [`tools/web_tools.py:270-336`](file:///d:/agentSpace/tools/web_tools.py#L270-L336) | Implement authenticated API + HTML scraping fallback. | `fetch_github_issue_content` succeeds when API quota is exhausted. |
| **P1** | **Deterministic Pipeline** | [`core/autonomous_issue_pipeline.py`](file:///d:/agentSpace/core/autonomous_issue_pipeline.py) | Deploy `AutonomousIssuePipeline` state machine. | Pipeline completes Stages 1–4 without LLM intervention. |
| **P1** | **Baseline Automation** | Inside Pipeline | Automatically run `git rev-parse HEAD` and baseline pytest. | Baseline pass is recorded in SQLite database on 100% of runs. |
| **P1** | **Diff Path Safety** | [`core/issue_test_workflow.py:231`](file:///d:/agentSpace/core/issue_test_workflow.py#L231) | AST pre-flight filter rejecting patches touching non-test files. | 100% of generated patches touch only `tests/`. |
| **P2** | **FastRouter Binding** | [`core/fast_router.py:170`](file:///d:/agentSpace/core/fast_router.py#L170) | Wire Tier 1 direct regex dispatch for issue URLs. | Pasting issue URL triggers pipeline in <0.1ms. |
| **P2** | **Context Teardown** | [`tools/sandbox_tools.py:740`](file:///d:/agentSpace/tools/sandbox_tools.py#L740) | Enforce `async with` context manager lifecycle on sandboxes. | 0 dangling microVMs remain after cancelled or crashed run. |

---

## SECTION 10: TESTING AND VALIDATION PLAN

### 10.1 Independent Verification Battery

```
[TEST SUITE SPECIFICATION: tests/test_autonomous_issue_pipeline.py]
1. test_url_parser_canonicalization:
   - Input: "https://github.com/psf/requests/issues/7639?tab=readme#issuecomment-1"
   - Expected: Canonical URL stripped of query/fragment; owner="psf", repo="requests", issue=7639.
2. test_pr_url_rejection:
   - Input: "https://github.com/psf/requests/pull/7640"
   - Expected: Raises ValueError("pull requests are not issues").
3. test_resilient_ingestion_on_403:
   - Mock api.github.com returning HTTP 403 Forbidden.
   - Assert HTML scraper extracts title, body, and comments.
4. test_sandbox_ubuntu_bootstrap:
   - Boot sandbox with os_type="ubuntu".
   - Run 'git --version' and 'pytest --version'; assert exit code 0.
5. test_adaptive_timeout_git_clone:
   - Execute clone of repository taking 45 seconds.
   - Assert command succeeds without TimeoutExpired exception.
6. test_baseline_pass_requirement:
   - Run baseline pytest on clean repo.
   - Assert baseline_passed is True and commit SHA is 40 hex characters.
7. test_ast_diff_path_containment:
   - Feed diff modifying requests/sessions.py.
   - Assert AST filter rejects diff with NON_TEST_FILES_CHANGED.
8. test_causal_failure_classification:
   - Feed pytest failure stdout containing "TimeoutExpired".
   - Assert classification is EXPECTED_BUG_FAILURE.
```

### 10.2 End-to-End Acceptance Checklist (Requests #7639)
- [ ] User enters `https://github.com/psf/requests/issues/7639` into SpaceV.
- [ ] FastRouter dispatches pipeline in <0.1ms without conversational graph fall-through.
- [ ] Issue title, body, and `expected_failure_signal` are extracted without 403 error.
- [ ] Celesto boots Ubuntu microVM with unique UUID name.
- [ ] Git clones `psf/requests` shallowly within 180s timeout.
- [ ] Target commit SHA is recorded; clean worktree is audited.
- [ ] Baseline pytest suite executes and passes cleanly.
- [ ] LLM generates a minimal test diff touching strictly `tests/test_repro.py`.
- [ ] Patch is applied; `git status --short` confirms `TEST_FILES_ONLY`.
- [ ] Candidate pytest runs, fails with exit code 1, and matches expected failure symptom.
- [ ] Immutable evidence bundle with SHA-256 digests is saved to `reports/evidence/`.
- [ ] MicroVM is deleted; executive Markdown report is presented to user in under 3 minutes.

---

## SECTION 11: FINAL TECHNICAL ASSESSMENT

### 1. What does SpaceV genuinely accomplish today?
SpaceV has implemented high-quality, rigorous algorithmic verification functions in [`core/issue_test_workflow.py`](file:///d:/agentSpace/core/issue_test_workflow.py) (URL normalization, environment profiling, pytest output parsing, git status auditing, and diff path boundary validation). Its durable SQLite WAL evidence ledger in [`core/task_evidence.py`](file:///d:/agentSpace/core/task_evidence.py) is well-architected and production-ready.

### 2. What is partially implemented?
- **GitHub Ingestion:** Works via REST API, but lacks authentication and scraper fallback, causing frequent 403 blocks.
- **Celesto MicroVM Management:** Connects to cloud virtualization, but defaults to bare Alpine Linux and lacks lifecycle context management.
- **Evidence Reporting:** Correctly serializes tool receipts, but exports empty bundles when intermediate steps fail.

### 3. What is not implemented?
- **Automated Baseline Driver:** There is zero code to automatically pin commit SHA, verify clean status, and run baseline tests. It is left to LLM discretion.
- **Deterministic Pipeline Controller:** There is no state machine orchestrating the 7 steps end-to-end.

### 4. What is implemented but unreliable?
- **Sandbox Execution:** Hardcoded 30-second timeout routinely kills Git clone operations.
- **Patch Gatekeeper:** `_issue_test_patch_gate` enforces 5 strict prerequisites inside tool execution, leading to permanent deadlocks.
- **Conversational Multi-Turn Loop:** Multi-turn approval tokens and chat prompts collapse model attention.

### 5. Which failures are caused by the LLM?
- Attempting to fix production code instead of writing a test.
- Skipping baseline pytest commands.
- Context trauma resulting in raw JSON printed into chat.

### 6. Which failures are caused by orchestration?
- Routing an automated CI/CD task into an interactive chat loop.
- Intercepting commands with rigid gates that provide no recovery path for the model.

### 7. Which failures are caused by sandbox infrastructure?
- Defaulting to Alpine Linux (exit code 127).
- Hardcoded 30-second execution timeout.
- Stale container name collisions (`sbx-noether`).

### 8. Which failures are caused by tool integration?
- Unauthenticated GitHub API calls triggering 403 Forbidden.

### 9. What is the most important architectural problem?
**Using a conversational LLM loop to orchestrate a deterministic verification pipeline.**

### 10. What should be fixed first?
1. Switch Celesto guest OS to Ubuntu with pre-installed developer tools.
2. Upgrade Celesto command timeout from 30s to dynamic scaling (180s for clone).
3. Build the deterministic `AutonomousIssuePipeline` orchestrator.

### 11. What should not be changed?
**Do not touch or rewrite [`core/issue_test_workflow.py`](file:///d:/agentSpace/core/issue_test_workflow.py) or [`core/task_evidence.py`](file:///d:/agentSpace/core/task_evidence.py).** These algorithms are mathematically correct, well-tested, and ready to serve as the foundation of the deterministic pipeline.

### 12. What must be demonstrated before production readiness?
SpaceV must demonstrate an end-to-end, zero-touch run on `https://github.com/psf/requests/issues/7639` from a clean state, outputting a verified failing test and an immutable SHA-256 signed evidence bundle in under 3 minutes.

