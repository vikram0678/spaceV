# SpaceV Issue → Failing Test: Comprehensive Workflow Audit

> **Purpose:** Compare the seven-step target flow with the current SpaceV source and the execution evidence provided in this conversation. Explain verified gaps, observed failures, and a practical engineering remedy.
>
> **Scope:** Read-only source investigation plus analysis of user-provided logs. This Markdown file is the only artifact created for the request. No application source, configuration, or environment file was changed; no tests or sandbox commands were run.
>
> **Prepared:** 2026-11-08 | **Workspace:** D:/agentSpace

---

## How to read this audit

- **Target** means the workflow you want SpaceV to deliver.
- **Current source** means behavior visible in the checked-in implementation at inspection time.
- **Run evidence** means a tool result or correction shown in this conversation.
- **Source capability is not execution proof.** A method existing does not prove it ran.
- **Attempt is not success.** A tool call is not a successful operation unless its receipt says so.
- **A failing command is not a reproduced bug.** Setup, network, infrastructure, and issue symptoms are classified separately.
- Status labels: ✅ verified execution, 🔎 source capability, 🟡 partial/attempted, ❌ observed failure, ◻ not demonstrated.
- Source references use one-based line numbers and can move after edits.
- The attached brief’s issue text was a placeholder. This report does not invent the Requests #7639 title/body or the expected symptom.
- Different sandbox session IDs represent different attempts. The report never merges them into one imagined successful run.

## Executive summary

SpaceV contains real building blocks for Issue → Failing Test work: public GitHub issue parsing/fetching, an issue-specific prompt, a reusable approval-gated Celesto session, a separate source-only clone tool, test failure classification, a same-session test gate, and bounded evidence storage. These are spread over multiple files and are only partially connected into the seven-stage product workflow.

The logs do **not** establish a completed end-to-end reproduction. Across separate sessions, Git installation succeeded in one Alpine VM; a shallow Requests clone and capture of the test_stream_timeout body were reported in another attempt; the user corrected the summary to say source inspection was incomplete, no test diff was produced in that attempt, and no test was run. Other sessions failed for distinct reasons: Git absent, clone timed out, session expired, or a Celesto name collision prevented even git --version from reaching the guest. None is evidence that Requests issue #7639 was reproduced.

**Primary diagnosis:** SpaceV needs a durable, deterministic workflow state machine that advances only on validated receipts and preserves those receipts across approval turns and context compression. Another persona or a longer prompt will not fix missing session state, command timeouts, incomplete inspection, or an unsupported success claim.

**Confirmed code protections:** placeholder rejection; exact approval handling; guest-only command routing for active approved sessions; terminal stop and cleanup after failed guest commands; and a classifier that requires a target-test symptom before labeling EXPECTED_BUG_FAILURE.

**Not verified:** external tool exposure in every model call; actual issue #7639 contents; complete source analysis for that issue; a proposed diff grounded in the real source; guest dependencies; clean baseline; candidate test execution; final evidence bundle for one successful complete run.

## Contents

1. Scope and evidence rules
2. Target seven-step workflow
3. Executive side-by-side comparison
4. Detailed side-by-side stage audit
5. Current source inventory
6. Error and failure investigation
7. Actual execution and call graph
8. Target architecture
9. Senior-engineering solution
10. Prioritized implementation roadmap
11. Validation plan and acceptance checklist
12. Final assessment
13. Evidence ledger and limits

## 1. Scope and evidence rules

### 1.1 Source files inspected

- core/graph_engine.py — graph wiring, goal parsing, routing, tool execution, gates, cleanup, synthesis.
- core/grounded_agent.py — GroundedGoal, goal normalization, LLM interpretation/fallback, domain filters.
- core/swarm_orchestrator.py — task role selection and dispatch.
- core/agent_configs.py — issue analyst instructions and tool allowlist.
- core/issue_test_workflow.py — GitHub issue URL validation and test/status classifiers.
- core/task_input.py — unresolved template marker detection.
- core/task_evidence.py — bounded/redacted receipts, retrieval, and bundle export.
- tools/repo_tools.py — approved source-only host clone.
- tools/sandbox_tools.py — Celesto readiness, session lifecycle, command execution, simulation helpers.
- spacev/fleet/celesto_engine.py — real Celesto computer initialization, run, snapshot/rollback, cleanup.
- tools/registry.py — names, aliases, schemas, environment tags, dynamic tool scoping.
- tools/web_tools.py — GitHub issue API fetch path through read_web_page.
- ARCHITECTURE.md and requirements.txt — project-level architecture and dependency declaration.

### 1.2 Evidence categories

| Kind | Definition | Example |
|---|---|---|
| Source fact | Current code directly shows it | SandboxSessionManager.run delegates to instance.run. |
| Runtime receipt | Log output shows a result | Guest command returned exit 127 and “git: not found.” |
| User correction | User corrected an earlier report | The source inspection and diff were not completed. |
| Inference | Plausible engineering explanation, not proven | Repeated model turns increase context-loss risk. |
| Recommendation | A proposed change | Persist explicit workflow state and phase receipts. |

### 1.3 Limits

- The issue title/body are not present in the attached brief; it contains “[Paste the actual issue text here]”.
- This audit does not recover omitted issue text from memory or browse the issue.
- Logs reference multiple different VM/session identifiers and timestamps; these are separate runs.
- get_sandbox_status reports project registration/config readiness, not proof that an external harness delivered a tool in a specific request.
- No tests, live API calls, Celesto actions, or benchmarks were run for this audit.
- The audit distinguishes code that exists from code proven to have executed in a particular run.

## 2. Target seven-step workflow

1. **Accept a GitHub Issue URL.** Human provides a GitHub issue URL.
2. **Read and understand the issue.** Capture title, description, expected/actual behavior, and reproduction information.
3. **Clone in an isolated sandbox.** Provision or reuse a guest VM and clone the repository there.
4. **Inspect source and tests.** Identify relevant implementation, existing tests, dependencies, and execution requirements.
5. **Generate a minimal failing test.** Propose a focused test and do not fix production code.
6. **Execute and verify.** Establish a valid baseline, run only the approved candidate test, and classify the exact symptom.
7. **Deliver evidence.** Report issue, commit, source/test locations, diff, exact command/output, verdict, changed paths, and cleanup.

### Completion criteria

- Issue identity and content are known, or issue text is explicitly provided.
- Repository URL is derived from that validated issue identity.
- Clone occurs only in the approved isolated environment.
- Commit and clean initial git status are captured before edits.
- Source/test inspection is from that same commit.
- Diff is shown and approved before file edits.
- Baseline is valid and passes before candidate test, when authorized.
- Candidate test is separately approved and only that test is executed.
- EXPECTED_BUG_FAILURE requires the target test plus the explicit expected symptom.
- Evidence and cleanup are captured before any “complete” claim.

## 3. Executive side-by-side comparison

| Intended workflow | Current SpaceV behavior | Current files/methods | Status | Evidence / gap |
|---|---|---|---|---|
| 1. Accept issue URL | Parses public GitHub issue URL before model interpretation when the prompt looks issue-related; role classifier also recognizes issue URLs/phrases. | graph_engine.py:430-489; issue_test_workflow.py:19-53; swarm_orchestrator.py:84-105 | 🔎 / 🟡 | URL parsing is real. No single persisted issue-task object spans every stage. |
| 2. Read issue | read_web_page routes GitHub issue URLs to fetch_github_issue_content, which uses GitHub API and bounds content. | web_tools.py:255-335, 350-400; registry.py:227 | 🔎 / ◻ | Capability exists. In this pilot the issue text was missing/placeholder in some requests; the actual issue text is not available in this report’s evidence. |
| 3. Isolated clone | Two distinct paths exist: clone_public_repository is an approved host-side source-only checkout; Celesto session commands run in an approved guest. | repo_tools.py:20-151; sandbox_tools.py:580-702 | 🟡 | Historical logs show one guest clone succeeded, another timed out. Source clone tool and guest clone must not be confused. |
| 4. Inspect source/tests | Model can issue guest shell commands through generic command tool; no dedicated repository-inspection completeness contract is evident. | graph_engine.py:1202-1305; sandbox_tools.py:675-702 | 🟡 | User correction confirms test body was captured but source inspection remained incomplete. |
| 5. Propose minimal test | Issue analyst prompt instructs minimal test-only proposal and no production fix; model generates content. | agent_configs.py:120-143; graph_engine.py:855-968 | 🟡 | The prompt exists, but the corrected log says no grounded diff was produced in the incomplete run. |
| 6. Execute/verify | Same-session gate requires commit, clean initial status, passing baseline, approved test-only patch, unchanged commit; classifier labels only specific target symptom. | graph_engine.py:1446-1540; issue_test_workflow.py:153-205, 231-298 | 🔎 / ◻ | Gate and classifier exist; no candidate test result was captured. |
| 7. Report evidence | Tool receipts and turn summaries are bounded/redacted and can be exported; response synthesis remains model-led except selected deterministic status cases. | task_evidence.py:57-360; graph_engine.py:1384-1444, 1902-2018, 2193-2221 | 🟡 | Conversation summaries previously overstated completion; evidence must be authoritative and complete. |

### Key interpretation

The closest accurate description is **“a model-led graph with issue-task safeguards and a reusable sandbox control plane,”** not yet **“a deterministic Issue → Failing Test product workflow.”** The source already contains meaningful safety improvements; the remaining work is to make every stage explicit, evidence-backed, resumable, and impossible to skip silently.

## 4. Detailed side-by-side stage audit

### Stage 1 — Accept a GitHub Issue URL

**Overall status:** PARTIAL — parser and role recognition exist; successful task initialization depends on valid concrete input.

**Current implementation map:** graph_engine.py:430-489; issue_test_workflow.py:19-53; swarm_orchestrator.py:77-105; task_input.py:13-17.

#### 1.1 URL acceptance
- **Target:** Human supplies a public GitHub issue link.
- **Actual attempt/behavior:** Issue-like prompts are scanned for GitHub URLs before goal interpretation.
- **Source and evidence:** parse_github_issue_url validates HTTPS, github.com, owner/repo/issues/number and rejects PR forms.
- **Gap/status:** Record parsed canonical URL, repo URL, clone URL, issue number and immutable task ID.
- **Senior-engineer action:** Replace unstructured prompt parsing with an immutable `IssueTaskContext` dataclass in `core/fast_router.py` and `core/task_input.py` that validates the URL via `re.compile(r"^https://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/issues/(?P<number>\d+)$")`, generates an immutable `workflow_id = f"issue-{owner}-{repo}-{number}-{uuid.uuid4().hex[:8]}"`, and persists normalized URLs (`canonical_url`, `clone_url`, `api_url`) into `TaskEvidenceStore` before agent dispatch.

#### 1.2 Placeholder handling
- **Target:** Only a concrete issue URL/text should start work.
- **Actual attempt/behavior:** unresolved_template_marker blocks common markers before model/tool routing and again before VM proposal.
- **Source and evidence:** task_input.py:5-16; graph_engine.py:446-471, 567-578; sandbox_tools.py:580-637.
- **Gap/status:** Retain this early deterministic guard; add tests for casing, punctuation, and less common template forms.
- **Senior-engineer action:** Harden `unresolved_template_marker()` in `core/task_input.py` with case-insensitive boundary regex matching (`r"(?i)\b(paste|insert|put|todo|tbd)\b.*(url|link|issue|text|description)"`) across all prompt variants, and enforce a fail-closed unit test suite in `tests/test_task_input.py` verifying rejection of brackets, angle brackets, and whitespace variations before any LLM inference or sandbox allocation.

#### 1.3 Role selection
- **Target:** Issue reproduction selects the specialist workflow regardless of phrasing.
- **Actual attempt/behavior:** classify_agent_role selects ISSUE_TEST for issue URL or a short fixed phrase list.
- **Source and evidence:** swarm_orchestrator.py:84-105.
- **Gap/status:** Phrase matching can miss paraphrases; make role a capability hint only and derive workflow type from validated task state.
- **Senior-engineer action:** Decouple workflow dispatch from brittle LLM role classification in `core/swarm_orchestrator.py`; bind validated `IssueTaskContext` presence directly to deterministic execution of `AutonomousIssuePipeline` in `core/fast_router.py`, treating `AgentRole.ISSUE_TEST` solely as an informational capability metadata tag.

#### 1.4 URL normalization
- **Target:** Repository identity must come from the issue link, never guessed.
- **Actual attempt/behavior:** Parser returns normalized issue_url/repository_url/clone_url and integer issue number.
- **Source and evidence:** issue_test_workflow.py:19-53; graph_engine.py:473-489.
- **Gap/status:** Validate route with positive/negative URL cases and keep normalized values in task state.
- **Senior-engineer action:** Implement a pure-function URL normalization validator in `core/issue_test_workflow.py` that strips trailing slashes, fragment hashes (`#issue-...`), and query parameters; converts SSH/Git protocols to standard HTTPS; and enforces unit test coverage across 20+ positive and negative GitHub URL edge cases.

#### 1.5 Malformed URL
- **Target:** Bad URLs must stop before tools.
- **Actual attempt/behavior:** Parser raises ValueError; graph returns a user-facing stop message.
- **Source and evidence:** graph_engine.py:477-489.
- **Gap/status:** Keep the fail-closed behavior and report exact field/reason without requesting unrelated status tools.
- **Senior-engineer action:** Ensure `parse_github_issue_url` raises a structured `InvalidIssueUrlError` containing the exact malformed component (domain, owner, repo, issue_number, or scheme), caught by `core/graph_engine.py` to immediately short-circuit to a terminal error response with actionable correction guidance without invoking conversational fallbacks or VM tools.

