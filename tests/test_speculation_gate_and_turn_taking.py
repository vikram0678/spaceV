"""
Unit and Integration Tests for SpeculationGate and Speculative Turn-Taking in AgentWorker.
Inspired by Pipecat AI (eto/pipecat/src/pipecat/turns/speculation_gate.py).
"""
from unittest.mock import MagicMock, patch

from core.agent_worker import AgentWorker, SpeculationGate, SpeculationState


def test_speculation_gate_initial_state():
    gate_normal = SpeculationGate(is_speculative=False)
    assert gate_normal.state == SpeculationState.OPEN
    assert not gate_normal.is_holding
    assert not gate_normal.is_speculating

    gate_spec = SpeculationGate(is_speculative=True)
    assert gate_spec.state == SpeculationState.HOLDING
    assert gate_spec.is_holding
    assert gate_spec.is_speculating


def test_speculation_gate_hold_and_confirm():
    gate = SpeculationGate(is_speculative=True)
    gate.hold_token("Hello")
    gate.hold_token(" ")
    gate.hold_token("World")

    assert gate.is_holding

    released = gate.confirm()
    assert released == ["Hello", " ", "World"]
    assert gate.state == SpeculationState.OPEN
    assert not gate.is_holding
    assert not gate.is_speculating


def test_speculation_gate_cancel_drops_tokens():
    gate = SpeculationGate(is_speculative=True)
    gate.hold_token("Draft")
    gate.hold_token(" response")

    gate.cancel()
    assert gate.state == SpeculationState.DROPPING
    assert not gate.is_holding

    # Confirming after cancel returns nothing
    assert gate.confirm() == []


def test_agent_worker_speculative_holding_and_confirmation():
    mock_agent = MagicMock()
    worker = AgentWorker(mock_agent, "What is the weather?", is_speculative=True)

    received_tokens = []
    worker.token_received.connect(lambda t: received_tokens.append(t))

    # Mock GraphEngine.run to stream tokens
    def mock_run(prompt, tool_callback=None, token_callback=None):
        if token_callback:
            token_callback("The ")
            token_callback("weather ")
            token_callback("is ")
            token_callback("sunny.")
        return "The weather is sunny."

    with patch.object(worker.graph_engine, "run", side_effect=mock_run):
        worker.run()

        # While speculative and unconfirmed, tokens must NOT be emitted to UI
        assert received_tokens == []
        assert worker.speculation_gate.is_holding
        assert worker._pending_response == "The weather is sunny."

        # Now simulate turn confirmation
        worker.confirm_speculation()

        # All tokens must now be emitted
        assert received_tokens == ["The ", "weather ", "is ", "sunny."]
        assert not worker.speculation_gate.is_holding


def test_agent_worker_speculative_cancellation():
    mock_agent = MagicMock()
    worker = AgentWorker(mock_agent, "Partial command...", is_speculative=True)

    received_tokens = []
    worker.token_received.connect(lambda t: received_tokens.append(t))

    def mock_run(prompt, tool_callback=None, token_callback=None):
        if token_callback:
            token_callback("Speculative ")
            token_callback("words")
        return "Speculative words"

    with patch.object(worker.graph_engine, "run", side_effect=mock_run):
        worker.run()
        assert received_tokens == []

        # Cancel speculation because user resumed speaking
        worker.cancel_speculation()
        assert worker._is_aborted
        assert worker.speculation_gate.state == SpeculationState.DROPPING
        assert received_tokens == []


def test_agent_worker_backward_compatibility_non_speculative():
    mock_agent = MagicMock()
    # Default is_speculative=False
    worker = AgentWorker(mock_agent, "Tell me a joke")

    received_tokens = []
    worker.token_received.connect(lambda t: received_tokens.append(t))

    def mock_run(prompt, tool_callback=None, token_callback=None):
        if token_callback:
            token_callback("Why ")
            token_callback("did ")
            token_callback("the ")
            token_callback("chicken...")
        return "Why did the chicken..."

    with patch.object(worker.graph_engine, "run", side_effect=mock_run):
        worker.run()
        # Normal execution immediately emits tokens
        assert received_tokens == ["Why ", "did ", "the ", "chicken..."]
        assert not worker.speculation_gate.is_holding
