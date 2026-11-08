"""Focused regression tests for bounded structured-goal recovery."""

from types import SimpleNamespace
from unittest.mock import Mock

from core.grounded_agent import GroundedGoal, goal_interpretation_requires_clarification, interpret_goal


VALID_GOAL = (
    '{"objective":"Inspect the supplied issue","steps":[],"success_criteria":[],"'
    'entities":{},"constraints":["Do not fetch the issue"],"tool_domains":["sandbox"],'
    '"requires_action":true,"confidence":0.9}'
)


class _Response:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": self.content}}


def test_malformed_goal_gets_exactly_one_schema_preserving_repair(monkeypatch):
    prompt = "Inspect issue #7639. Do not fetch it."
    post = Mock(side_effect=[_Response('{"objective":"Inspect issue'), _Response(VALID_GOAL)])
    monkeypatch.setattr("core.grounded_agent.requests.post", post)
    agent = SimpleNamespace(provider="ollama", model="test-model")

    goal, source = interpret_goal(prompt, agent, "http://localhost:11434", 2048)

    assert goal.objective == "Inspect the supplied issue"
    assert source == "model_repaired"
    assert post.call_count == 2
    first_payload = post.call_args_list[0].kwargs["json"]
    repair_payload = post.call_args_list[1].kwargs["json"]
    assert first_payload["format"]["properties"]
    assert repair_payload["format"] == first_payload["format"]
    assert any(message.get("content") == prompt for message in repair_payload["messages"])
    assert "Preserve the original user request and every constraint" in repair_payload["messages"][-1]["content"]


def test_goal_repair_is_bounded_and_falls_back_as_unstructured(monkeypatch):
    prompt = "Inspect issue #7639. Do not fetch it."
    post = Mock(side_effect=[_Response('{"objective":"partial'), _Response('{"objective":')])
    monkeypatch.setattr("core.grounded_agent.requests.post", post)
    agent = SimpleNamespace(provider="ollama", model="test-model")

    goal, source = interpret_goal(prompt, agent, "http://localhost:11434", 2048)

    assert isinstance(goal, GroundedGoal)
    assert goal.objective == prompt
    assert source == "raw_request_fallback_unstructured"
    assert post.call_count == 2
    assert goal_interpretation_requires_clarification(source) is True
    assert goal_interpretation_requires_clarification("model_repaired") is False


def test_cloud_goal_prompt_contains_schema_and_valid_goal_needs_one_call():
    class FakeCloudClient:
        def __init__(self):
            self.messages = None

        def select_cloud_model(self, _prompt, requires_tools=False):
            return "test-cloud-model"

        def chat(self, messages, **_kwargs):
            self.messages = messages
            return {"content": VALID_GOAL}

    client = FakeCloudClient()
    agent = SimpleNamespace(provider="openai", cloud_client=client)

    goal, source = interpret_goal("Inspect issue #7639", agent, "http://unused", 2048)

    assert goal.objective == "Inspect the supplied issue"
    assert source == "model"
    assert "JSON Schema" in client.messages[0]["content"]
    assert "objective" in client.messages[0]["content"]