#### 1.6 Numeric entity typing
- **Target:** Structured goal entities use stable string values.
- **Actual attempt/behavior:** Parsed issue values are copied into goal.entities using str(value).
- **Source and evidence:** grounded_agent.py:16-31; graph_engine.py:640-641.
- **Gap/status:** This addresses number-vs-string schema errors when parsed_issue exists; verify issue_number is always string in goal entities.
- **Senior-engineer action:** Enforce strict Pydantic/dataclass schema typing in `core/grounded_agent.py` where `GroundedGoal.entities["issue_number"]` is validated as an integer-formatted string (`str(int(val))`), preventing JSON-schema deserialization mismatches across LangGraph state transitions and tool invocation payloads.

#### 1.7 Natural phrasing
- **Target:** User should not need internal tool function names.
- **Actual attempt/behavior:** Goal interpretation prompt says user can describe outcome naturally; role recognition still uses deterministic phrase/URL rules.
- **Source and evidence:** grounded_agent.py:69-82; swarm_orchestrator.py:84-105.
- **Gap/status:** Preserve natural language support; broaden intent via typed routing/LLM as advisory, never hardcode tool-name phrasing as the only path.
- **Senior-engineer action:** Implement semantic intent classification via few-shot embeddings or fast LLM structured extraction in `core/semantic_router_engine.py` that maps colloquial requests (e.g., "reproduce #7639", "write a test proving the bug reported here...") directly to `IssueTaskContext` without requiring the user to specify internal tool names or CLI flags.

#### 1.8 Task identity
- **Target:** Each issue attempt should be independently traceable.
- **Actual attempt/behavior:** No standalone issue-run ID is visible in GroundedGoal; issue values are ordinary entities.
- **Source and evidence:** grounded_agent.py:16-31; task_evidence.py:111-145.
- **Gap/status:** Add immutable workflow_id and source identity fields to persisted task state, not only a prompt string.
- **Senior-engineer action:** Introduce a first-class `run_id: UUID` and `task_id: str` in `GroundedGoal` and `TaskState`, persisted in `core/durable_ledger.py` and `core/task_evidence.py`, ensuring all downstream logs, sandbox allocations, receipts, and git patches are immutably keyed to this single execution lifecycle.

#### 1.9 Issue URL absent
- **Target:** If no URL, ask for it or use explicitly supplied issue text.
- **Actual attempt/behavior:** The graph may interpret the prompt and call web tools; no dedicated deterministic “missing issue URL” stage is shown.
- **Source and evidence:** graph_engine.py:608-648; grounded_agent.py:56-135.
- **Gap/status:** Add explicit input validation: require one of URL or supplied issue text before opening a sandbox.
- **Senior-engineer action:** Insert an upfront deterministic precondition gate in `core/graph_engine.py` that verifies `(task.issue_url is not None or task.raw_issue_text is not None)` prior to graph execution; if neither is present, transition immediately to `INPUT_REQUIRED` state and solicit the missing URL or problem description without consuming LLM tokens.

#### 1.10 Acceptance proof
- **Target:** Stage passes only when a validated issue object exists.
- **Actual attempt/behavior:** URL parse is source-backed; historical execution excerpts show repeated placeholder/missing issue content.
- **Source and evidence:** Logs: 15:19:56 prompt contains placeholder; 16:20:35 issue fetch was forbidden and not performed.
- **Gap/status:** Report accepted issue identity and provenance. Never treat role selection as acceptance completion.
- **Senior-engineer action:** Emit a signed, immutable `Stage1AcceptanceReceipt` containing `sha256(canonical_url)`, `timestamp`, `workflow_id`, and `repo_coordinates` into `TaskEvidenceStore`; make this cryptographic receipt an explicit prerequisite in the state machine before permitting transition to Stage 2.

### Stage 2 — Read and understand the issue

**Overall status:** PARTIAL — a bounded GitHub API fetch path exists; issue-grounding evidence is not guaranteed by the graph.

**Current implementation map:** tools/web_tools.py:255-335, 350-434; tools/registry.py:227; grounded_agent.py:56-135; graph_engine.py:980-1177.

#### 2.1 Issue fetch route
- **Target:** Retrieve title, body, state, and useful discussion from public GitHub.
- **Actual attempt/behavior:** read_web_page recognizes GitHub issue/API URLs and routes them to fetch_github_issue_content.
- **Source and evidence:** web_tools.py:255-335, 350-400.
- **Gap/status:** Call only with approved web capability and preserve raw returned issue receipt in the evidence store.
- **Senior-engineer action:** Implement a dual-channel authenticated fetch pipeline in `tools/web_tools.py` that first queries `api.github.com/repos/{owner}/{repo}/issues/{number}` using `GITHUB_TOKEN` (or `GH_TOKEN`), automatically falling back to scraping public GitHub HTML via BeautifulSoup when unauthenticated rate limits (403 Forbidden) are encountered, and persisting the raw HTTP payload to `TaskEvidenceStore`.

#### 2.2 API URL safety
- **Target:** Only expected GitHub API resources should be fetched.
- **Actual attempt/behavior:** _github_issue_api_url maps github.com issue paths to api.github.com and issue API paths.
- **Source and evidence:** web_tools.py:255-270.
- **Gap/status:** Retain host/path checks; add tests for encoded paths, pull requests, query strings, redirects, and malformed authorities.
- **Senior-engineer action:** Enforce strict URL domain and path whitelisting in `_github_issue_api_url()` using `urllib.parse.urlsplit`, validating that `scheme == "https"`, `netloc == "api.github.com"`, and path matches regex `^/repos/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+/issues/\d+$`, rejecting any URL containing query strings, userinfo, port manipulation, or SSRF redirect vectors.

#### 2.3 Issue body capture
- **Target:** Body must be preserved for later reasoning.
- **Actual attempt/behavior:** fetch_github_issue_content formats title, URL, state, author, date and body; caps at 12000 characters.
- **Source and evidence:** web_tools.py:286-335.
- **Gap/status:** Store raw fetched body separately from LLM summary and mark truncation exactly.
- **Senior-engineer action:** Store the unmodified, raw issue Markdown body in `TaskEvidenceStore` under `raw_issue_receipt`, compute its SHA-256 hash, and pass a structured `IssuePayload(title, body, labels, author, truncated=bool)` to downstream stages, explicitly flagging truncation character offsets rather than silently dropping context.

