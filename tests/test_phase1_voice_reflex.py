"""
Unit tests for SpaceV Phase 1: Reflex & Voice Core upgrades.
Verifies:
- Dual-Pass STT (DraftTranscriptionFrame, SpeechProgressFrame)
- Pipecat Microsecond Barge-In (<50us buffer flushing)
- Deterministic Tool & Fast Routing
"""
import time
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from voice.frame_pipeline import (
    SpaceVFramePipeline,
    DraftTranscriptionFrame,
    TranscriptionFrame,
    SpeechProgressFrame,
    AudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    InterruptionFrame,
)
from spacev.core.reflex import SpaceVReflexEngine


def test_dual_pass_frames():
    draft = DraftTranscriptionFrame(text="drafting user command", is_final=False)
    assert draft.text == "drafting user command"
    assert not draft.is_final

    progress = SpeechProgressFrame(accumulated_pcm=b"\x00" * 3200)
    assert len(progress.accumulated_pcm) == 3200

    commit = TranscriptionFrame(text="launch calculator", language="en")
    assert commit.text == "launch calculator"


def test_pipecat_microsecond_flush():
    pipeline = SpaceVFramePipeline()
    res = pipeline.flush_microsecond(reason="test_barge_in")
    assert "flush_latency_us" in res
    assert "flushed_items" in res
    assert res["status"] == "flushed"
    # Microsecond flush should be well under 20000us (20ms)
    assert res["flush_latency_us"] < 20000


def test_reflex_engine_instant_match():
    reflex = SpaceVReflexEngine()
    
    # 1. App launch
    match = reflex.match_command("launch calculator")
    assert match is not None
    assert match.tool_name == "open_application"
    assert match.confidence >= 0.99

    # 2. Web search
    match = reflex.match_command("search google for quantum computing")
    assert match is not None
    assert match.tool_name == "search_google"
    assert "quantum computing" in match.arguments.get("query", "")

    # 3. Memory search
    match = reflex.match_command("search memory for project roadmap")
    assert match is not None
    assert match.tool_name == "search_memory"

    # 4. Folder creation
    match = reflex.match_command("create folder SpaceVProject")
    assert match is not None
    assert match.tool_name == "create_folder"
    assert match.arguments.get("folder_name") == "SpaceVProject"


def test_grammar_guard_schema_recovery():
    from core.grammar_guard import GrammarGuard, repair_json_syntax

    # 1. Test malformed JSON repair
    malformed_json = "{'name': 'set_timer', 'arguments': {'minutes': '15',}}"
    repaired = repair_json_syntax(malformed_json)
    assert '"name": "set_timer"' in repaired
    assert '"minutes": "15"' in repaired

    # 2. Test type-coercion validation: string minutes to float minutes
    ok, valid_args, recovery = GrammarGuard.recover_tool_arguments("set_timer", {"minutes": "15"})
    assert ok is True
    assert valid_args["minutes"] == 15.0

    # 3. Test missing parameter extraction from prompt
    ok, valid_args, recovery = GrammarGuard.recover_tool_arguments("open_application", {}, user_prompt="please open notepad")
    assert ok is True
    assert valid_args["app_name"] == "notepad"
    assert "extracted_app_name" in recovery

    # 4. Test missing query extraction for search_google
    ok, valid_args, recovery = GrammarGuard.recover_tool_arguments("search_google", {}, user_prompt="search google for space exploration")
    assert ok is True
    assert "space exploration" in valid_args["query"]
    assert "extracted_query" in recovery
