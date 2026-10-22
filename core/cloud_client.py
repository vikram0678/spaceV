"""
Universal Cloud Brain Client for SpaceV Cybernetic AI Agent.
Provides native OpenAI / OpenRouter API communication with streaming,
tool calling, and automatic rate-limit (HTTP 429) fallback to local Ollama.
"""
import json
import uuid
from collections.abc import Callable
from typing import Any

import requests

from config import (
    AUTONOMOUS_AGENT_MODEL,
    CODING_ENGINEER_MODEL,
    FAST_CHAT_CLOUD_MODEL,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    OLLAMA_BASE_URL,
    PRIMARY_MODEL,
)


class UniversalBrainClient:
    """
    High-performance, resilient OpenAI/OpenRouter client supporting
    both streaming token delivery and function calling with zero-downtime local fallback.
    """

    def __init__(
        self,
        base_url: str = LLM_BASE_URL,
        api_key: str = LLM_API_KEY,
        default_model: str = LLM_MODEL,
        fallback_base_url: str = OLLAMA_BASE_URL,
        fallback_model: str = PRIMARY_MODEL
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.fallback_base_url = fallback_base_url.rstrip("/")
        self.fallback_model = fallback_model
        self.last_used_provider = "cloud"

    def select_cloud_model(self, prompt: str, requires_tools: bool = False) -> str:
        """Dynamically routes between top-tier free OpenRouter models based on task intent."""
        prompt_lower = prompt.lower()
        if any(w in prompt_lower for w in ["code", "python", "script", "terminal", "debug", "test", "git", "bash", "compile"]):
            return CODING_ENGINEER_MODEL
        elif any(w in prompt_lower for w in ["screen", "click", "window", "gui", "see", "look", "desktop", "browser"]):
            return AUTONOMOUS_AGENT_MODEL
        elif not requires_tools and len(prompt.split()) < 15:
            return FAST_CHAT_CLOUD_MODEL
        return self.default_model

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://spacev.ai",
            "X-Title": "SpaceV Cybernetic Desktop Agent",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        token_callback: Callable[[str], None] | None = None,
        timeout: int = 60
    ) -> dict[str, Any]:
        """
        Executes a chat completion against OpenRouter/OpenAI API with live streaming
        and automatic 429 rate limit fallback to local Ollama.
        """
        active_model = model or self.default_model
        url = f"{self.base_url}/chat/completions"

        # Transform tools to OpenAI schema format if needed
        openai_tools = None
        if tools:
            openai_tools = []
            for t in tools:
                if "type" in t and t["type"] == "function":
                    openai_tools.append(t)
                elif "function" in t:
                    openai_tools.append({"type": "function", "function": t["function"]})
                else:
                    openai_tools.append({"type": "function", "function": t})

        # Transform messages to strict OpenAI/OpenRouter contract:
        # Every 'tool' role message MUST carry a non-empty string tool_call_id.
        sanitized_messages = []
        pending_tool_call_ids = []
        for msg in messages:
            msg_copy = dict(msg)
            role = msg_copy.get("role")
            if role == "assistant" and msg_copy.get("tool_calls"):
                fixed_calls = []
                for idx, tc in enumerate(msg_copy["tool_calls"]):
                    tc_copy = dict(tc)
                    tc_id = tc_copy.get("id") or f"call_{idx}_{uuid.uuid4().hex[:8]}"
                    tc_copy["id"] = tc_id
                    pending_tool_call_ids.append(tc_id)
                    fixed_calls.append(tc_copy)
                msg_copy["tool_calls"] = fixed_calls
            elif role == "tool":
                if not msg_copy.get("tool_call_id"):
                    if pending_tool_call_ids:
                        msg_copy["tool_call_id"] = pending_tool_call_ids.pop(0)
                    else:
                        msg_copy["tool_call_id"] = f"call_{uuid.uuid4().hex[:8]}"
            sanitized_messages.append(msg_copy)

        payload: dict[str, Any] = {
            "model": active_model,
            "messages": sanitized_messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # Streaming is only enabled when no tools are passed or when streaming tokens
        use_stream = bool(token_callback and not openai_tools)
        if use_stream:
            payload["stream"] = True
        if openai_tools:
            payload["tools"] = openai_tools
            payload["tool_choice"] = "auto"

        try:
            res = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                stream=use_stream,
                timeout=timeout
            )

            # Check for Rate Limit (429) or Service Overload (503) -> Failover
            if res.status_code in (429, 502, 503):
                print(f"[CLOUD-BRAIN] ⚠️ OpenRouter returned HTTP {res.status_code}. Initiating local Ollama fallback...")
                return self._fallback_to_ollama(messages, tools, token_callback)

            if res.status_code != 200:
                print(f"[CLOUD-BRAIN] ⚠️ Cloud API error ({res.status_code}): {res.text}. Failing over to Ollama...")
                return self._fallback_to_ollama(messages, tools, token_callback)

            self.last_used_provider = "cloud"

            if use_stream:
                full_content = ""
                for line in res.iter_lines():
                    if line:
                        line_text = line.decode("utf-8").strip()
                        if line_text.startswith("data: "):
                            data_str = line_text[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                token = delta.get("content", "")
                                if token:
                                    full_content += token
                                    if token_callback:
                                        token_callback(token)
                            except Exception:
                                continue
                return {
                    "role": "assistant",
                    "content": full_content,
                    "tool_calls": []
                }

            # Non-streaming JSON response
            data = res.json()
            choice = data.get("choices", [{}])[0].get("message", {})
            content = choice.get("content", "") or ""
            raw_tool_calls = choice.get("tool_calls", [])

            parsed_tool_calls = []
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"raw_input": args}
                parsed_tool_calls.append({
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": fn.get("name", ""),
                        "arguments": args
                    }
                })

            return {
                "role": "assistant",
                "content": content,
                "tool_calls": parsed_tool_calls
            }

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"[CLOUD-BRAIN] ⚠️ Connection to OpenRouter failed ({e!s}). Failing over to local Ollama...")
            return self._fallback_to_ollama(messages, tools, token_callback)
        except Exception as e:
            print(f"[CLOUD-BRAIN] ⚠️ Unexpected error: {e!s}. Failing over to local Ollama...")
            return self._fallback_to_ollama(messages, tools, token_callback)

    def _fallback_to_ollama(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        token_callback: Callable[[str], None] | None = None
    ) -> dict[str, Any]:
        """Local Ollama resilient fallback when cloud API is unavailable or rate limited."""
        self.last_used_provider = "ollama_fallback"
        url = f"{self.fallback_base_url}/api/chat"

        # Sanitize messages for Ollama native format (strip OpenAI-specific properties)
        ollama_messages = []
        for m in messages:
            role = m.get("role", "user")
            content = str(m.get("content", ""))
            cleaned = {"role": role, "content": content}
            if role == "assistant" and m.get("tool_calls"):
                cleaned_calls = []
                for tc in m["tool_calls"]:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            pass
                    cleaned_calls.append({"function": {"name": fn.get("name", ""), "arguments": args}})
                cleaned["tool_calls"] = cleaned_calls
            ollama_messages.append(cleaned)

        ollama_payload: dict[str, Any] = {
            "model": self.fallback_model,
            "messages": ollama_messages,
            "stream": bool(token_callback and not tools),
            "options": {"temperature": 0.2, "num_ctx": 2048}
        }
        if tools:
            clean_tools = []
            for t in tools:
                if "function" in t:
                    clean_tools.append(t)
                else:
                    clean_tools.append({"type": "function", "function": t})
            ollama_payload["tools"] = clean_tools

        try:
            if token_callback and not tools:
                res = requests.post(url, json=ollama_payload, stream=True, timeout=60)
                full_reply = ""
                for line in res.iter_lines():
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_reply += token
                            token_callback(token)
                return {"role": "assistant", "content": full_reply, "tool_calls": []}

            res = requests.post(url, json=ollama_payload, timeout=60)
            if res.status_code == 200:
                data = res.json()
                msg = data.get("message", {})
                return {
                    "role": "assistant",
                    "content": msg.get("content", ""),
                    "tool_calls": msg.get("tool_calls", [])
                }
            return {
                "role": "assistant",
                "content": f"[Ollama Error {res.status_code}]: {res.text}",
                "tool_calls": []
            }
        except Exception as err:
            return {
                "role": "assistant",
                "content": f"Both Cloud and Local LLMs were unreachable. Error: {err!s}",
                "tool_calls": []
            }