#### 2.4 Comments
- **Target:** Comments may clarify expected behavior but should not be mandatory by default.
- **Actual attempt/behavior:** Function fetches up to 30 comments when comments_count > 0; comment fetch errors are appended, not fatal.
- **Source and evidence:** web_tools.py:317-329.
- **Gap/status:** Label issue body vs discussion as separate sources; do not let comments silently override the reporter’s stated behavior.
- **Senior-engineer action:** Structurally partition the issue representation into `original_post` (author's primary symptom/contract) and `discussion_comments` (maintainer/community commentary) with explicit author role tagging (`MEMBER`, `CONTRIBUTOR`, `NONE`), ensuring maintainer clarifications are weighted appropriately without overwriting the original bug reproduction steps.

#### 2.5 Network errors
- **Target:** DNS/HTTP failures must be classified as issue retrieval failure.
- **Actual attempt/behavior:** fetch_github_issue_content catches exceptions and returns a string beginning Failed.
- **Source and evidence:** web_tools.py:334-335.
- **Gap/status:** Convert failure text into a typed ToolResult error so the workflow cannot pass it to analysis as if it were issue content.
- **Senior-engineer action:** Refactor `fetch_github_issue_content` to return a typed `ToolResult(success=False, error_code="HTTP_FETCH_ERROR", details=...)` on network exceptions (DNS failure, timeout, 403, 404, 500) rather than a string literal, preventing the LLM from hallucinating an issue analysis from error messages.

#### 2.6 Missing/empty body
- **Target:** Empty issue data must not become fabricated context.
- **Actual attempt/behavior:** Empty body is rendered as “(No issue description.)”; goal interpreter falls back to raw prompt on model/JSON errors.
- **Source and evidence:** web_tools.py:313-315; grounded_agent.py:126-135.
- **Gap/status:** Treat absent body as missing evidence and stop or request user input, not as a valid issue summary.
- **Senior-engineer action:** Implement a schema validation guard in `core/graph_engine.py` that raises `InsufficientIssueContextError` if the issue title and body combined contain fewer than 20 characters of substantive text, immediately halting the pipeline to prompt the user for reproduction details rather than allowing the model to hallucinate expected behaviors.

#### 2.7 Expected vs actual
- **Target:** Agent should state expected and actual behavior, reproduction, and uncertainty.
- **Actual attempt/behavior:** ISSUE_TEST prompt explicitly requires these, and expected_failure_signal only when grounded.
- **Source and evidence:** agent_configs.py:123-132; grounded_agent.py:76-78.
- **Gap/status:** Require structured fields with evidence spans/citations into issue text before accepting interpretation.
- **Senior-engineer action:** Enforce structured JSON extraction using Pydantic (`class IssueSemantics(BaseModel): expected_behavior: str; actual_behavior: str; reproduction_steps: List[str]; expected_failure_signal: str; evidence_citations: List[str])`), rejecting any LLM response that fails schema validation or omits direct string quotations from the captured issue text.

#### 2.8 Issue correctness
- **Target:** The issue analyzed must match URL and repository.
- **Actual attempt/behavior:** Issue API formatter includes html_url and fetch route uses normalized path; no graph-level identity consistency gate is evident.
- **Source and evidence:** web_tools.py:306-315; issue_test_workflow.py:45-52.
- **Gap/status:** Compare returned html_url/number/repo with parsed issue identity. Stop on mismatch.
- **Senior-engineer action:** Implement an assertion in `core/graph_engine.py` verifying that `response_json["html_url"].lower() == context.canonical_url.lower()` and `response_json["number"] == context.issue_number`; abort immediately with `IssueIdentityMismatchError` if an API redirect or erroneous response returns data from an unintended repository or issue.

#### 2.9 Input from user
- **Target:** Provided issue text should be usable without web access.
- **Actual attempt/behavior:** Prompt includes conversation history and current prompt; durable evidence retrieval may add prior chat/tool text.
- **Source and evidence:** grounded_agent.py:85-90; graph_engine.py:610-639; task_evidence.py:168-287.
- **Gap/status:** Represent user-provided issue text as its own source, with explicit provenance and stable link to task ID.
- **Senior-engineer action:** Create a typed ingestion channel `UserSuppliedIssueRecord(text: str, source="USER_PROMPT", timestamp: float, task_id: str)` that bypasses external network fetching entirely when offline or when local issue descriptions are pasted, attaching verified user provenance to the evidence ledger.

#### 2.10 Actual run evidence
- **Target:** At least one issue body must be captured before source analysis.
- **Actual attempt/behavior:** Provided logs include missing context and an explicit issue fetch refusal; the body is absent from this report’s input.
- **Source and evidence:** Conversation log 16:20:35 says no web fetch tool permitted in that run; 15:19:56 uses placeholder.
- **Gap/status:** Stage is not verified for #7639. Do not summarize issue-specific behavior in this document.
- **Senior-engineer action:** Maintain strict audit integrity by categorizing issue #7639 as `UNVERIFIED_INGESTION` in the audit report; mandate that execution cannot proceed to Stage 3 without an active, verified HTTP receipt or verified user text recorded in the durable SQLite store.

#### 2.11 Acceptance proof
- **Target:** Stage passes only with issue content plus structured interpretation.
- **Actual attempt/behavior:** No deterministic issue-analysis result schema or source-span validator is visible.
- **Source and evidence:** agent_configs.py prompt; GroundedGoal has generic objective/steps/entities fields.
- **Gap/status:** Add an IssueRecord plus a validated IssueUnderstanding record; require links from claims to evidence.
- **Senior-engineer action:** Generate an immutable `Stage2AcceptanceReceipt` containing `raw_body_sha256`, validated `IssueSemantics`, and a boolean `grounding_verified=True`; gate Stage 3 entry strictly on the cryptographic presence of this record in `TaskEvidenceStore`.

### Stage 3 — Clone repository in an isolated sandbox

**Overall status:** PARTIAL — both source-only host clone and real Celesto guest sessions exist, with different trust semantics.

**Current implementation map:** tools/repo_tools.py:20-151; tools/sandbox_tools.py:407-446, 460-749; spacev/fleet/celesto_engine.py:29-149; registry.py:215-219, 1251-1313.

#### 3.1 Isolation selection
- **Target:** Repository content and commands belong in an isolated guest.
- **Actual attempt/behavior:** create_sandbox_session provisions a reusable VM; clone_public_repository clones on the SpaceV host outside project.
- **Source and evidence:** sandbox_tools.py:580-674; repo_tools.py:64-151.
- **Gap/status:** For the issue workflow, select only the guest session path; keep host clone tool unavailable in its execution plan.
- **Senior-engineer action:** Remove `clone_public_repository` from the permitted tool registry of the issue reproduction pipeline; enforce that all git operations, dependencies, and test executions run exclusively inside an isolated Celesto MicroVM / Docker sandbox container via `sandbox_tools.py`.

#### 3.2 Approval
- **Target:** User reviews exact task and approval binds to it.
- **Actual attempt/behavior:** Session create first stores a bounded task proposal; exact phrase approval loads the immutable task.
- **Source and evidence:** sandbox_tools.py:580-674; graph_engine.py:491-552.
- **Gap/status:** Keep exact approval; persist approval state outside volatile process memory if sessions must survive app restart.
- **Senior-engineer action:** Persist pending and granted sandbox approvals in `core/durable_ledger.py` using HMAC-signed approval tokens tied to `(workflow_id, repo_url, commit_sha, requested_tools)` so that session authorizations survive process restarts and cannot be hijacked or replayed by altered prompts.

#### 3.3 Session reuse
- **Target:** One VM should handle a whole bounded task.
- **Actual attempt/behavior:** Manager stores session by session_id; repeated commands reuse instance; one active session max.
- **Source and evidence:** sandbox_tools.py:460-508, 675-702.
- **Gap/status:** Retain reusable session; avoid one-command detonate path for multi-phase inspection.
- **Senior-engineer action:** Maintain a session lifecycle manager with ref-counting and leasing in `spacev/fleet/celesto_engine.py`, guaranteeing that the same guest container instance is preserved across Stages 3, 4, 5, and 6, avoiding expensive multi-minute re-provisioning and maintaining guest filesystem state throughout the test cycle.

#### 3.4 Guest readiness
- **Target:** Do not advertise ready until a real VM is connected.
- **Actual attempt/behavior:** CelestoSandboxInstance starts Computer eagerly and records ready only after start returns.
- **Source and evidence:** celesto_engine.py:63-117; sandbox_tools.py:645-673.
- **Gap/status:** Good direction. Add backend capability handshake and verify returned machine identity before issuing commands.
- **Senior-engineer action:** Implement an active guest readiness handshake in `CelestoSandboxInstance.start()` that executes a canary echo command (`/bin/sh -c 'echo celesto_ready_$(uname -m)'`) with exponential backoff (up to 15s) and verifies a non-empty machine identity before marking the session state as `ACTIVE`.

#### 3.5 Unique local name
- **Target:** Avoid stale generated-name collision.
- **Actual attempt/behavior:** SpaceV generates UUID name and passes it to Celesto’s private _build_auto_config for local provider.
- **Source and evidence:** celesto_engine.py:81-100; sandbox_tools.py:648-650.
- **Gap/status:** The observed sbx-noether collision predates or bypassed this path; verify current SDK integration in a controlled run.
- **Senior-engineer action:** Enforce RFC 4122 UUIDv4 container and VM naming (`name = f"sbx-{uuid.uuid4().hex}"`) across all Celesto configuration factories, eliminating static fallback names (such as `sbx-noether`) and executing a pre-creation Docker/container cleanup check to eliminate orphaned namespace collisions.

#### 3.6 Git missing
- **Target:** Check guest toolchain; install only after approval.
- **Actual attempt/behavior:** run_sandbox_session_command executes exact guest command; prompt schema says inspect OS before assuming apk/apt.
- **Source and evidence:** registry.py:1302-1313; issue_test_workflow.py:56-82.
- **Gap/status:** Preflight command should collect os-release, git, python, disk, outbound access; no silent package installation.
- **Senior-engineer action:** Provision sandbox images using pre-baked Ubuntu 22.04 LTS / Debian base images that already bundle `git`, `python3`, `pip`, and `pytest`, or execute an automated preflight probe (`which git python3`) during initialization to eliminate mid-flight package manager failures and avoid unauthorized guest package installations.

#### 3.7 Git install
- **Target:** Package install changes guest state and requires clear authorization.
- **Actual attempt/behavior:** User approved apk add --no-cache git in one prior Alpine session; output said Git 2.43.7 installed.
- **Source and evidence:** Conversation log 03:31:11 approval and 03:36:49 success summary; session IDs differ from other attempts.
- **Gap/status:** Install only if the exact approved task includes install or a new approval is obtained; store receipt and distro identity.
- **Senior-engineer action:** Standardize guest images to production-grade developer environments containing Git 2.40+ by default; if dynamic package installation is ever strictly necessary, wrap it in a typed `GuestProvisioningPlan` requiring explicit user authorization and logging the package manager exit receipt to `TaskEvidenceStore`.

#### 3.8 Clone command
- **Target:** Clone source to a fixed disposable path and pin commit.
- **Actual attempt/behavior:** Guest commands are free-form shell strings; manager does not parse approved plan to enforce command sequence.
- **Source and evidence:** sandbox_tools.py:675-702; schema registry.py:1304-1313.
- **Gap/status:** Use typed clone action or strict command policy; validate URL/path and reject shell chaining outside approved commands.
- **Senior-engineer action:** Replace arbitrary shell string execution with a parameterized guest clone method `clone_repo(target_url, workdir="/workspace/repo", depth=50)` that executes `git clone --depth 50 <url> /workspace/repo && cd /workspace/repo && git rev-parse HEAD`, preventing arbitrary shell injection and ensuring standardized repository location.

#### 3.9 Clone timeouts
- **Target:** Bound clone duration and preserve diagnostic output.
- **Actual attempt/behavior:** Celesto instance uses run(command, timeout=30); repo_tools host clone has 180-second timeout.
- **Source and evidence:** celesto_engine.py:134-149; repo_tools.py:118-146.
- **Gap/status:** Guest clone timed out at 30 seconds in logs. Set explicit operation timeout or progress-aware clone, but never auto-retry.
- **Senior-engineer action:** Increase guest command timeout for `git clone` operations from 30 seconds to 180 seconds in `celesto_engine.py` (with shallow clone `--depth 50`), capturing incremental stdout/stderr so that progress can be monitored without premature SIGTERM aborts.

#### 3.10 Network access
- **Target:** GitHub and package repositories need outbound access.
- **Actual attempt/behavior:** Celesto session uses network configuration; proposal text describes network intent but no internet health check is enforced by manager.
- **Source and evidence:** sandbox_tools.py:580-702; celesto_engine.py:32-56.
- **Gap/status:** Expose network policy and preflight receipts. Distinguish DNS, TCP/TLS, GitHub, and package mirror failures.
- **Senior-engineer action:** Implement a pre-clone connectivity check (`curl -sI --connect-timeout 5 https://github.com`) within the sandbox before issuing git commands, distinguishing DNS lookup failures, egress firewall blocks, and HTTP proxy errors, logging the diagnostic receipt to `TaskEvidenceStore`.

#### 3.11 Cleanup
- **Target:** Disposable VM must close after success or terminal failure.
- **Actual attempt/behavior:** Graph directly closes after failed guest execution; manager has TTL reaper and explicit close; close reports state/timing.
- **Source and evidence:** graph_engine.py:1625-1668; sandbox_tools.py:487-503, 704-734.
- **Gap/status:** Retain close path. Record cleanup state even when command tool call fails or context is lost.
- **Senior-engineer action:** Wrap all sandbox operations in an asynchronous Python context manager (`async with CelestoSandboxSession(...) as session:`) with guaranteed `finally:` teardown, ensuring that MicroVMs, containers, and temporary disk volumes are destroyed even on unhandled exceptions, SIGINT, or timeout events.

#### 3.12 Acceptance proof
- **Target:** Clone success requires commit and initial clean status from the guest.
- **Actual attempt/behavior:** No clone receipt automatically pins commit or baseline state; issue gate later searches session receipts for git rev-parse/status.
- **Source and evidence:** graph_engine.py:1446-1540.
- **Gap/status:** Make clone stage return typed commit/status receipt and fail stage transition unless exit code is zero and paths are clean.
- **Senior-engineer action:** Execute `git rev-parse HEAD` and `git status --porcelain` immediately following clone completion; store the returned commit SHA and clean working-tree confirmation in a typed `Stage3AcceptanceReceipt`, failing stage transition if exit code != 0 or untracked changes exist.

### Stage 4 — Inspect source code and existing tests

**Overall status:** PARTIAL — the model can inspect through guest shell, but completion is not structurally validated.

**Current implementation map:** graph_engine.py:1202-1305; sandbox_tools.py:675-702; agent_configs.py:125-131; task_evidence.py:146-212.

#### 4.1 Relevant test discovery
- **Target:** Locate named test, fixtures, and surrounding context in the cloned commit.
- **Actual attempt/behavior:** Agent prompt asks inspect existing tests; command tool accepts generic shell text.
- **Source and evidence:** agent_configs.py:125-132; sandbox_tools.py:675-702.
- **Gap/status:** Collect exact path, line range, and excerpt; stop if named test is absent rather than broadening silently.
- **Senior-engineer action:** Implement an automated test locator using `pytest --collect-only -q` or AST parsing over `tests/` in the guest sandbox, extracting exact test file paths, test function names, and enclosing class structures related to the issue keywords, persisting the located test nodes in `TaskEvidenceStore`.

#### 4.2 Source path mapping
- **Target:** Trace test to implementation functions/classes.
- **Actual attempt/behavior:** Prompt asks inspect relevant code; no static source map object is required before stage exit.
- **Source and evidence:** agent_configs.py:125-132.
- **Gap/status:** Require a source map with symbol, file, line span, caller/callee relation, and why relevant.
- **Senior-engineer action:** Generate a static symbol call graph in the sandbox using Python AST analysis or `cpg`/`grep` targeting the modules imported by the located test, producing a structured `SourceInspectionMap(symbol, file_path, line_range, call_sites)` that is saved to the task evidence ledger.

#### 4.3 Inspection command failures
- **Target:** Any failed grep/read command should be reported and stop dependent analysis.
- **Actual attempt/behavior:** Failed guest command is terminal for the active task; cleanup follows.
- **Source and evidence:** graph_engine.py:1625-1668, 1732-1748.
- **Gap/status:** Good fail-closed policy. Failure classification should distinguish grep no-match exit 1 from VM execution failure.
- **Senior-engineer action:** Implement semantic exit-code classification in `core/issue_test_workflow.py`: treat `grep` exit code 1 as a non-fatal `SYMBOL_NOT_FOUND` signal (prompting fallback search) while treating exit code 2 or command timeouts as fatal infrastructure errors, avoiding premature aborts on simple search misses.

#### 4.4 Search precision
- **Target:** Exact test names should not be replaced with vaguely related hits.
- **Actual attempt/behavior:** No dedicated command allowlist or exact-name-presence gate exists; LLM chooses command.
- **Source and evidence:** sandbox_tools.py:675-702; agent_configs.py:125-143.
- **Gap/status:** Represent required inspection targets declaratively and parse receipts against them.
- **Senior-engineer action:** Enforce exact symbol matching by searching for definitions (`def test_...`, `class Test...`) using `git grep -n -F "<symbol_name>"` before resorting to broad fuzzy searches, validating that any captured test actually contains the specific assertion logic under investigation.

#### 4.5 Source completeness
- **Target:** Need all code paths directly relevant to the observed symptom.
- **Actual attempt/behavior:** No deterministic “all required modules inspected” state transition found.
- **Source and evidence:** graph_engine.py graph routes; no dedicated inspector node.
- **Gap/status:** Add checklist of required source/test evidence fields and block proposal until complete or explicitly waived.
- **Senior-engineer action:** Define a deterministic `InspectionChecklist` requiring both (1) the existing test definition and (2) the target implementation function/method body to be successfully captured in `TaskEvidenceStore` before allowing the workflow state machine to transition to Stage 5.

#### 4.6 Dependency/environment info
- **Target:** Record runtime version and test requirements without installing.
- **Actual attempt/behavior:** detect_guest_environment parses OS release, Python, architecture only when cat /etc/os-release output captured.
- **Source and evidence:** issue_test_workflow.py:56-94; graph_engine.py:1432-1443.
- **Gap/status:** Add read-only version probes for package manager, Git, Python, and test runner; installation remains approval-gated.
- **Senior-engineer action:** Run a read-only environment probe (`python3 --version; pip list --format=freeze | grep -E "pytest|urllib3|requests"; cat /etc/os-release`) upon sandbox initialization and serialize the returned runtime manifest into `guest_env_receipt.json`.

#### 4.7 Same checkout provenance
- **Target:** Test and source must be read from same pinned commit.
- **Actual attempt/behavior:** Test execution gate uses session-scoped git rev-parse HEAD receipts; inspect stage itself not tied to commit mechanically.
- **Source and evidence:** graph_engine.py:1446-1525.
- **Gap/status:** Attach each inspection receipt to guest session ID and pinned commit; reject cross-session evidence.
- **Senior-engineer action:** Tag every file read and grep receipt with `(session_id, pinned_commit_sha)`; reject any inspection receipt if the current sandbox HEAD does not match the pinned checkout commit SHA.

#### 4.8 Actual #7639 run
- **Target:** A complete code path should be evidenced before diff generation.
- **Actual attempt/behavior:** User corrected prior summary: test body captured; source inspection not completed.
- **Source and evidence:** Conversation correction at 07:57:16; later issue text was unavailable in current turn.
- **Gap/status:** Stage is incomplete. Re-run only after a fresh approved task; don’t reuse the prior overstated summary.
- **Senior-engineer action:** Reset the inspection state for issue #7639 to `INCOMPLETE`, purge unverified claims from memory, and require a fresh, approved execution of both test and source file inspection before allowing test generation.

#### 4.9 Output truncation
- **Target:** Inspection excerpts must include enough surrounding lines to reason.
- **Actual attempt/behavior:** Evidence store bounds records; tool results are compressed for model context; truncation flags exist.
- **Source and evidence:** task_evidence.py:102-109, 146-166; graph_engine.py:1384-1401.
- **Gap/status:** Store full bounded artifact by receipt ID; pass relevant excerpts plus a truncation flag and request targeted continuation if cut.
- **Senior-engineer action:** Store full, un-truncated file contents (up to 1MB) in `TaskEvidenceStore` on disk while providing a windowed excerpt (±50 lines around the target symbol) with exact byte and line offsets to the LLM context, preventing context starvation while preserving full inspection evidence.

#### 4.10 Acceptance proof
- **Target:** Stage passes only if required test and source evidence are collected.
- **Actual attempt/behavior:** Current graph is model-led; no explicit state enum for INSPECTION_COMPLETE was observed.
- **Source and evidence:** graph_engine.py:351-425, 855-968.
- **Gap/status:** Create deterministic stage validator that checks each requested file/test target has a successful same-session read receipt.
- **Senior-engineer action:** Issue a signed `Stage4AcceptanceReceipt` containing paths and SHA-256 hashes of inspected test and implementation files; block transition to Stage 5 until this receipt is cryptographically validated in the workflow ledger.

### Stage 5 — Generate a minimal failing test (proposal only)

**Overall status:** PARTIAL — prompt requirements exist; no evidence proves grounded test generation completed in the corrected run.

**Current implementation map:** agent_configs.py:120-143; graph_engine.py:855-968, 980-1177; issue_test_workflow.py:118-205.

#### 5.1 Minimality
- **Target:** Propose the smallest test that captures the issue.
- **Actual attempt/behavior:** ISSUE_TEST system prompt requests a focused test diff.
- **Source and evidence:** agent_configs.py:123-132.
- **Gap/status:** Require one focused behavior assertion; reject unrelated refactors, fixtures, and multiple test changes.
- **Senior-engineer action:** Enforce an automated patch complexity linter in `core/issue_test_workflow.py` that verifies the proposed diff contains $\le 1$ new test function, $\le 30$ modified lines, touches only existing test files or adds a single test module, and contains no structural refactors or multi-test additions.

#### 5.2 No production fix
- **Target:** Demonstrate, do not repair.
- **Actual attempt/behavior:** Prompt says role proposes test and does not fix production code; path classifier can flag changed non-test paths.
- **Source and evidence:** agent_configs.py:133-141; issue_test_workflow.py:231-298.
- **Gap/status:** Keep production files read-only until user explicitly changes task scope.
- **Senior-engineer action:** Implement an AST and path gate that parses the unified diff headers; if any modified file path does not match `tests/**` or `test_*.py`, reject the diff immediately with `ProductionCodeModificationForbiddenError` and demand a test-only revision.

#### 5.3 Issue grounding
- **Target:** Test must reflect reported expected behavior.
- **Actual attempt/behavior:** Prompt asks to derive expected_failure_signal only when grounded; generic goal schema stores entities.
- **Source and evidence:** grounded_agent.py:76-78; agent_configs.py:127-132.
- **Gap/status:** Bind every assertion and failure signal to a quoted/paraphrased issue evidence span.
- **Senior-engineer action:** Require the model proposal payload to include explicit `citation_offset` and `expected_failure_signal` matching terms from the validated Stage 2 `IssueSemantics` record, validating semantic alignment before presenting the diff to the user.

#### 5.4 Diff grounding
- **Target:** Diff must apply to the actual inspected test body.
- **Actual attempt/behavior:** Model generates response text; current logs corrected that no proposed diff was completed.
- **Source and evidence:** graph_engine.py:1902-2018; conversation correction 07:57:16.
- **Gap/status:** Generate unified diff from captured file text and validate hunk context against read receipt before presenting.
- **Senior-engineer action:** Validate proposed unified diffs using `git apply --check` in memory against the exact file content captured in Stage 4 read receipts; if hunks do not apply cleanly or context lines mismatch, automatically re-prompt the diff generator with exact line numbers.

#### 5.5 Import/fixture assumptions
- **Target:** Use actual test module imports and fixtures.
- **Actual attempt/behavior:** No enforced import/fixture inspection prerequisite is visible in proposal prompt.
- **Source and evidence:** agent_configs.py:125-143.
- **Gap/status:** Require header imports and target fixture excerpt before a pytest-based patch can be accepted.
- **Senior-engineer action:** Inject the captured test file's top-level imports and available `conftest.py` fixtures into the test generation prompt; parse the proposed diff using `ast.parse()` to ensure all invoked symbols and decorators are defined or imported.

#### 5.6 Expected failure reason
- **Target:** Explain why candidate should fail on the current bug.
- **Actual attempt/behavior:** Issue prompt asks for explanation; classifier is only active after actual test command.
- **Source and evidence:** agent_configs.py:130-139; issue_test_workflow.py:153-205.
- **Gap/status:** Separate prediction from observed result. Label proposed result as hypothesis, never as verified failure.
- **Senior-engineer action:** Enforce strict separation in data schemas between `HypothesizedFailure(signal, reason, assertion)` and `ObservedTestFailure(exit_code, stdout, stderr, signal_matched)` to prevent predictive text from being reported as empirical proof.

#### 5.7 Diff-only review
- **Target:** Show proposal without editing files.
- **Actual attempt/behavior:** Prompt and user approval boundary require separate approval before edit/run.
- **Source and evidence:** agent_configs.py:133-143; sandbox_tools.py run command accepts arbitrary command after approval.
- **Gap/status:** Add explicit state WAITING_FOR_DIFF_APPROVAL and reject all write/test commands until it is approved.
- **Senior-engineer action:** Transition workflow state machine into `WAITING_FOR_DIFF_APPROVAL`, displaying a syntax-highlighted unified diff in the UI and locking guest execution tools until an explicit user confirmation token is received.

#### 5.8 Expected/actual ambiguity
- **Target:** Call out unclear contract instead of guessing.
- **Actual attempt/behavior:** Prompt requires uncertainties; model judgment currently supplies this behavior.
- **Source and evidence:** agent_configs.py:127-132.
- **Gap/status:** Persist ambiguity flags; prevent candidate-test generation when expected contract is unresolved.
- **Senior-engineer action:** Add an `ambiguity_score` metric to the issue semantic parser; if contradictory expected behaviors or missing reproduction steps are detected, pause test synthesis and trigger an interactive user clarification prompt.

#### 5.9 Actual #7639 diff
- **Target:** A credible diff should be grounded in captured test, imports, issue, and code.
- **Actual attempt/behavior:** Prior assistant once proposed pytest.raises diff from incomplete evidence; user says source/diff not established in corrected run.
- **Source and evidence:** Conversation logs at 16:49:27 and 07:57:16 conflict in evidence completeness; treat specific run as not completed.
- **Gap/status:** Withdraw unsupported diff claims. Reconstruct only from a new successful read receipt and issue text.
- **Senior-engineer action:** Mark all previously hallucinated diff artifacts for issue #7639 as `INVALIDATED_DUE_TO_INCOMPLETE_EVIDENCE`; mandate that a new candidate diff can only be synthesized after Stages 2, 3, and 4 are demonstrably re-executed and verified.

#### 5.10 Acceptance proof
- **Target:** Stage passes only when diff is shown and clearly test-only.
- **Actual attempt/behavior:** No deterministic diff artifact validation before report stage was found.
- **Source and evidence:** agent_configs.py prompt; no separate test-diff validator in graph.
- **Gap/status:** Persist exact diff bytes/hash and approval state; validate changed paths after edits.
- **Senior-engineer action:** Save the candidate diff as an immutable artifact with `diff_sha256`, target file path, and AST-validated test-only flag; generate `Stage5AcceptanceReceipt` prior to requesting test execution authorization.

### Stage 6 — Execute and verify the test

**Overall status:** NOT DEMONSTRATED — safeguards exist, but no candidate test was run in the provided #7639 evidence.

**Current implementation map:** graph_engine.py:1286-1305, 1446-1540, 1403-1444; issue_test_workflow.py:153-205, 208-298.

#### 6.1 Separate approval
- **Target:** Exact diff and exact command need approval before file edit/test.
- **Actual attempt/behavior:** ISSUE_TEST prompt states this; patch gate blocks test command without evidence.
- **Source and evidence:** agent_configs.py:135-140; graph_engine.py:1446-1540.
- **Gap/status:** Keep distinct approvals for write and run; store exact diff hash plus command string.
- **Senior-engineer action:** Require two-phase authorization: (1) user approves applying the exact SHA-256 signed diff, and (2) user approves the exact pytest command string (`pytest tests/test_... -k ...`), logging each approval to the durable audit ledger.

#### 6.2 Commit pin
- **Target:** Record exact revision before any candidate changes.
- **Actual attempt/behavior:** Gate parses successful git rev-parse HEAD in same session.
- **Source and evidence:** graph_engine.py:1471-1496.
- **Gap/status:** Retain; include repository URL, commit SHA and session ID in every test receipt.
- **Senior-engineer action:** Execute `git rev-parse HEAD` immediately prior to applying the diff; record this baseline commit SHA in the test run receipt to guarantee that test evaluation occurs against the exact unmodified commit.

#### 6.3 Clean baseline
- **Target:** Capture git status before edits.
- **Actual attempt/behavior:** Gate requires successful clean status associated with pinned commit.
- **Source and evidence:** graph_engine.py:1497-1509, 1527-1535.
- **Gap/status:** Retain; reject truncated status output or status captured before clone finished.
- **Senior-engineer action:** Execute `git status --porcelain` and assert that stdout is empty; abort execution if any untracked or modified files exist before the candidate test patch is applied.

#### 6.4 Passing baseline
- **Target:** Candidate failure only means something if baseline passes.
- **Actual attempt/behavior:** Gate looks for PASS_NO_REPRODUCTION while initial tree clean and before patch.
- **Source and evidence:** graph_engine.py:1511-1518; issue_test_workflow.py:181-183.
- **Gap/status:** Require baseline command approval if not covered; record command and dependencies exactly.
- **Senior-engineer action:** Automate running the unmodified test target in the clean sandbox *before* applying the diff (`pytest <test_path>::<existing_test>`); record a verified `BaselineTestReceipt(exit_code=0, passed=True)` and fail immediately if the baseline is already broken.

#### 6.5 Test-only patch
- **Target:** Candidate edit may touch only test paths and few files.
- **Actual attempt/behavior:** Classifier limits two paths, checks path safety and test-like names.
- **Source and evidence:** issue_test_workflow.py:231-298; graph_engine.py:1506-1525.
- **Gap/status:** Retain but supplement with git diff --check and exact diff review; status-only cannot prove content.
- **Senior-engineer action:** Apply patch via `git apply --check` followed by `git apply`; run `git diff --stat` to verify that 100% of modified lines are confined to `tests/` and no unexpected files were touched.

#### 6.6 Test output parsing
- **Target:** Use targeted test failure and expected issue phrase.
- **Actual attempt/behavior:** Classifier extracts target pytest node/path and searches that failure block for expected signal.
- **Source and evidence:** issue_test_workflow.py:108-150, 153-205.
- **Gap/status:** Retain; add tests for output truncation, parametrized node IDs, Windows paths, pytest summary variants.
- **Senior-engineer action:** Implement a robust pytest JUnit XML or structured report parser (`pytest --junitxml=report.xml --tb=short`) that extracts exact failure message, traceback, and assertion error, matching against `expected_failure_signal` using normalized regex tokenization.

#### 6.7 Infrastructure categories
- **Target:** Timeout, import, dependency, discovery errors are not bug reproduction.
- **Actual attempt/behavior:** Classifier names TIMEOUT, TEST_DISCOVERY_ERROR, DEPENDENCY_ERROR, IMPORT_ERROR, ENVIRONMENT_ERROR, INCONCLUSIVE.
- **Source and evidence:** issue_test_workflow.py:153-205.
- **Gap/status:** Good foundation. Ensure tool exit code and underlying Celesto receipt are present before classification.
- **Senior-engineer action:** Enforce strict failure classification taxonomy in `classify_test_output()`: map exit code 2 to `SYNTAX_OR_IMPORT_ERROR`, exit code 4 to `TEST_DISCOVERY_ERROR`, exit code 124/137 to `TIMEOUT`, exit code 1 without matching assertion signal to `UNEXPECTED_TEST_FAILURE`, and exit code 1 with verified signal to `EXPECTED_BUG_FAILURE`.

#### 6.8 No automatic retry
- **Target:** Timeout should stop; retry only if user reauthorizes exact action.
- **Actual attempt/behavior:** Prompt says timeout is TIMEOUT and not permission to retry; graph stops failed guest execution and closes.
- **Source and evidence:** agent_configs.py:138; graph_engine.py:1625-1668, 1732-1748.
- **Gap/status:** Retain terminal behavior; allow only a new user-approved session/task after timeout.
- **Senior-engineer action:** Treat any command execution timeout as a hard terminal state; disallow automated retries or prompt loops; require user review of captured partial output and explicit parameter reauthorization before re-running.

#### 6.9 Actual result
- **Target:** A candidate test output/exit code is necessary.
- **Actual attempt/behavior:** Conversation corrections explicitly state no tests were run for the incomplete #7639 task.
- **Source and evidence:** Conversation correction at 07:57:16 and later 13:52:05.
- **Gap/status:** Status remains unverified; never classify prior git/grep errors as EXPECTED_BUG_FAILURE.
- **Senior-engineer action:** Maintain empirical truth in the audit ledger: issue #7639 has zero executed test runs; classify Stage 6 as `NOT_RUN` and prohibit any reporting node from synthesizing a simulated test result.

#### 6.10 Acceptance proof
- **Target:** A passing baseline and expected-symptom target failure are both present.
- **Actual attempt/behavior:** Gate and classifier encode these checks but no passing run receipt exists in supplied evidence.
- **Source and evidence:** graph_engine.py:1446-1540; issue_test_workflow.py:153-205.
- **Gap/status:** Produce a machine-checkable verification record; only it can set stage VERIFIED.
- **Senior-engineer action:** Emit a signed `Stage6AcceptanceReceipt` strictly when $(C_{\text{base}} = 0 \land C_{\text{cand}} = 1 \land \text{Signal} \in \text{Stdout} \land \text{Scope} \subseteq \text{Tests})$; without this mathematical proof, reject verification completion.

### Stage 7 — Deliver evidence and report

**Overall status:** PARTIAL — evidence persistence/export exists, but previous reports overstated what logs proved.

**Current implementation map:** task_evidence.py:57-360; graph_engine.py:1384-1444, 1670-1730, 1902-2018, 2193-2221; sandbox_tools.py:704-734.

#### 7.1 Receipt preservation
- **Target:** Keep exact tool name, arguments, status, output, source, truncation and session identity.
- **Actual attempt/behavior:** TaskEvidenceStore stores bounded/redacted tool evidence and chat turns in local SQLite.
- **Source and evidence:** task_evidence.py:71-178.
- **Gap/status:** Retain; make receipt IDs first-class references in workflow state and final report.
- **Senior-engineer action:** Store all raw command invocations, return codes, stdout, stderr, execution wall-clock time, and environment hashes in SQLite (`TaskEvidenceStore`), generating unique UUIDv4 receipt handles referenced in all downstream reports.

#### 7.2 Cross-turn recall
- **Target:** Follow-up turns should recover prior task evidence.
- **Actual attempt/behavior:** Goal interpretation retrieves related context; sandbox continuation context holds pending/active task.
- **Source and evidence:** graph_engine.py:610-639; task_evidence.py:213-287; sandbox_tools.py:510-559.
- **Gap/status:** Recall is helpful but not authoritative alone; load task state and receipts by workflow/session ID.
- **Senior-engineer action:** Implement indexed session state restoration in `core/durable_ledger.py` keyed by `workflow_id`, allowing any subsequent conversational turn to hydrate the full historical receipt chain rather than relying on LLM memory or prompt stuffing.

#### 7.3 Truncation visibility
- **Target:** A short excerpt must not masquerade as full output.
- **Actual attempt/behavior:** _bounded returns a truncation flag; records cap output; export records hash/truncation metadata.
- **Source and evidence:** task_evidence.py:102-109, 146-166, 288-360.
- **Gap/status:** Retain and ensure final response explicitly reports missing/truncated evidence.
- **Senior-engineer action:** Add explicit visual indicators and metadata flags (`[TRUNCATED: Showing lines 1-100 of 850; full output in receipt_id=...]`) whenever tool outputs exceed model context thresholds, guaranteeing that truncated logs are never mistaken for complete test traces.

#### 7.4 Claim/evidence separation
- **Target:** Model summary should not be mistaken for tool result.
- **Actual attempt/behavior:** Records have source_kind tool/chat and export bundle focuses on tool receipts.
- **Source and evidence:** task_evidence.py:111-145, 168-212, 288-360.
- **Gap/status:** Good foundation; report generator should only mark completion from typed tool receipts.
- **Senior-engineer action:** Structurally segregate reports into two discrete sections: (1) Deterministic Evidence Table (pure tool receipts and exit codes directly formatted by Python without LLM modification), and (2) Agent Synthesis & Recommendations (clearly marked LLM prose analysis).

#### 7.5 Final response
- **Target:** Report must not exaggerate source inspection or diff completion.
- **Actual attempt/behavior:** Response synthesis is generally LLM-led; deterministic special case is sandbox status.
- **Source and evidence:** graph_engine.py:1902-2018.
- **Gap/status:** Render issue-task report from structured evidence, then use LLM only for explanation and bounded prose.
- **Senior-engineer action:** Construct the final user-facing status report using a Jinja2 deterministic template populated directly from verified stage acceptance receipts; invoke the LLM only to produce the explanatory prose summary within strict bounds.

#### 7.6 Cleanup evidence
- **Target:** State whether VM was deleted and include timing/error.
- **Actual attempt/behavior:** close returns explicit state and timings; graph stores close tool result after failure.
- **Source and evidence:** sandbox_tools.py:704-723; graph_engine.py:1625-1668.
- **Gap/status:** Require cleanup receipt before final state; if cleanup fails, say so and keep run incomplete.
- **Senior-engineer action:** Generate an explicit `TeardownReceipt(session_id, destroyed_at, duration_ms, status)` recorded in `TaskEvidenceStore`; prominently display container destruction confirmation in the executive report summary.

#### 7.7 Actual report quality
- **Target:** Corrected report should retract unsupported claims.
- **Actual attempt/behavior:** User correction explicitly noted prior summary overclaimed completed inspection/diff.
- **Source and evidence:** Conversation user correction at 07:57:16.
- **Gap/status:** Use confidence/provenance rule: if no receipt, report NOT VERIFIED, not completed.
- **Senior-engineer action:** Apply a strict empirical proof invariant across all audit generation logic: any stage lacking an immutable receipt in SQLite must be rendered as `NOT DEMONSTRATED` or `UNVERIFIED`, eliminating speculative or optimistic status claims.

#### 7.8 Evidence bundle
- **Target:** A reproducible report artifact should tie to exact session.
- **Actual attempt/behavior:** export_bundle includes matching session receipts, bounded text and hashes.
- **Source and evidence:** task_evidence.py:288-360; graph_engine.py:2193-2209.
- **Gap/status:** Retain; include issue record, commit, diff hash, test command/result and cleanup object in schema.
- **Senior-engineer action:** Package all run artifacts into an OCI-compliant or zip/json bundle (`bundle_<workflow_id>.json`) containing the parsed issue, commit SHA, unified diff, pytest stdout/stderr, and environment receipt, enabling 100% offline reproducibility.

#### 7.9 Final stage status
- **Target:** “Complete” means all seven stage validators pass.
- **Actual attempt/behavior:** No single all-stage issue workflow status is evident in source map.
- **Source and evidence:** graph_engine.py graph routes separate generic nodes.
- **Gap/status:** Introduce terminal status enum and explicit completion invariant.
- **Senior-engineer action:** Define a terminal state enum `WorkflowVerdict(VERIFIED_FAILING_TEST, BASELINE_FAILURE, ENVIRONMENT_ERROR, INSUFFICIENT_EVIDENCE, USER_ABORTED)`; compute the verdict deterministically as a Boolean conjunction of all 7 stage receipts ($\bigwedge_{i=1}^{7} \text{Receipt}_i.\text{valid}$).

#### 7.10 Acceptance proof
- **Target:** Final report cites data and uncertainties.
- **Actual attempt/behavior:** Current reports may synthesize from compressed model context and past turns.
- **Source and evidence:** graph_engine.py:1902-2018; task_evidence.py:213-287.
- **Gap/status:** Build from evidence IDs, include unverified list, and test that unsupported claims are impossible.
- **Senior-engineer action:** Append cryptographic SHA-256 signatures to the final markdown report corresponding to each cited receipt ID, providing an immutable audit trail that can be verified independently by external tooling.



## 5. Current source map: files, classes, functions, and methods

### 5.1 Graph construction and execution

| Source lines | Symbol | Workflow responsibility | Evidence-backed interpretation |
|---|---|---|---|
| core/graph_engine.py:29-65 | CompiledNativeApp | Graph fallback runtime | Invokes nodes and follows configured transitions. |
| core/graph_engine.py:68-104 | StateGraph | Graph wiring abstraction | Registers nodes, routes and terminal edges. |
| core/graph_engine.py:106-130 | SpaceVState | Shared graph state | Carries prompts, goals, tools, evidence, sandbox context and completion flags. |
| core/graph_engine.py:132-196 | determine_tool_status | Normalize result state | Converts tool receipts to status labels. |
| core/graph_engine.py:198-211 | sandbox_context_payload / sandbox_context_state | Continue session | Reads state tags from serialized context. |
| core/graph_engine.py:294-335 | prune_conversation_trauma | Context pruning | Removes old conversation messages; relevant to long tasks. |
| core/graph_engine.py:338-348 | SpaceVGraphEngine.__init__ | Build graph owner | Sets the agent and graph runtime. |
| core/graph_engine.py:351-425 | _build_graph | Actual topology | Entry is goal_interpreter; nodes include perception, reasoning, tools, healing, clarification and response. |
| core/graph_engine.py:430-648 | _goal_interpreter_node | Guard and goal construction | Security, placeholders, GitHub URL parsing, proposal/approval fast path, memory recall and goal interpretation. |
| core/graph_engine.py:651-659 | _route_after_goal | Initial route | Complete, sandbox control, conversation, or action. |
| core/graph_engine.py:665-847 | _fast_router_node | Quick route / remediation | Handles selected deterministic shortcuts; not an issue-specific workflow controller. |
| core/graph_engine.py:848-853 | _route_after_fast_router | Fast route choice | Complete, perception, or direct tools. |
| core/graph_engine.py:855-974 | _perception_guard_node | Context and role prompt | Captures environment, scratchpad plan, selects issue specialist prompt. |
| core/graph_engine.py:975-978 | _route_after_perception | Perception transition | Stops when stuck; otherwise reasons. |
| core/graph_engine.py:980-1177 | _model_reasoning_node | LLM tool planning | Chooses model and tools; LLM output drives next action. |
| core/graph_engine.py:1178-1200 | _route_after_reasoning | Reasoning transition | Execute tool calls, loop reasoning, or synthesize. |
| core/graph_engine.py:1202-1383 | _tool_executor_node / _exec_single | Tool dispatch and guardrails | Enforces sandbox scope and active-session controls, then calls registry. |
| core/graph_engine.py:1384-1402 | _record_evidence | Receipt persistence | Stores bounded tool result and truncation signal. |
| core/graph_engine.py:1403-1445 | _issue_test_note | Deterministic annotations | Applies guest/test/status/path classifiers to sandbox command receipts. |
| core/graph_engine.py:1446-1548 | _issue_test_patch_gate | Candidate-test gate | Requires same-session commit, clean baseline, passing baseline and approved test-only path audit. |
| core/graph_engine.py:1625-1668 | Failure cleanup block | Terminal guest failure | Closes session and records close result when guest execution fails. |
| core/graph_engine.py:1732-1817 | _route_after_tools | Post-tool route | Stops failed guest command; routes other failures and pending work. |
| core/graph_engine.py:1819-1879 | _self_healing_node / _route_after_healing | Generic recovery | Diagnoses/remediates selected failures; active guest failures have stricter handling. |
| core/graph_engine.py:1881-1900 | _clarification_node | Ask and stop | Returns a clarification question. |
| core/graph_engine.py:1902-2135 | _response_synthesizer_node | User-facing response | Synthesizes from messages/results; sandbox-status case has deterministic response path. |
| core/graph_engine.py:2137-2238 | run | Graph entry | Initializes state, invokes graph, exports issue evidence and records completed turn. |

### 5.2 Role, goal, issue and evidence modules

| File and lines | Class/function/method | Purpose | Limitation or connection |
|---|---|---|---|
| core/swarm_orchestrator.py:77-82 | route_task | Select role and dispatch | Role routing does not itself run a seven-stage issue workflow. |
| core/swarm_orchestrator.py:84-105 | classify_agent_role | Select ISSUE_TEST for issue URL/phrase | Phrase/URL heuristic is finite; it should not be the only capability resolver. |
| core/swarm_orchestrator.py:126-196 | dispatch | Build/dispatch role task | Specialized role is prompt/config, not independent process isolation. |
| core/swarm_orchestrator.py:197-220 | _build_agent_prompt | Compose role prompt | LLM prompt informs behavior but cannot prove action. |
| core/agent_configs.py:16-21 | AgentRole | Role enum | Includes ISSUE_TEST and AUDITOR. |
| core/agent_configs.py:24-48 | AgentConfig | Role settings | Provider/model, token caps, retries, timeout and tools. |
| core/agent_configs.py:120-146 | ISSUE_TEST_AGENT_CONFIG | Issue analyst policy | Requires uncertainty, baseline, focused diff, approval and evidence-based classification. |
| core/agent_configs.py:147-165 | ISSUE_TEST config values | Limits and allowlist | 3000 per-turn; allowed tools include read_web_page, clone_public_repository, file/code tools and sandbox controls. |
| core/agent_configs.py:168-189 | AUDITOR_AGENT_CONFIG | General auditor | Separate config exists; no mandatory independent adversarial audit stage is shown. |
| core/grounded_agent.py:16-31 | GroundedGoal | Generic typed goal | No issue-specific required fields or completion phase enum. |
| core/grounded_agent.py:33-53 | normalize_goal_alias | Normalize model JSON | Converts goal alias/scalar entities; does not repair malformed arbitrary JSON. |
| core/grounded_agent.py:56-135 | interpret_goal | Model JSON and fallback | Catches errors and returns raw-request fallback, which weakens structured workflow requirements. |
| core/grounded_agent.py:138-183 | inspect_environment | Desktop/system snapshot | Not a source-code repository inspector. |
| core/grounded_agent.py:185-188 | evidence_context | Format observations | Makes evidence model-readable. |
| core/grounded_agent.py:190-239 | tools_for_goal | Filter tools by domain | Depends on model-produced tool_domains. |
| core/issue_test_workflow.py:19-53 | parse_github_issue_url | Validate public issue URL | Correctly rejects unsupported URL forms and derives repo identity. |
| core/issue_test_workflow.py:56-94 | detect_guest_environment / format_guest_environment | Parse environment receipt | Limited to OS release, Python and architecture fields. |
| core/issue_test_workflow.py:97-115 | _is_test_path / _target_test_from_command | Detect test paths and target | Heuristic patterns need regression coverage. |
| core/issue_test_workflow.py:118-150 | _target_failure_contains_signal | Match symptom to target failure | Avoids matching arbitrary phrase elsewhere in output. |
| core/issue_test_workflow.py:153-205 | classify_test_execution | Classify candidate output | Correctly separates several infrastructure classes; depends on complete output/exit code. |
| core/issue_test_workflow.py:208-228 | classify_git_status | Parse status snapshot | A single snapshot is not enough unless tied to commit/session/phase. |
| core/issue_test_workflow.py:231-298 | classify_test_patch_paths | Audit changed files | Detects unsafe paths, too many files and non-test changes. |
| core/issue_test_workflow.py:301-329 | format_*_classification | Format classifier output | Useful compact annotations; not a workflow state machine. |
| core/task_input.py:5-16 | unresolved_template_marker | Detect unfilled placeholders | Correct guard for common template markers; cannot detect every vague task. |
| core/task_evidence.py:57-63 | _redact | Mask secrets | Common API-key formats only, not an absolute DLP guarantee. |
| core/task_evidence.py:64-69 | _terms | Search-term extraction | Used to retrieve relevant records. |
| core/task_evidence.py:71-100 | TaskEvidenceStore / _connect | SQLite evidence store | Local persistence, subject to bounded retention. |
| core/task_evidence.py:102-110 | _bounded | Limit result text | Emits truncation indicator. |
| core/task_evidence.py:111-145 | _insert | Store receipt row | Persists provenance/status/session fields. |
| core/task_evidence.py:146-167 | record_tool | Tool evidence | Records bounded tool output. |
| core/task_evidence.py:168-178 | record_turn | Chat evidence | Distinguishes chat from tool result. |
| core/task_evidence.py:179-212 | session_tool_results | Same-session receipts | Supplies the issue-test gate with earlier command results. |
| core/task_evidence.py:213-287 | retrieve_context | Recall relevant evidence | Adds context; does not reconstruct data never stored. |
| core/task_evidence.py:288-421 | export_bundle | Export report evidence | Includes hashes/truncation and same-session receipts. |

### 5.3 Tooling and Celesto modules

| File and lines | Symbol | What is actually implemented |
|---|---|---|
| tools/repo_tools.py:20-61 | _validate_clone_target | Allows public HTTPS github.com owner/repo and a new absolute destination outside project. |
| tools/repo_tools.py:64-151 | clone_public_repository | Proposal/approval-gated source-only clone on the host; no repository code or dependency installation. |
| tools/web_tools.py:255-270 | _github_issue_api_url | Map public issue URL to GitHub API resource. |
| tools/web_tools.py:273-284 | _github_api_get_json | HTTP GET with 12-second timeout. |
| tools/web_tools.py:286-335 | fetch_github_issue_content | Formats issue title/body/comments; caps content and returns textual error on failure. |
| tools/web_tools.py:350-434 | read_web_page | Routes issue URL to API helper; general web fetch is separate path. |
| tools/registry.py:215-233 | TOOL_FUNCTIONS | Registers host clone, Celesto controls and read_web_page. |
| tools/registry.py:235-309 | TOOL_ALIASES | Guest command synonyms map to run_sandbox_session_command; finite aliases are conveniences, not user requirements. |
| tools/registry.py:1251-1337 | OLLAMA_TOOLS_SCHEMA | Describes approval, session, command and status interfaces. |
| tools/registry.py:1678-1798 | execute_tool_normalized / execute_tool | Canonicalize name and wrap result/environment metadata. |
| tools/registry.py:1807-1950 | Tool-name sets / get_scoped_tools | Prompt keyword-based schema scoping; sandbox requests try to exclude host tools. |
| tools/sandbox_tools.py:65-260 | CelestoSandboxRunner | Older runner with setup, teardown, snapshots and command helper. |
| tools/sandbox_tools.py:261-406 | StepWorkflowEngine.execute_10_step_workflow | Generic workflow simulation, separate from issue-to-test workflow. |
| tools/sandbox_tools.py:407-446 | _celesto_readiness | Checks settings, SDK and Python; does not boot VM. |
| tools/sandbox_tools.py:450-579 | _SandboxSession / manager setup | In-memory session/task state, TTL, expiry and continuation context. |
| tools/sandbox_tools.py:580-674 | SandboxSessionManager.create | Exact approval, immutable task binding, one active session, real VM creation. |
| tools/sandbox_tools.py:675-703 | SandboxSessionManager.run | Execute one string command and return status/output/timings. |
| tools/sandbox_tools.py:704-734 | close / close_all | Explicit teardown and app-exit cleanup. |
| tools/sandbox_tools.py:737-749 | Session tool wrappers | Public create/run/close functions. |
| tools/sandbox_tools.py:752-843 | detonate_in_sandbox | Real single-command path or clearly labeled simulator. |
| tools/sandbox_tools.py:845-901 | get_sandbox_status | Readiness/registration snapshot; no VM creation. |
| tools/sandbox_tools.py:931-943 | run_sandboxed_workflow | Explicitly simulation-only workflow. |
| tools/sandbox_tools.py:991-1099 | ContainmentHarness / audit_sandbox_containment | Simulated containment report, not actual isolation proof. |
| spacev/fleet/celesto_engine.py:29-117 | CelestoSandboxInstance._initialize | Eagerly starts actual SDK computer; UUID name supplied in local path. |
| spacev/fleet/celesto_engine.py:119-149 | CelestoSandboxInstance.run | Audits and runs command once; captures output/exit and time. |
| spacev/fleet/celesto_engine.py:151-175 | snapshot / rollback | Calls SDK methods if available. |
| spacev/fleet/celesto_engine.py:177-197 | close | Cleanup state is deleted or cleanup_failed; records duration. |
| spacev/fleet/celesto_engine.py:206-221 | CelestoFleetManager | Manages instances separately from approved session manager. |

### 5.4 Tool boundary caveat

The issue-agent allowed-tools list includes read_web_page, clone_public_repository, list/read/search files, query_code_graph, sandbox status, create/run/close session. The graph later narrows to SANDBOX_TOOL_NAMES when the interpreted goal explicitly includes the sandbox domain or continuation context is present. Therefore:

- A sandbox-specific prompt is not sufficient by itself to prove tool delivery.
- Correct tool_domains and current sandbox context matter.
- A host-side clone tool exists and must not be used for the isolated checkout.
- During an active approved session, the graph permits only guest command and close; after a failed guest command, it permits close only.
- Current registry alias support helps when an LLM says “run guest command” or “command in VM”; the user should not have to know any internal function name.
- A runtime’s external tool manifest may differ from the project’s registry; get_sandbox_status explicitly warns that source registration does not prove per-request tool exposure.

## 6. Error and failure investigation

| Failure class | Concrete evidence from conversation | Confirmed interpretation | What it blocks | Correct engineering response |
|---|---|---|---|---|
| Git missing | Guest stderr: /bin/sh: git: not found; exit 127. | Git executable absent in that VM/path. | Clone step. | Record distro, check Git, ask approval before install, install only in that VM. |
| Git installed elsewhere | User-provided output reports apk installation and git version 2.43.7. | One specific session had Git. | Does not prove other VMs have Git. | Bind environment receipt to session ID and image. |
| Celesto name collision | Error: computer sbx-noether already exists; exit 1 before command output. | VM command did not reach guest; Git status unknown. | All guest operation in that attempt. | UUID naming exists in current local implementation; reproduce only with approved runtime check. |
| Clone timeout | Celesto said vsock run timed out after 30 seconds; exit 1. | Guest operation exceeded executor deadline; root cause not shown. | Checkout/source inspection. | Classify TIMEOUT; preserve output; never retry automatically. |
| Session expired/missing | Tool said session missing or expired. | That session ID could not be used at call time; exact reason not established by this response alone. | Continuation in that VM. | Persist task/session mapping, expose expiry receipt, require new approval for replacement. |
| Missing issue text | Some prompts contain a literal issue-text placeholder; a later user request prohibited fetch and body was not visible. | Issue content prerequisite absent in those turns. | Issue summary and expected symptom. | Placeholder guard is right; ask for issue text or fetch approval. |
| Pydantic errors | Logs: invalid JSON, missing objective, integer where entities require string. | Model output did not match schema in those turns. | Reliable structured routing. | Normalize known aliases/types, one constrained repair, then stop high-risk workflow on invalid contract. |
| Cloud DNS/TLS/reset/timeout | Logs show name resolution failure, TLS EOF, connection reset, read timeout to configured endpoint. | Model transport failed in those requests; network root cause varies/unknown. | Model reasoning/goal interpretation. | Typed transport status; bounded safe retry policy; surface local fallback and model identity. |
| Raw DSML output | User-visible response showed literal DSML invoke markup. | UI received protocol text rather than a normal completion in that turn. | Usable user report. | Normalize streaming/protocol output; suppress raw control tokens and summarize receipt. |
| Long task latency | One turn showed tools ~210 seconds, total ~255 seconds; VM creation/close also consumed time. | The receipts show accumulated time; they do not establish one cause for all delay. | User experience and context retention. | Show per-phase progress; use reusable session; cap overall deadline and report slow stage. |
| Incomplete inspection | User explicitly corrected the summary: test body captured; source inspection incomplete. | No evidence of full source trace in that attempt. | Credible test rationale. | Require named test/source receipt checklist before diff proposal. |
| No test diff in corrected run | User correction says no proposed diff was completed. | That run did not deliver the requested artifact. | Separate review/approval phase. | Do not infer from earlier unrelated assistant prose; regenerate from actual source evidence. |
| No test run | User correction says no tests were run. | No candidate test command/exit/output exists for that attempt. | Bug reproduction verdict. | Keep status NOT_RUN; never assign EXPECTED_BUG_FAILURE. |
| Grep returned 1 | User said one grep exited 1; later search only found references without surrounding source. | Search did not yield required context; exact root of that command depends on its arguments/output. | Source-path confirmation. | Stop on exact target missing; report exact command/output; do not broaden silently. |
| Overstated summary | User corrected prior completion claim. | Assistant report went beyond available receipts. | Trust and safe continuation. | Evidence-only renderer with receipt links and no implicit completion. |
| Cleanup differs by session | Some logs show deleted; others expired/missing; IDs differ. | Cleanup must be assessed per session. | Claiming all VMs are cleaned. | Report exact session ID, state and cleanup timing only from close receipt. |

### 6.1 Root-cause confidence

- **Confirmed:** the exact outputs above show Git missing in one guest, clone timeout in another, a name collision in a separate call, an expired/missing session in another call, and malformed goal output in several turns.
- **Confirmed from user correction:** the specified read-only #7639 run did not finish source inspection, did not produce a diff, and did not run tests.
- **Likely, not proven:** repeated context compression contributed to lost issue/test details and mistaken summaries.
- **Possible, not proven:** network/throughput contributed to the clone timeout; stale VM inventory contributed to the name collision.
- **Unknown:** whether DNS, GitHub rate limit, proxy or vsock caused the timeout; whether every external harness request received the project’s sandbox tools; why raw DSML reached the UI.
- **Not a bug proof:** missing Git, wrong environment, timeout, name collision, schema parse failure, unavailable session, no-match grep, or no test execution.

## 7. Actual execution and call graph

### 7.1 Current source-backed path

~~~mermaid
flowchart TD
    U[User prompt] --> R[SpaceVGraphEngine.run]
    R --> GI[_goal_interpreter_node]
    GI --> GUARD{Security and placeholder guards}
    GUARD -->|blocked or missing| STOP[Clarify and stop]
    GUARD -->|valid| URL[Parse GitHub issue URL]
    URL --> CTX[Load sandbox continuation and evidence recall]
    CTX --> GOAL[interpret_goal: cloud or Ollama JSON]
    GOAL --> VALID{GroundedGoal valid?}
    VALID -->|no| FALLBACK[Raw prompt fallback]
    VALID -->|yes| CONTRACT[Goal contract]
    FALLBACK --> PER
    CONTRACT --> PER[perception_guard]
    PER --> ROLE[classify_agent_role chooses ISSUE_TEST prompt]
    ROLE --> LLM[model_reasoning chooses tools and next action]
    LLM --> CALL{Tool call?}
    CALL -->|yes| TE[tool_executor]
    CALL -->|no| SYNTH[response_synthesizer]
    TE --> SCOPE{Sandbox domain/session checks}
    SCOPE -->|blocked| RECEIPT[Capture failure receipt]
    SCOPE -->|allowed| TOOL[execute_tool_normalized]
    TOOL --> ACTION[Web, host clone, or Celesto session action]
    ACTION --> NOTE[_issue_test_note classifiers]
    NOTE --> FAILED{Guest command failed?}
    FAILED -->|yes| CLOSE[Close active session and record cleanup]
    CLOSE --> SYNTH
    FAILED -->|no| LOOP[_route_after_tools]
    LOOP -->|work remains| LLM
    LOOP -->|finish| SYNTH
    SYNTH --> EXPORT[run evidence export and turn recording]
    EXPORT --> DONE[Final response]
~~~

### 7.2 Call graph boundaries

~~~mermaid
flowchart LR
    GRAPH[core/graph_engine.py] --> SWARM[core/swarm_orchestrator.py]
    GRAPH --> CONFIG[core/agent_configs.py]
    GRAPH --> GOAL[core/grounded_agent.py]
    GRAPH --> CLASS[core/issue_test_workflow.py]
    GRAPH --> EVIDENCE[core/task_evidence.py]
    GRAPH --> REGISTRY[tools/registry.py]
    REGISTRY --> WEB[tools/web_tools.py]
    REGISTRY --> CLONE[tools/repo_tools.py]
    REGISTRY --> SESSION[tools/sandbox_tools.py]
    SESSION --> ENGINE[spacev/fleet/celesto_engine.py]
    WEB --> API[GitHub REST API]
    CLONE --> HOST[Host-side Git process]
    ENGINE --> VM[Celesto SDK computer]
~~~

- Swarm role selection selects guidance; it does not itself perform steps.
- Goal interpretation selects structured intent; it is not the durable state store.
- Registry exposes both host clone and guest session tools; tool scoping must select the right trust boundary.
- Sandbox session manager owns guest lifecycle; the model supplies generic shell command strings.
- Classifiers annotate receipts; they cannot recover content that was never captured.
- Evidence recall helps follow-up; it cannot recreate evidence that was not stored.

### 7.3 Intended workflow

~~~mermaid
flowchart LR
    I1[1 Accept issue URL] --> I2[2 Capture and understand issue]
    I2 --> I3[3 Clone in approved isolated VM]
    I3 --> I4[4 Inspect relevant tests and code]
    I4 --> I5[5 Propose minimal test-only diff]
    I5 --> I6[6 Separate approval, baseline, candidate run]
    I6 --> I7[7 Evidence-backed report and cleanup]
~~~

### 7.4 Current behavior, including failure transitions

~~~mermaid
flowchart TD
    A[Generic graph receives prompt] --> B[URL / placeholder checks]
    B --> C[LLM goal extraction; may fall back to raw request]
    C --> D[ISSUE_TEST role prompt]
    D --> E[LLM selects next tool and command]
    E --> F{Correct sandbox domain and context?}
    F -->|yes| G[Approved reusable Celesto VM]
    F -->|no| H[Possible web/host tool route; later guard may block]
    G --> J[Generic guest command with executor timeout]
    J --> K{Success?}
    K -->|no| L[Close guest; stop; report error]
    K -->|yes| M[Store receipt and deterministic annotations]
    M --> N[LLM chooses next stage]
    N --> O[Classifier / test gate applies if relevant]
    O --> P[Model synthesizes final report]
    H --> P
    P --> Q{All required receipts present?}
    Q -->|not structurally enforced for every stage| R[Risk: incomplete report]
    Q -->|supported special gate| S[Evidence bundle]
~~~

### 7.5 Why this is not yet the full target

- There is no dedicated IssueWorkflowController whose only job is the seven ordered phases.
- The graph has generic nodes and loops; the model decides much of the sequence.
- Stage completion is not uniformly represented by typed states and required receipt IDs.
- Generic shell commands make the approved task description broader than a per-command capability policy.
- The test gate is strong relative to test execution, but the earlier stages (issue, clone, inspection, diff) are less mechanically validated.
- The final response can still be model-synthesized from incomplete context; evidence persistence reduces but does not eliminate this risk.

## 8. Target architecture and boundaries

~~~mermaid
flowchart LR
    USER[User / UI] --> CTRL[Deterministic IssueWorkflowController]
    CTRL --> FETCH[IssueRetriever]
    FETCH --> ISSUE[IssueRecord with source provenance]
    ISSUE --> ANALYST[LLM Issue Analyst]
    ANALYST --> UNDERSTANDING[Validated expected/actual/repro fields]
    CTRL --> SANDBOX[SandboxManager]
    SANDBOX --> VM[Approved disposable guest]
    VM --> REPO[Clone + commit pin]
    REPO --> INSPECT[RepositoryInspector]
    INSPECT --> MAP[Source/test evidence map]
    MAP --> PROPOSAL[TestProposalGenerator]
    PROPOSAL --> DIFF[Validated test-only diff + hash]
    DIFF --> APPROVE[Human diff approval]
    APPROVE --> BASELINE[Baseline runner]
    BASELINE --> CANDIDATE[Single approved candidate test]
    CANDIDATE --> CLASSIFY[Failure classifier]
    FETCH --> LEDGER[Evidence ledger]
    VM --> LEDGER
    REPO --> LEDGER
    INSPECT --> LEDGER
    DIFF --> LEDGER
    BASELINE --> LEDGER
    CANDIDATE --> LEDGER
    CLASSIFY --> LEDGER
    LEDGER --> REPORT[Evidence-bound report builder]
    REPORT --> USER
    CTRL --> CLEAN[Cleanup controller]
    CLEAN --> SANDBOX
~~~

### 8.1 Component contracts

| Component | Owns | Boundary |
|---|---|---|
| IssueWorkflowController | Phase enum, transitions, approvals, deadlines and stop policies. | LLM may recommend; controller validates/advances. |
| IssueRetriever | Public GitHub read or user-supplied body, issue identity, fetch timestamp and provenance. | Missing/failed issue is terminal for analysis. |
| LLM Issue Analyst | Summarize reporter claims and uncertainties from issue evidence. | Cannot invent expected contract or tool permission. |
| SandboxManager | Approval-bound VM session, network policy, lifecycle and cleanup. | No host fallback for guest task. |
| RepositoryInspector | Commit, clean status, target test, source symbols and environment receipt. | Read-only until explicit diff approval. |
| TestProposalGenerator | Minimal unified diff tied to captured file content and issue symptom. | No production-code edits. |
| ApprovalController | Exact diff hash and exact candidate command approval. | Approval is scoped and single-use. |
| BaselineRunner | Approved baseline test on pinned clean commit. | Failure means stop; no candidate inference. |
| CandidateRunner | One approved target test, one command, captured full receipt. | No silent retries or expanded test suite. |
| FailureClassifier | Expected symptom vs setup/infrastructure/unrelated failure. | Needs complete output, test identity and exit code. |
| EvidenceLedger | Append-only receipts, hashes, redaction, session/task identity and truncation. | Chat claims remain separate from tool facts. |
| ReportBuilder | Final tables, citations, status and unresolved items. | No completion unless invariants are satisfied. |
| CleanupController | Close/expire guest and persist cleanup result. | Cleanup failure leaves task incomplete. |

### 8.2 State machine

- INPUT_REQUIRED: URL or issue body missing.
- ISSUE_CAPTURED: source, title/body and normalized identity recorded.
- ISSUE_UNDERSTOOD: expected/actual/reproduction and uncertainty linked to issue text.
- SANDBOX_PROPOSED: exact task/actions held for approval.
- SANDBOX_READY: approved session and guest identity confirmed.
- ENVIRONMENT_READY: distro, Git, runtime and network facts captured.
- REPOSITORY_PINNED: clone succeeded, commit SHA and initial status recorded.
- INSPECTION_COMPLETE: all required test/source excerpts captured from pinned commit.
- DIFF_PROPOSED: minimal test-only unified diff validated and displayed.
- WAITING_DIFF_APPROVAL: no edit or run permitted.
- PATCH_APPLIED: exact approved diff applied; diff/status audited.
- BASELINE_VERIFIED: clean baseline passed under approved command.
- WAITING_TEST_APPROVAL: exact target test command awaiting separate approval.
- CANDIDATE_EXECUTED: exact command receipt has exit code/stdout/stderr.
- CLASSIFIED: verdict derived by deterministic classifier.
- CLEANUP_CONFIRMED: close receipt reports deleted or records failure.
- COMPLETE: all mandatory phase invariants pass.
- STOPPED / BLOCKED / INCONCLUSIVE: terminal state with reason and evidence IDs.

**Transition invariant:** prose from the model never advances workflow state. Only a successful, validated receipt advances a stage. A failed command stops dependent work. A timeout never authorizes retry.



## 9. Senior-engineering diagnosis and remedies

### 9.1 Highest-impact problems

| Problem | Why current behavior is insufficient | Recommended change | Existing work to retain | How to prove the fix |
|---|---|---|---|---|
| LLM controls stage sequence | The LLM can omit or reorder steps; generic graph loops do not guarantee seven-stage completion. | Add deterministic IssueWorkflowController with explicit state enum and transition validator. | LangGraph node model, ISSUE_TEST prompt, scratchpad for narrative planning. | Test every transition and prove skipped-stage commands are blocked. |
| Goal parse fallback preserves raw text | JSON error becomes a valid generic fallback goal, which can still proceed into action routing. | For issue workflow, malformed structured goal is a terminal parse error after one schema-repair attempt. | GroundedGoal alias/scalar normalization and raw prompt preservation for ordinary chat. | Feed malformed JSON; assert no tools are called and user sees a clear parse failure. |
| Role prompt mistaken for workflow | ISSUE_TEST_AGENT_CONFIG is strong guidance but prompts are not state gates. | Keep role as reasoning specialization; move permissions and phase transitions to controller. | AgentConfig and deterministic role classifier. | Remove/alter role phrase in prompt; core phase protections must still hold. |
| Host clone and guest clone coexist | clone_public_repository is explicitly host-side. A model can select it if sandbox domain is missing. | Issue controller exposes only guest clone command in the issue flow; use host clone only as a separately named, separately approved capability. | URL validation and source-only safeguards in repo_tools.py. | Assert issue task cannot dispatch clone_public_repository or host terminal tools. |
| Approval binds task but not every command | Session approval binds task description; run accepts a generic command string, not a plan step token. | Add typed actions or per-command capability/phase policy; validate requested path, URL, install, write, and test intent. | Exact approval phrase and immutable task binding. | Try an out-of-scope host command, write, install, or extra test; all must be blocked before Celesto. |
| In-memory session state expires | Reaper deletes expired session and manager has no cross-process persistence in inspected code. | Persist task/session status and cleanup receipts; on restart mark session state unknown/expired and require explicit recovery. | TTL/reaper and close_all. | Restart app with open VM; task resumes only if session is verifiably alive or stops cleanly. |
| Single 30-second command ceiling | Celesto engine invokes guest run with timeout=30; Git clone hit exactly that limit in a prior receipt. | Configure operation-specific deadlines, progress and cancellation; do not auto-retry. | Phase timing and explicit failure result. | Simulate slow clone; one timeout receipt, no duplicate command, session closes. |
| Inspection completeness is narrative | Model may say “inspected” after a grep or partial/truncated output. | Require an evidence manifest with each file, line range, command, exit code, truncation and commit. | TaskEvidenceStore, classifier, repository tools. | Missing source file receipt blocks DIFF_PROPOSED. |
| Diff is not mechanically tied to source | A plausible diff can be generated from memory or old test output. | Validate unified-diff context against source receipt hash; record diff hash; require exact human approval. | Prompt’s separate approval rule. | Alter source after proposal; patch application must reject stale context/hash. |
| Baseline and candidate evidence are complex | Gate parses shell commands and strings; text output can be truncated or malformed. | Use typed test-run receipt with command argv, cwd, commit, baseline/candidate phase, exit, duration and output hash. | Existing issue_test_workflow classifiers and graph gate. | Missing field or truncated output produces INCONCLUSIVE, never expected failure. |
| Final answer model can overclaim | Summarizer sees compressed context and may confuse chat claim with tool receipt. | Render status from ledger first; let model explain only verified structured fields. | Evidence store separates tool and chat sources, export hashes. | Adversarial transcript says success without receipt; report must say NOT VERIFIED. |
| API/network errors conflated with workflow progress | Textual “Failed:” responses can still be interpreted as ordinary content. | Normalize errors into ToolResult error codes (DNS, TLS, HTTP, timeout, auth, schema). | execute_tool_normalized and bounded model timeouts. | Inject each error class; issue/repo/test stages remain blocked. |
| Raw tool protocol can leak to UI | DSML appeared in one user-visible response. | Add output parser/sanitizer at streaming/render boundary; tool calls are UI events, not assistant prose. | Existing tool callbacks and response synthesizer. | Stream malformed and partial tool-call chunks; no control token reaches transcript. |
| Tool alias list is finite | Users use many natural synonyms; fixed alias list cannot cover all language. | Parse intent to canonical capability using registry metadata, then enforce policy by capability. | Existing aliases and schema descriptions. | Natural-language paraphrase suite maps safely to same canonical guest operation. |

### 9.2 What a senior engineer would do first

1. **Freeze the pilot’s scope.** One public issue, one repository, one target test, one disposable VM, no production fix.
2. **Make a task record.** Persist issue URL/body hash, repo URL, requested constraints, session ID, commit, current phase and evidence IDs.
3. **Make the workflow deterministic.** Use the seven-stage order as application state; use the LLM to interpret evidence, not decide whether evidence exists.
4. **Separate approval gates.** Approval A for exact VM/clone/read actions; Approval B for exact diff edit; Approval C for exact baseline/candidate test commands where not already authorized.
5. **Use typed receipts.** Every operation has action type, session, cwd, commit, command, exit code, output artifact, truncation, duration and status.
6. **Stop on prerequisite failure.** No clone after failed Git check; no inspection after clone failure; no diff after incomplete evidence; no classification without candidate output.
7. **Keep failures useful.** Return the exact underlying failure class, stage, command and next safe action; no fuzzy file-search remediation for a VM command failure.
8. **Make report generation mechanical.** Final answer derives completion markers from receipts and visibly lists missing items.
9. **Then integrate with broader Celesto capabilities.** Reuse snapshots and concurrency only after the single-session issue pilot is correct.

### 9.3 Keep, improve, and defer

- **Keep:** public issue URL validation; unresolved-placeholder guard; exact immutable sandbox approval; reusable session; UUID-backed local naming; strict no-host fallback during sandbox task; terminal guest failure cleanup; conservative test classifier; bounded/redacted evidence store.
- **Improve:** graph phase control; structured goal failure policy; typed tool receipts; issue/source provenance; per-command authorization; session persistence; timeout budgets; final report validation.
- **Do not claim yet:** end-to-end #7639 success; fully reliable source inspection; test reproduction; universal external tool availability; production-grade sandbox isolation based solely on simulation reports.
- **Defer:** five-way concurrent VMs, dependency-upgrade bisector, PR reviewer benchmarking, two-agent coding. Those expand scope before the single-task path is proven.
- **Avoid rebuild:** existing modules cover many primitives. The missing value is deterministic composition, not replacing every file.

## 10. Prioritized implementation roadmap

| Priority | Problem | Existing files | Improvement | Acceptance criteria |
|---|---|---|---|---|
| P0 | Completion claims not bound to receipts | graph_engine.py, task_evidence.py | Add IssueRun state and evidence-driven report builder. | Any missing mandatory receipt forces PARTIAL/INCONCLUSIVE. |
| P0 | Model chooses workflow progression | graph_engine.py, grounded_agent.py | Add deterministic phase controller; LLM only returns structured analysis/proposal. | Transition table has tests for all allowed/denied edges. |
| P0 | Issue text may be missing or malformed | web_tools.py, task_input.py, grounded_agent.py | Add IssueRecord validation and explicit fetch/user-provided source provenance. | No issue analysis occurs with placeholder, failed fetch, or mismatched issue URL. |
| P0 | Approved task can contain broad command strings | sandbox_tools.py, registry.py | Add per-phase command/action policy and command receipt schema. | Unauthorized install/write/test/host action rejected before execution. |
| P0 | Source-inspection completion is not checked | graph_engine.py, task_evidence.py | Require exact test/source excerpt manifest at pinned commit. | Missing one required excerpt blocks diff generation. |
| P1 | Clone timeout at 30 seconds | celesto_engine.py, sandbox_tools.py | Operation-specific deadlines and progress reporting; preserve no-retry default. | Timeout remains TIMEOUT with one execution and cleanup receipt. |
| P1 | Git/environment differences across VMs | issue_test_workflow.py, sandbox_tools.py | Environment preflight and session-pinned package/tool versions. | Every clone/test result identifies distro, architecture, Git and Python versions. |
| P1 | Session state is memory-only | sandbox_tools.py | Persist approval/session/run state and lifecycle transitions. | App restart does not silently lose or recreate an active session. |
| P1 | Diff may be stale or unsupported | graph_engine.py, agent_configs.py | Diff parser validates context and hashes against captured source; separate approval token. | Stale diff or production path is rejected before edit. |
| P1 | Baseline evidence must be parseable | issue_test_workflow.py, graph_engine.py | Typed baseline/candidate receipts with explicit phase IDs. | Classifier rejects missing exit/output/session/commit fields. |
| P1 | Tool response text can masquerade as success | registry.py, graph_engine.py | Normalize success/error result object before adding to model context. | Nonzero command cannot be represented as success by LLM prose. |
| P1 | Raw DSML reaches UI | graph_engine.py, UI streaming layer | Sanitize/parse protocol chunks and keep tool events separate. | No internal protocol token visible in transcript. |
| P2 | Alias coverage and routing ambiguity | registry.py, grounded_agent.py | Capability metadata and synonym-to-capability intent mapping. | Natural phrasing resolves to least-privileged canonical tool. |
| P2 | Evidence truncation hides relevant context | task_evidence.py, graph_engine.py | Store bounded artifact in file/object storage with summary pointer and full-output hash. | Truncated result is visibly marked and can be safely continued by targeted reads. |
| P2 | Long task UX is opaque | telemetry, graph_engine.py, sandbox_tools.py | Stream phase events and time budget/progress. | User sees phase, elapsed time, next gate and stop reason. |
| P3 | Multi-agent review and scaling | swarm_orchestrator.py | Add independent reviewer only after pilot passes; use read-only reviewer guest. | Reviewer reports independently sourced findings, not shared driver claims. |
| P3 | Concurrency / bisector / PR bot | sandbox fleet, snapshots | Defer until single-run correctness and resource limits are measured. | Separate benchmark proves queueing, isolation and cleanup at target concurrency. |

### 10.1 Dependency ordering

- P0 issue/run ledger precedes reliable cross-turn continuation.
- P0 deterministic controller precedes adding more agent roles.
- P0 approval/action policy precedes enabling writes or tests.
- P1 timeout and session persistence precede long-running clones.
- P1 baseline/candidate receipts precede any EXPECTED_BUG_FAILURE claim.
- P2 UX improvements follow correctness; they must not mask a failed phase.
- P3 concurrency depends on measured single-session correctness and Celesto capacity.

## 11. Verification plan and acceptance checklist

### 11.1 Stage-level verification

| Stage | Verification method | Required evidence | Pass rule |
|---|---|---|---|
| URL acceptance | Unit tests for URL parser and placeholder detector | Canonical issue/repo/number or explicit rejection | Only valid public issue accepted. |
| Issue reading | Mocked GitHub API tests plus one explicitly approved live read | Title/body, returned URL, timestamp, truncation | Identity matches requested issue and body is captured. |
| Sandbox | Manager unit tests with fake SDK plus one approved real smoke VM | Proposal ID, exact approval, session ID, guest identity, close receipt | No VM before approval; no host fallback; cleanup proven. |
| Clone | Guest command integration test | Git version, clone exit zero, commit SHA, clean status | Checkout exists in guest and same session. |
| Inspection | Fixture repository with known source/test symbols | Exact read receipts with line spans and commit | Every required target has successful nontruncated output. |
| Diff proposal | Unit tests of diff generation/validation | Unified diff, source hash, changed path list | Applies to captured source; test-only; human can review. |
| Baseline | Approved one-test baseline in guest | Exact command, exit zero, commit, output | Baseline passes before patch. |
| Candidate run | Approved exact command in same guest | Exit code/output and expected symptom | Only target test run; timeout is not retried. |
| Classification | Unit tests across failure fixtures | Classifier result and cited target block | EXPECTED_BUG_FAILURE only with target assertion and symptom. |
| Reporting | Contract tests with missing/contradictory receipts | Report status and evidence IDs | No unsupported “complete” claim. |
| Cleanup | Close success/failure/expiry tests | Session ID, final state and timing | VM state is deleted or cleanup failure is explicit. |

### 11.2 Failure-injection matrix

- Git command missing: stage becomes ENVIRONMENT_BLOCKED; no clone command is issued.
- Package manager unknown: stop and ask; do not guess apk/apt.
- GitHub DNS failure: issue/repository network error; no issue interpretation as success.
- Git clone timeout: stage TIMEOUT; no automatic retry or source-inspection continuation.
- Celesto name collision: no guest command is considered executed; session cleanup/state is reconciled.
- Session expired: old ID remains terminal; new session requires fresh approval.
- Grep no match: report exact target absent; no silent broad search.
- Truncated test excerpt: request a targeted read; do not build diff from incomplete body.
- Missing expected issue behavior: classify contract ambiguous; do not fabricate failure signal.
- Baseline failure: candidate is not run; report baseline/setup issue.
- Test import error: classify IMPORT_ERROR, not bug.
- Test discovery error: classify TEST_DISCOVERY_ERROR, not bug.
- Assertion with wrong symptom: ASSERTION_FAILURE_UNRELATED or INCONCLUSIVE.
- Expected target symptom: EXPECTED_BUG_FAILURE only if classifier associates it with the exact target test.
- Diff touches production: block edit/run and flag changed path.
- Cleanup error: terminal CLEANUP_FAILED; never state deleted.
- Model malformed JSON: one repair or stop; no action from raw fallback for gated issue workflow.
- Internal tool markup: UI sanitizer strips/protects control protocol from user-facing text.
- Evidence database unavailable: issue task stops or marks evidence persistence degraded; do not claim durable audit.

### 11.3 End-to-end acceptance checklist

- [ ] User supplies a valid GitHub issue URL or complete issue text.
- [ ] Issue content is captured with source provenance.
- [ ] Expected/actual behavior and reproduction are extracted with uncertainty.
- [ ] Repository URL is derived from validated issue identity.
- [ ] A VM proposal lists exact network, install, clone and read actions.
- [ ] No VM starts before exact approval.
- [ ] Approval resumes the same immutable task.
- [ ] Guest distro, Git and runtime versions are captured.
- [ ] Git installation is separately approved if required.
- [ ] Clone runs only inside approved guest.
- [ ] Commit SHA and initial git status are captured in that guest.
- [ ] Required test body, imports and fixture context are captured.
- [ ] Relevant production source path and caller/callee context are captured.
- [ ] Every inspection receipt has exit code and truncation state.
- [ ] Proposed diff is based on exact captured test text and issue behavior.
- [ ] Proposed diff touches test files only.
- [ ] User approves the exact diff before any edit.
- [ ] Patch applied to same commit/session and diff audit is clean.
- [ ] Baseline test command is approved and passes on clean tree.
- [ ] User approves exact candidate test command.
- [ ] Only that target test is executed.
- [ ] Output, exit code, commit, duration and session are recorded.
- [ ] Classifier links expected failure to target test’s output block.
- [ ] Infrastructure or unrelated failures remain non-bug classifications.
- [ ] Final report distinguishes proposal, execution and verified result.
- [ ] Evidence bundle includes source receipts and hashes/truncation.
- [ ] Celesto close receipt proves cleanup or reports cleanup failure.
- [ ] No host path/tool was used for guest-scoped actions.
- [ ] No unapproved dependency install, code edit, or expanded test run occurred.

## 12. Final technical assessment

### Answers to the audit questions

1. **What does SpaceV genuinely accomplish today?**  
   It has a structured graph, issue-role prompt, public issue URL/API helpers, approval-gated reusable Celesto sessions, command receipts, path/test classifiers, a same-session test gate, evidence recall/export, and cleanup logic.

2. **What is partial?**  
   The end-to-end sequencing, reliable issue context continuity, source inspection completeness, minimal diff generation, and evidence-bound final reporting.

3. **What is not demonstrated?**  
   A complete Requests #7639 source analysis, grounded test diff, passing baseline, candidate test run, expected-symptom failure, and one complete report with commit/diff/test/cleanup evidence.

4. **What is implemented but unreliable?**  
   Model-produced goal/tool sequencing and generic command execution are bounded by useful safeguards but still depend on context, correct domain selection, runtime availability, and the model choosing the right next step.

5. **Which failures are LLM-related?**  
   Malformed structured JSON and at least one overclaimed summary are observed. The exact root of every tool-choice or protocol-rendering error is not proven.

6. **Which failures are orchestration-related?**  
   Lack of a single explicit issue-phase state machine and reliance on prompt/context to remember progress are architectural gaps. These are supported by source structure and observed incomplete runs.

7. **Which failures are sandbox infrastructure?**  
   Git missing in a guest, VM name collision, clone timeout and expired/missing session are directly shown in logs. Their separate underlying causes should not be collapsed into one root cause.

8. **Which are tool integration?**  
   External request tool availability is not inspectable in status; guest command execution has a 30-second timeout; host clone and guest clone are separate tools; command tool is generic.

9. **Most important architectural problem?**  
   No deterministic, durable controller enforces the entire seven-stage workflow from verified evidence.

10. **What should be fixed first?**  
    Persisted IssueRun state, strict transition gates, typed receipts, and an evidence-derived final report.

11. **What should not be changed?**  
    Keep the user’s seven-step objective, the no-production-fix policy, exact approval gates, sandbox isolation, and conservative “expected symptom required” verdict rule.

12. **What must be demonstrated before production-ready?**  
    One complete issue with real issue evidence, same-guest clone/commit, complete read receipts, reviewable test-only diff, separate approval, passing baseline, target-specific expected failure, evidence bundle and cleanup receipt.

### Bottom-line status for the current Requests #7639 pilot

- Issue text: **not present in this audit’s source material**.
- Git installation: **reported successful in one separate VM session**.
- Clone: **reported successful in one separate attempt; another clone timed out**.
- Test body: **reported captured by user correction**.
- Full source inspection: **not completed in the corrected run**.
- Test diff: **not produced in the corrected run**.
- Test execution: **not run**.
- Bug reproduction: **not established**.
- VM cleanup: **proven only for sessions with explicit close receipts; cannot generalize across all session IDs**.
- Current application code changed by this audit: **no**.

## 13. Evidence ledger and limitations

### Source evidence

- Current line numbers and symbols were read from the files listed in Section 5.
- ARCHITECTURE.md describes the graph, repository clone, sandbox, and evidence modules, and warns that simulation reports are not live isolation proof.
- tools/repo_tools.py explicitly performs host-side cloning; tools/sandbox_tools.py exposes separate guest-session operations.
- ISSUE_TEST_AGENT_CONFIG explicitly requires issue grounding, baseline evidence, separate diff/test approval, no production fix, no retry on timeout, and conservative failure classification.
- issue_test_workflow.py contains deterministic helpers implementing several of those verdict/path checks.
- graph_engine.py contains issue prompt selection, sandbox routing, evidence notes, a test gate, failure cleanup and final evidence export.

### Runtime evidence supplied in conversation

- Git missing in one disposable Alpine guest: exit 127 and stderr “git: not found”.
- Git installation was later approved in a different live session; reported Git version was 2.43.7.
- A separate shallow clone was reported successful and the target test body was captured.
- User corrected the execution report: source inspection incomplete, no test diff in that run, and no tests run.
- Another command attempt failed before guest execution due to a Celesto name collision.
- Another clone command timed out after 30 seconds.
- Another session ID was reported missing/expired.
- Several LLM requests returned structured JSON validation errors.
- Several cloud transport logs report DNS, TLS, connection reset or read timeout failures.
- A UI transcript showed raw DSML tool-call markup.
- A prior close receipt explicitly reported one sandbox deleted; that evidence applies only to the named session.

### What this document does not claim

- It does not claim that issue #7639’s expected behavior is known.
- It does not claim that the current Requests checkout is available or that any source file from it was inspected in this run.
- It does not claim a proposed diff exists or that the test passes/fails.
- It does not claim all Celesto sessions were cleaned up.
- It does not claim external model tool payloads were inspected.
- It does not claim the proposed architecture or roadmap is already implemented.
- It does not claim test suites passed; no tests were run for this documentation task.

### Final recommendation

Complete the pilot in this order: recover the actual issue body or explicitly authorize a read-only fetch; submit one exact sandbox proposal; capture environment and Git; clone and pin commit/status; capture the named test, imports and relevant source excerpts; show a test-only diff; wait for separate approval; run a clean baseline; wait for exact candidate-run approval; execute only the target test; classify from raw output; export evidence; close the VM. If any stage fails, stop at that stage and report the exact receipt. That single disciplined run will show which remaining code change is truly necessary.

