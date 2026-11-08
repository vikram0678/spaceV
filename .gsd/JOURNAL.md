# JOURNAL.md

## 2026-10-22 — Project Initialization & Architecture Mapping
- Executed `/new-project` and `/map` workflows.
- Successfully indexed SpaceV architecture (`ui/`, `voice/`, `core/`, `tools/`).
- Mapped 41 passing unit tests.
- Initialized SPEC, ROADMAP (3 phases), and REQUIREMENTS baseline for Celesto hackathon delivery.

## 2026-11-04 — DAG Clarification Pause/Resume Validation
- Added an end-to-end DAG test for the user-input wait path in `tests/test_dag_workflow_engine.py`.
- The test asserts the question and `WAITING_INPUT` state persist, supplied arguments merge on resume, the workflow completes, and completed upstream work runs once.
- Focused validation output: `9 passed in 3.20s` (`python -m pytest -q tests/test_dag_workflow_engine.py`).
- The sandboxed pytest invocation stalled during Windows asyncio loop initialization before test collection; running the same focused suite outside the restricted sandbox completed successfully.
- Syntax compilation and `git diff --check` passed for the touched workflow/test files.

## 2026-11-04 — Goal-Aware Career Assistant Slice
- Added a local SQLite career assistant store for draft/active goals, dated plan tasks, user-confirmed progress, persistent reminders, and deduplicated opportunity links.
- Added tool registry/schema integration for goal creation, explicit activation, plan edits, manual progress, daily reviews, reminder CRUD/snooze, opportunity inbox, and confirmed data deletion.
- Added Qt-thread polling for persisted reminders and daily-review notifications while SpaceV runs; recurring reminders persist an IANA timezone.
- Harvested job links now enter the local inbox. User-provided internship/hackathon links can be tracked; no hackathon discovery feed or calendar OAuth integration is configured.
- Corrected application confirmation routes: no form integration means no claim of submission and no Applied status. User remains responsible for site submission until a verified permitted integration exists.
- Focused validation outputs: career assistant + career tools `32 passed in 5.08s`; reliability `13 passed in 2.28s`; DAG workflow `9 passed in 3.10s`.
- `py_compile` and targeted `git diff --check` completed successfully. No dependencies were added.

## 2026-11-04 — Windows Test and Runtime Compatibility
- Disabled the optional third-party semantic-router initialization on Windows, where its warmup deadlocks in this runtime; SpaceV uses its native sparse-vector fallback.
- Replaced `/tmp` assumptions in system execution and self-healing path selection with the platform temp directory; Windows `python3` resolution now uses the active interpreter.
- Updated tests that expected assistant prose to become tool calls, ran UI inspection in graph tests through mocks, and refreshed stale capability/interpreter expectations.
- Fixed a Chrome profile continuation label and corrected the Windows-specific assumptions in two tests (desktop-control guard and quoted Windows test path).
- Focused regression validation: `103 passed, 1 skipped`; Python compilation completed.
- Broad suite remains incomplete: event-loop setup hangs in this Windows environment, and the remaining sync-only run stalls later in another unmarked platform-dependent test. `git diff --check` reports pre-existing whitespace changes elsewhere in the dirty worktree.

## 2026-11-05 — Bounded Native OCR
- Added a single-worker, 3-second timeout and process-local circuit breaker around synchronous Windows OCR. A timed-out OCR request returns unavailable rather than blocking the calling UI/agent path; later calls skip native OCR, allowing geometric parsing fallback.
- Routed screen text lookup, screen text reading, and OmniParser OCR through the bounded helper.
- Added timeout/success unit tests. Focused OCR/visual tests: `9 passed`; core regression group: `105 passed, 1 skipped`; Python compilation passed.
- A broad run excluding asyncio-marked tests and ambient perception again reached 43% and reported two failures before stalling later; remaining full-suite coverage is unresolved.

## 2026-11-05 — Broad-Suite Blocker Follow-up
- Closed SQLite connections deterministically in RunLedgerService and the direct-connection test, fixing Windows temporary database cleanup failure.
- Restored ChatWindow.dock_near(point) behavior to position above the supplied icon and clamp within the active screen.
- Updated the WebRTC APM test to skip when the optional package is absent (requirements intentionally excludes it on Windows).
- Focused rerun: `2 passed, 1 skipped` for run-ledger cleanup, WebRTC optional dependency, and window docking.
- Broad suite still does not complete: after these fixes it reached 43% and showed one failure before stalling later. Remaining failure and stall need targeted isolation; the full suite is not green.

## 2026-11-05 — Broad Suite Failure Isolation
- Unified graph-engine security refusal wording and updated its test to assert current prompt safety invariants instead of obsolete persona branding.
- Identified the remaining broad-suite hang in `test_reports.py::test_contract_11_api_endpoints`: Starlette TestClient starts an AnyIO portal which blocks in Windows asyncio `socket.socketpair()` on this host. No production API defect was observed; the portal cannot start here.
- With asyncio-marked tests, ambient perception, and that API TestClient case excluded, broad validation completed: `497 passed, 2 skipped, 9 deselected in 45.12s`.
- Earlier focused OCR/core regression, run-ledger, docking, security, and prompt tests passed. Full unfiltered suite remains unverified because of the Windows socketpair limitation.

## 2026-11-05 — Deterministic Desktop and Timing Tests
- Removed the strict 280 ms DAG wall-clock assertion; the test already asserts interleaved start/end order, which directly proves concurrent fan-out and is robust to machine/UI load.
- Mocked the live screen capture in the browser-grounding unit test, whose `image=None` behavior intentionally inspects the real desktop and was picking up visible UI elements.
- The browser-grounding test passes in isolation (`1 passed`). The DAG test was not revalidated in this restricted runner because its asyncio loop stalled at socketpair setup; the user's normal Windows run previously passed all 10 asyncio tests before this assertion change.
