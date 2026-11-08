"""
Universal Cloud Brain Client for SpaceV Cybernetic AI Agent.
Supports one configured OpenAI-compatible endpoint or Anthropic Messages API,
including streaming and tool calling.
"""

import json
import os
import time
import uuid
from collections.abc import Callable
from typing import Any

import requests

from config import (
    BASE_DIR,
    CEREBRAS_API_KEY,
    CEREBRAS_API_KEYS,
    CEREBRAS_BASE_URL,
    CEREBRAS_FAST_MODEL,
    CEREBRAS_MODEL,
    GEMINI_API_KEY,
    GEMINI_API_KEYS,
    GEMINI_BASE_URL,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_API_KEYS,
    GROQ_BASE_URL,
    GROQ_FAST_MODEL,
    GROQ_MODEL,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_PROVIDER,
    MISTRAL_API_KEY,
    MISTRAL_API_KEYS,
    MISTRAL_BASE_URL,
    MISTRAL_MODEL,
    MISTRAL_SMALL_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_NUM_CTX,
    OPENROUTER_API_KEY,
    OPENROUTER_API_KEYS,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    PRIMARY_MODEL,
    SAMBANOVA_API_KEY,
    SAMBANOVA_BASE_URL,
    SAMBANOVA_MODEL,
    ZAI_API_KEY,
    ZAI_BASE_URL,
    ZAI_MODEL,
)
from core.context_compressor import compress_tool_output
from core.rate_limiter import rate_limiter
from core.token_optimizer import token_optimizer


class UniversalBrainClient:
    """
    Single-endpoint cloud client supporting OpenAI-compatible APIs and Anthropic.
    """

    def __init__(
        self,
        base_url: str = LLM_BASE_URL,
        api_key: str = LLM_API_KEY,
        groq_api_key_2: str = "",
        default_model: str = LLM_MODEL,
        fallback_base_url: str = OLLAMA_BASE_URL,
        fallback_model: str = PRIMARY_MODEL,
        gemini_api_key: str = GEMINI_API_KEY,
        gemini_base_url: str = GEMINI_BASE_URL,
        gemini_model: str = GEMINI_MODEL,
        sambanova_api_key: str = SAMBANOVA_API_KEY,
        sambanova_base_url: str = SAMBANOVA_BASE_URL,
        sambanova_model: str = SAMBANOVA_MODEL,
        cerebras_api_key: str = CEREBRAS_API_KEY,
        cerebras_base_url: str = CEREBRAS_BASE_URL,
        cerebras_model: str = CEREBRAS_MODEL,
        routing_mode: str = "direct",
        provider: str = LLM_PROVIDER,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.fallback_base_url = fallback_base_url.rstrip("/")
        self.fallback_model = fallback_model
        self.gemini_api_key = gemini_api_key
        self.gemini_base_url = gemini_base_url.rstrip("/")
        self.gemini_model = gemini_model
        self.sambanova_api_key = sambanova_api_key
        self.sambanova_base_url = sambanova_base_url.rstrip("/")
        self.sambanova_model = sambanova_model
        self.cerebras_api_key = cerebras_api_key
        self.cerebras_base_url = cerebras_base_url.rstrip("/")
        self.cerebras_model = cerebras_model
        self.routing_mode = routing_mode
        self.provider = provider
        self.last_used_provider = "cloud"
        self.disabled_providers: set[str] = set()

        # Multi-Account Key Pools
        self.groq_keys = list(GROQ_API_KEYS)
        if api_key and api_key not in self.groq_keys:
            self.groq_keys.insert(0, api_key)

        self.cerebras_keys = list(CEREBRAS_API_KEYS)
        if cerebras_api_key and cerebras_api_key not in self.cerebras_keys:
            self.cerebras_keys.insert(0, cerebras_api_key)

        self.gemini_keys = list(GEMINI_API_KEYS)
        if gemini_api_key and gemini_api_key not in self.gemini_keys:
            self.gemini_keys.insert(0, gemini_api_key)

        self.mistral_keys = list(MISTRAL_API_KEYS)
        if MISTRAL_API_KEY and MISTRAL_API_KEY not in self.mistral_keys:
            self.mistral_keys.insert(0, MISTRAL_API_KEY)

        self.openrouter_keys = list(OPENROUTER_API_KEYS)
        if OPENROUTER_API_KEY and OPENROUTER_API_KEY not in self.openrouter_keys:
            self.openrouter_keys.insert(0, OPENROUTER_API_KEY)

        # Pre-emptive round-robin key rotation indices (ensures turns alternate accounts)
        self._rotation_indices: dict[str, int] = {
            "groq": 0,
            "cerebras": 0,
            "gemini": 0,
            "mistral": 0,
            "openrouter": 0,
        }

        # Persistent Cooldown State File
        self._cooldown_file = BASE_DIR / ".gateway_cooldowns.json"
        self._cooldowns: dict[str, float] = self._load_cooldowns()

    def _load_cooldowns(self) -> dict[str, float]:
        """Load persistent circuit-breaker cooldown timestamps from disk."""
        if "PYTEST_CURRENT_TEST" in os.environ:
            return {}
        if self._cooldown_file.exists():
            try:
                data = json.loads(self._cooldown_file.read_text(encoding="utf-8"))
                now = time.time()
                # Prune expired cooldowns
                return {k: float(v) for k, v in data.items() if float(v) > now}
            except Exception:
                pass
        return {}

    def _save_cooldown(self, key_or_provider: str, duration_sec: float) -> None:
        """Record a provider/key cooldown duration and persist to disk."""
        now = time.time()
        self._cooldowns[key_or_provider] = now + duration_sec
        if "PYTEST_CURRENT_TEST" in os.environ:
            return
        try:
            self._cooldown_file.write_text(json.dumps(self._cooldowns), encoding="utf-8")
        except Exception:
            pass

    def is_in_cooldown(self, key_or_provider: str) -> bool:
        """Check if a key or provider is currently within its circuit-breaker cooldown window."""
        cooldown_until = self._cooldowns.get(key_or_provider, 0.0)
        return time.time() < cooldown_until

    def _build_provider_pipeline(
        self,
        prompt: str = "",
        requested_model: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        pipeline = []
        prompt_lower = prompt.lower()

        # Pre-Flight Token Estimation: includes message history AND tool schemas
        total_msg_chars = sum(len(str(m.get("content", ""))) for m in (messages or []))
        tools_chars = len(json.dumps(tools)) if tools else 0
        estimated_tokens = (total_msg_chars + tools_chars or len(prompt)) // 4

        needs_gemini_first = (
            any(w in prompt_lower for w in ["screenshot", "screen", "look at", "see my desktop", "image", "vision"])
            or len(prompt) > 18000
            or total_msg_chars > 18000
            or estimated_tokens > 4800
        )

        # 1. DIRECT BYOK PAID MODE: bypass free mesh if direct mode is active (unless running unit tests with mock keys)
        if self.routing_mode == "direct" and not (
            self.api_key.startswith("mock_") or self.api_key.startswith("gsk_mock")
        ):
            from core.virtual_router import virtual_router

            direct_model = requested_model or self.default_model
            # If a virtual alias like spacev/auto is requested in direct mode, resolve it or keep default
            if direct_model and virtual_router.is_virtual_alias(direct_model):
                direct_model = self.default_model
            pipeline.append(
                {
                    "name": "Direct Paid API",
                    "base_url": self.base_url,
                    "api_key": self.api_key,
                    "model": direct_model,
                }
            )
            return pipeline

        # Track families rotated during this turn to advance each family once per request
        rotated_families: set[str] = set()

        # Helper to get active keys with pre-emptive round-robin rotation
        def get_pool_candidates(
            name_prefix: str, keys: list[str], base_url: str, model_id: str, family: str
        ) -> list[dict[str, Any]]:
            if not keys:
                return []
            valid_keys = [k for k in keys if k and not self.is_in_cooldown(k)]
            if not valid_keys:
                return []

            # Pre-emptive round-robin: shift order once per turn so consecutive turns alternate accounts
            start_idx = self._rotation_indices.get(family, 0) % len(valid_keys)
            if family not in rotated_families:
                self._rotation_indices[family] = (start_idx + 1) % len(valid_keys)
                rotated_families.add(family)
            ordered_keys = valid_keys[start_idx:] + valid_keys[:start_idx]

            prefix = name_prefix
            if prefix == "Groq" and "groq.com" not in base_url:
                prefix = "Cloud API"

            candidates = []
            for i, k in enumerate(ordered_keys, 1):
                # In mesh mode, each provider must strictly use its own model ID.
                # requested_model is only used when running in direct BYOK mode.
                target_model = requested_model if (self.routing_mode == "direct" and requested_model) else model_id
                candidates.append(
                    {
                        "name": prefix if i == 1 else f"{prefix} Pool {i}",
                        "base_url": base_url,
                        "api_key": k,
                        "model": target_model,
                        "family": family,
                    }
                )
            return candidates

        cerebras_candidates = get_pool_candidates(
            "Cerebras", self.cerebras_keys, self.cerebras_base_url, self.cerebras_model, "cerebras"
        )
        cerebras_fast_candidates = get_pool_candidates(
            "Cerebras Fast", self.cerebras_keys, self.cerebras_base_url, CEREBRAS_FAST_MODEL, "cerebras"
        )
        groq_base = GROQ_BASE_URL or "https://api.groq.com/openai/v1"
        groq_candidates = get_pool_candidates("Groq", self.groq_keys, groq_base, GROQ_MODEL, "groq")
        mistral_candidates = get_pool_candidates(
            "Mistral", self.mistral_keys, MISTRAL_BASE_URL, MISTRAL_MODEL, "mistral"
        )
        mistral_small_candidates = get_pool_candidates(
            "Mistral Small", self.mistral_keys, MISTRAL_BASE_URL, MISTRAL_SMALL_MODEL, "mistral"
        )
        gemini_candidates = get_pool_candidates(
            "Google Gemini", self.gemini_keys, self.gemini_base_url, self.gemini_model, "gemini"
        )

        # Fast candidates for Groq
        groq_fast_candidates = get_pool_candidates("Groq Fast", self.groq_keys, groq_base, GROQ_FAST_MODEL, "groq")
        sambanova_provider = {
            "name": "SambaNova",
            "base_url": self.sambanova_base_url,
            "api_key": self.sambanova_api_key,
            "model": self.sambanova_model,
            "family": "sambanova",
        }

        openrouter_candidates = get_pool_candidates(
            "OpenRouter", self.openrouter_keys, OPENROUTER_BASE_URL, OPENROUTER_MODEL, "openrouter"
        )

        zai_provider = {
            "name": "ZAI Direct",
            "base_url": ZAI_BASE_URL,
            "api_key": ZAI_API_KEY,
            "model": ZAI_MODEL,
            "family": "zai",
        }

        from core.virtual_router import virtual_router

        model_name = requested_model or self.default_model
        resolved_alias = (
            virtual_router.resolve_alias(model_name, prompt=prompt, tools=tools)
            if virtual_router.is_virtual_alias(model_name)
            else None
        )

        if resolved_alias == "spacev/fast":
            # Priority: Cerebras Fast / Groq Fast -> Full models -> Others
            pipeline.extend(cerebras_fast_candidates)
            pipeline.extend(groq_fast_candidates)
            pipeline.extend(groq_candidates)
            pipeline.extend(cerebras_candidates)
            pipeline.extend(mistral_small_candidates)
            pipeline.extend(gemini_candidates)
        elif resolved_alias == "spacev/coder":
            # Priority: Codestral / Mistral -> Groq -> Cerebras -> SambaNova
            pipeline.extend(mistral_candidates)
            pipeline.extend(groq_candidates)
            pipeline.extend(cerebras_candidates)
            pipeline.extend(mistral_small_candidates)
            if self.sambanova_api_key:
                pipeline.append(sambanova_provider)
            pipeline.extend(gemini_candidates)
        elif resolved_alias == "spacev/smart" or needs_gemini_first:
            pipeline.extend(gemini_candidates)
            pipeline.extend(cerebras_candidates)
            pipeline.extend(groq_candidates)
            pipeline.extend(mistral_candidates)
            if self.sambanova_api_key:
                pipeline.append(sambanova_provider)
            pipeline.extend(openrouter_candidates)
            if ZAI_API_KEY:
                pipeline.append(zai_provider)
        else:
            # Low latency code/tool calling order: Groq (ultra-low latency) -> Cerebras (1,800 tok/s) -> Mistral -> 8B Fallbacks -> Gemini -> OpenRouter/ZAI
            pipeline.extend(groq_candidates)
            pipeline.extend(cerebras_candidates)
            pipeline.extend(mistral_candidates)
            pipeline.extend(groq_fast_candidates)
            pipeline.extend(cerebras_fast_candidates)
            pipeline.extend(mistral_small_candidates)
            pipeline.extend(gemini_candidates)
            if self.sambanova_api_key:
                pipeline.append(sambanova_provider)
            pipeline.extend(openrouter_candidates)
            if ZAI_API_KEY:
                pipeline.append(zai_provider)

        pipeline = [
            p
            for p in pipeline
            if p["name"] not in self.disabled_providers
            and not self.is_in_cooldown(p.get("api_key", ""))
            and not self.is_in_cooldown(p["name"])
        ]

        if not pipeline:
            pipeline.append(
                {
                    "name": "Cloud API",
                    "base_url": self.base_url,
                    "api_key": self.api_key,
                    "model": requested_model or self.default_model,
                    "family": "groq",
                }
            )

        return pipeline

    def select_cloud_model(self, prompt: str = "", requires_tools: bool = False) -> str:
        """Use only the model explicitly configured by the user or endpoint default."""
        return self.default_model

    def _get_headers(self, api_key: str | None = None) -> dict[str, str]:
        key = api_key if api_key is not None else self.api_key
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://spacev.ai",
            "X-Title": "SpaceV Cybernetic Desktop Agent",
        }
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def sanitize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Transform messages to strict OpenAI/OpenRouter contract:
        - Every 'assistant' message with tool_calls is strictly preserved with valid JSON string arguments.
        - Every 'tool' role message carries a non-empty string tool_call_id and name.
        """
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
                    if "type" not in tc_copy:
                        tc_copy["type"] = "function"
                    func = dict(tc_copy.get("function", {}))
                    args = func.get("arguments", "{}")
                    if isinstance(args, (dict, list)):
                        func["arguments"] = json.dumps(args)
                    elif not isinstance(args, str):
                        func["arguments"] = str(args)
                    tc_copy["function"] = func
                    pending_tool_call_ids.append(tc_id)
                    fixed_calls.append(tc_copy)
                msg_copy["tool_calls"] = fixed_calls
                if msg_copy.get("content") is None:
                    msg_copy["content"] = ""
                sanitized_messages.append(msg_copy)
            elif role == "tool":
                if not msg_copy.get("tool_call_id"):
                    if pending_tool_call_ids:
                        msg_copy["tool_call_id"] = pending_tool_call_ids.pop(0)
                    else:
                        msg_copy["tool_call_id"] = f"call_{uuid.uuid4().hex[:8]}"
                if not msg_copy.get("name"):
                    target_id = msg_copy.get("tool_call_id")
                    matched_name = ""
                    for prev_m in reversed(sanitized_messages):
                        if prev_m.get("role") == "assistant" and prev_m.get("tool_calls"):
                            for tc in prev_m["tool_calls"]:
                                if tc.get("id") == target_id:
                                    matched_name = tc.get("function", {}).get("name", "")
                                    break
                            if matched_name:
                                break
                    msg_copy["name"] = matched_name or "tool_result"
                if not isinstance(msg_copy.get("content"), str):
                    content_val = msg_copy.get("content", "")
                    msg_copy["content"] = (
                        json.dumps(content_val) if isinstance(content_val, (dict, list)) else str(content_val)
                    )
                sanitized_messages.append(msg_copy)
            else:
                sanitized_messages.append(msg_copy)
        return sanitized_messages

    def _chat_anthropic(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
        temperature: float,
        max_tokens: int,
        token_callback: Callable[[str], None] | None,
        timeout: int,
    ) -> dict[str, Any]:
        """Call Anthropic's Messages API and normalize its response for SpaceV."""
        if not model:
            return {
                "role": "assistant",
                "content": "LLM_MODEL is required when LLM_PROVIDER=anthropic. Set the Claude model name in .env.",
                "tool_calls": [],
            }

        system_parts: list[str] = []
        anthropic_messages: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role == "system":
                if content:
                    system_parts.append(str(content))
            elif role == "tool":
                result_block = {
                    "type": "tool_result",
                    "tool_use_id": str(message.get("tool_call_id", "")),
                    "content": str(content or ""),
                }
                if anthropic_messages and anthropic_messages[-1].get("role") == "user":
                    existing = anthropic_messages[-1]["content"]
                    if isinstance(existing, list):
                        existing.append(result_block)
                    else:
                        anthropic_messages[-1]["content"] = [
                            {"type": "text", "text": str(existing)}, result_block
                        ]
                else:
                    anthropic_messages.append({"role": "user", "content": [result_block]})
            elif role in ("user", "assistant"):
                blocks: list[dict[str, Any]] = []
                if content:
                    blocks.append({"type": "text", "text": str(content)})
                if role == "assistant":
                    for tool_call in message.get("tool_calls", []) or []:
                        function = tool_call.get("function", {})
                        arguments = function.get("arguments", {})
                        if isinstance(arguments, str):
                            try:
                                arguments = json.loads(arguments)
                            except json.JSONDecodeError:
                                arguments = {"raw_input": arguments}
                        blocks.append(
                            {
                                "type": "tool_use",
                                "id": str(tool_call.get("id") or f"call_{uuid.uuid4().hex[:8]}"),
                                "name": str(function.get("name", "")),
                                "input": arguments if isinstance(arguments, dict) else {"value": arguments},
                            }
                        )
                anthropic_messages.append({"role": role, "content": blocks or ""})

        payload: dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if tools:
            payload["tools"] = [
                {
                    "name": tool.get("function", {}).get("name", ""),
                    "description": tool.get("function", {}).get("description", ""),
                    "input_schema": tool.get("function", {}).get("parameters", {"type": "object", "properties": {}}),
                }
                for tool in tools
            ]
            payload["tool_choice"] = {"type": "auto"}

        base_url = self.base_url.rstrip("/")
        if base_url.endswith("/v1/messages"):
            endpoint = base_url
        elif base_url.endswith("/messages"):
            endpoint = base_url
        else:
            if not base_url.endswith("/v1"):
                base_url += "/v1"
            endpoint = f"{base_url}/messages"
        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            use_stream = bool(token_callback and not tools)
            if use_stream:
                payload["stream"] = True
            response = requests.post(endpoint, headers=headers, json=payload, stream=use_stream, timeout=timeout)
            if response.status_code != 200:
                return {
                    "role": "assistant",
                    "content": f"Anthropic API error ({response.status_code}): {response.text[:500]}",
                    "tool_calls": [],
                }

            if use_stream:
                text_parts: list[str] = []
                for line in response.iter_lines():
                    if not line:
                        continue
                    line_text = line.decode("utf-8", errors="replace").strip()
                    if not line_text.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line_text[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            text_parts.append(delta["text"])
                            token_callback(delta["text"])
                self.last_used_provider = "anthropic"
                return {"role": "assistant", "content": "".join(text_parts), "tool_calls": []}

            data = response.json()
            text_parts = []
            tool_calls: list[dict[str, Any]] = []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": block.get("input", {}),
                            },
                        }
                    )
            self.last_used_provider = "anthropic"
            return {"role": "assistant", "content": "".join(text_parts), "tool_calls": tool_calls}
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            return {"role": "assistant", "content": f"Anthropic connection failed: {exc!s}", "tool_calls": []}
        except Exception as exc:
            return {"role": "assistant", "content": f"Anthropic request failed: {exc!s}", "tool_calls": []}

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        token_callback: Callable[[str], None] | None = None,
        timeout: int = 25,
        pre_tokens: int = 0,
        post_tokens: int = 0,
        agent: str = "direct",
    ) -> dict[str, Any]:
        """
        Executes one configured provider request. Local fallback is reserved for
        legacy mesh mode and is not used for the normal single-endpoint path.
        """
        active_model = model or self.default_model

        # Fail-safe auto-optimizer: if pre_tokens was not provided by caller, optimize automatically
        if not pre_tokens and len(messages) >= 1:
            try:
                from core.token_harness import token_harness, estimate_messages_tokens
                pre_tokens = estimate_messages_tokens(messages)
                last_p = ""
                for m in reversed(messages):
                    if m.get("role") == "user":
                        last_p = str(m.get("content", ""))
                        break
                opt_messages, opt_tools = token_harness.optimize(
                    messages=messages,
                    tools=tools,
                    user_prompt=last_p,
                )
                messages = opt_messages
                if opt_tools is not None:
                    tools = opt_tools
                post_tokens = estimate_messages_tokens(messages)
            except Exception:
                pass

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
        sanitized_messages = self.sanitize_messages(messages)

        # Context Compressor (skills/context-compressor):
        # Type-aware elision of grep, shell ANSI, JSON, and file dumps to protect TPM budgets
        tool_indices = [i for i, m in enumerate(sanitized_messages) if m.get("role") == "tool"]
        latest_tool_indices = set(tool_indices[-2:] if tool_indices else [])

        for idx in tool_indices:
            raw_content = str(sanitized_messages[idx].get("content", ""))
            if idx in latest_tool_indices:
                sanitized_messages[idx]["content"] = compress_tool_output(raw_content, max_chars=2000)
            else:
                sanitized_messages[idx]["content"] = compress_tool_output(raw_content, max_chars=400)

        # CacheAligner & ContextToolCleanup: Anchor system prompt & replace stale intermediate tool blobs
        sanitized_messages = token_optimizer.optimize_messages_for_cache(sanitized_messages)

        if self.provider == "anthropic":
            return self._chat_anthropic(
                sanitized_messages,
                openai_tools,
                active_model,
                temperature,
                max_tokens,
                token_callback,
                timeout,
            )

        payload: dict[str, Any] = {
            "messages": sanitized_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if active_model:
            payload["model"] = active_model

        # Streaming is only enabled when no tools are passed or when streaming tokens
        use_stream = bool(token_callback and not openai_tools)
        if use_stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if openai_tools:
            payload["tools"] = openai_tools
            payload["tool_choice"] = "auto"

        # Determine prompt content for routing
        last_user_prompt = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_prompt = str(m.get("content", ""))
                break

        pipeline = self._build_provider_pipeline(
            prompt=last_user_prompt,
            requested_model=model,
            messages=sanitized_messages,
            tools=openai_tools,
        )

        for provider in pipeline:
            provider_name = provider["name"]
            # Pre-emptive rate limit check (OmniRoute + WeKnora pattern)
            if not rate_limiter.acquire_slot(provider_name, estimated_tokens=1500, max_wait_sec=0.0):
                print(
                    f"[CLOUD-BRAIN] ⏳ {provider_name} at RPM/TPM limit. Pre-emptively failing over to next provider."
                )
                continue

            url = f"{provider['base_url']}/chat/completions"
            provider_key = provider["api_key"]
            provider_model = provider["model"]

            current_payload = dict(payload)
            if provider_model:
                current_payload["model"] = provider_model
            else:
                current_payload.pop("model", None)

            current_timeout = 15 if "sambanova" in provider_name.lower() else timeout

            try:
                res = requests.post(
                    url,
                    headers=self._get_headers(provider_key),
                    json=current_payload,
                    stream=use_stream,
                    timeout=current_timeout,
                )

                # Check for Account/Payment Exhaustion (402)
                if res.status_code == 402 or "PAYMENT_METHOD_REQUIRED" in res.text:
                    print(
                        f"[CLOUD-BRAIN] ⚠️ {provider_name} returned HTTP 402 (Payment/Credits Exhausted). Disabling provider for this session."
                    )
                    self.disabled_providers.add(provider_name)
                    if provider_key:
                        self._save_cooldown(provider_key, 86400.0)
                    else:
                        self._save_cooldown(provider_name, 86400.0)
                    continue

                # Check for Rate Limit (429)
                if res.status_code == 429:
                    err_msg = ""
                    try:
                        err_data = res.json()
                        if isinstance(err_data, dict):
                            err_msg = err_data.get("error", {}).get("message", "") or str(err_data.get("error", ""))
                    except Exception:
                        pass
                    if not err_msg:
                        err_msg = res.text[:160].replace("\n", " ")

                    # Classify cooldown duration: Daily Quota vs Sliding Window TPM
                    is_daily = any(
                        s in err_msg.lower()
                        for s in ["tokens per day", "tpd", "requests per day", "rpd", "limit: 20", "daily"]
                    )
                    cooldown_sec = 86400.0 if is_daily else 35.0
                    cooldown_label = "24h daily quota" if is_daily else "35s sliding-window TPM"

                    # Trip circuit breaker for this key and rate limiter
                    rate_limiter.record_429(provider_name, retry_after=cooldown_sec)
                    if provider_key:
                        self._save_cooldown(provider_key, cooldown_sec)
                    else:
                        self._save_cooldown(provider_name, cooldown_sec)

                    print(
                        f"[CLOUD-BRAIN] ⚠️ {provider_name} returned HTTP 429 ({cooldown_label}): {err_msg}. Sidelining and rotating to next provider..."
                    )

                    # 1. Multi-Model TPM Bucket Hopping on Groq:
                    # Groq TPM is enforced per-model. llama-3.1-8b-instant has an independent 20,000 TPM limit!
                    is_groq = "groq" in provider_name.lower() or provider.get("family") == "groq"
                    if is_groq and not is_daily:
                        for fallback_m in ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]:
                            if fallback_m == provider_model:
                                continue
                            fast_payload = dict(current_payload)
                            fast_payload["model"] = fallback_m
                            res_fast = requests.post(
                                url,
                                headers=self._get_headers(provider_key),
                                json=fast_payload,
                                stream=use_stream,
                                timeout=current_timeout,
                            )
                            if res_fast.status_code == 200:
                                res = res_fast
                                provider_name = f"{provider_name} ({fallback_m})"
                                self.last_used_provider = provider_name
                                break

                    # 2. Short backoff retry if reset is small
                    if res.status_code == 429:
                        reset_header = res.headers.get("x-ratelimit-reset-tokens", "") or res.headers.get(
                            "retry-after", ""
                        )
                        wait_sec = 2.5
                        if "s" in reset_header:
                            try:
                                wait_sec = float(reset_header.replace("s", "").strip()) + 0.3
                            except Exception:
                                wait_sec = 2.5
                        elif reset_header.replace(".", "", 1).isdigit():
                            try:
                                wait_sec = float(reset_header) + 0.3
                            except Exception:
                                wait_sec = 2.5
                        if wait_sec <= 3.5:
                            time.sleep(wait_sec)
                            res = requests.post(
                                url,
                                headers=self._get_headers(provider_key),
                                json=current_payload,
                                stream=use_stream,
                                timeout=current_timeout,
                            )

                # Transient server overload (502 / 503) retry (common for Google Gemini)
                if res.status_code in (502, 503):
                    time.sleep(1.5)
                    res = requests.post(
                        url,
                        headers=self._get_headers(provider_key),
                        json=current_payload,
                        stream=use_stream,
                        timeout=current_timeout,
                    )

                if res.status_code in (429, 502, 503):
                    err_msg = ""
                    try:
                        err_data = res.json()
                        if isinstance(err_data, dict):
                            err_msg = err_data.get("error", {}).get("message", "") or str(err_data.get("error", ""))
                        elif isinstance(err_data, list) and err_data:
                            err_msg = err_data[0].get("error", {}).get("message", "")
                    except Exception:
                        pass
                    if not err_msg:
                        err_msg = res.text[:160].replace("\n", " ")
                    print(
                        f"[CLOUD-BRAIN] ⚠️ {provider_name} returned HTTP {res.status_code}: {err_msg}. Cascading to next cloud provider..."
                    )
                    continue

                if res.status_code != 200:
                    print(
                        f"[CLOUD-BRAIN] ⚠️ {provider_name} error ({res.status_code}): {res.text[:160]}. Cascading to next cloud provider..."
                    )
                    continue

                self.last_used_provider = provider_name
                rate_limiter.record_consumption(provider_name, 1500)

                stream_usage: dict[str, Any] = {}
                parsed_tool_calls: list[dict[str, Any]] = []
                content = ""

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
                                    if "usage" in chunk and chunk["usage"]:
                                        stream_usage = chunk["usage"]
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    token = delta.get("content", "")
                                    if token:
                                        full_content += token
                                        if token_callback:
                                            token_callback(token)
                                except Exception:
                                    continue

                    content = full_content
                    if full_content:
                        from core.ollama_client import parse_fallback_tool_calls

                        extracted, clean = parse_fallback_tool_calls(full_content)
                        if extracted:
                            parsed_tool_calls = extracted
                            content = clean
                else:
                    # Non-streaming JSON response
                    data = res.json()
                    choice = data.get("choices", [{}])[0].get("message", {})
                    content = choice.get("content", "") or ""
                    raw_tool_calls = choice.get("tool_calls", [])

                    for tc in raw_tool_calls:
                        fn = tc.get("function", {})
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = {"raw_input": args}
                        parsed_tool_calls.append(
                            {
                                "id": tc.get("id", "") or f"call_{uuid.uuid4().hex[:8]}",
                                "type": "function",
                                "function": {"name": fn.get("name", ""), "arguments": args},
                            }
                        )

                    # Resilient fallback parsing for open-weight models emitting XML/Markdown tools in content
                    if not parsed_tool_calls and content:
                        from core.ollama_client import parse_fallback_tool_calls

                        extracted, clean = parse_fallback_tool_calls(content)
                        if extracted:
                            parsed_tool_calls = extracted
                            content = clean

                # Determine accurate token usage from response or heuristic estimator
                usage = stream_usage if use_stream else data.get("usage", {})
                if usage and (usage.get("prompt_tokens") or usage.get("completion_tokens")):
                    in_tok = int(usage.get("prompt_tokens", 0) or 0)
                    out_tok = int(usage.get("completion_tokens", 0) or 0)
                else:
                    from core.token_harness import estimate_messages_tokens, estimate_tokens

                    in_tok = estimate_messages_tokens(messages)
                    out_tok = estimate_tokens(content)

                # Query rate limiter remaining capacity
                bucket_status = rate_limiter.get_provider_status(provider_name)
                bucket_after = bucket_status.get("tpm_remaining", 0)

                try:
                    from core.token_harness import token_harness

                    token_harness.record_usage(
                        provider=provider_name,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        model=provider_model,
                        agent=agent,
                        pre_tokens=pre_tokens or in_tok,
                        post_tokens=post_tokens or in_tok,
                        bucket_before=bucket_after + in_tok + out_tok,
                        bucket_after=bucket_after,
                    )
                except Exception:
                    pass

                return {"role": "assistant", "content": content, "tool_calls": parsed_tool_calls}

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                print(
                    f"[CLOUD-BRAIN] ⚠️ Connection to {provider_name} failed ({e!s}). Cascading to next cloud provider..."
                )
                continue
            except Exception as e:
                print(f"[CLOUD-BRAIN] ⚠️ Error with {provider_name} ({e!s}). Cascading...")
                continue

        # Do not silently switch a single-endpoint configuration to local Ollama.
        # An invalid key, model, or URL should be visible to the user.
        if self.routing_mode == "direct" and not (
            self.api_key.startswith("mock_") or self.api_key.startswith("gsk_mock")
        ):
            self.last_used_provider = "configured_endpoint_error"
            return {
                "role": "assistant",
                "content": "The configured LLM endpoint did not return a usable response. Check LLM_PROVIDER, LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL, then try again.",
                "tool_calls": [],
            }

        # If all cloud providers failed or returned error:
        print("[CLOUD-BRAIN] ⚠️ All cloud providers exhausted or unavailable. Initiating local fallback...")
        try:
            from core.colibri_client import colibri_client
            if colibri_client.is_server_running():
                print("[CLOUD-BRAIN] 🪶 Routing request to local Colibrì MoE engine (0 tokens)...")
                res = colibri_client.chat_completion(
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if res and "choices" in res and res["choices"]:
                    choice = res["choices"][0].get("message", {})
                    content = choice.get("content", "") or ""
                    tool_calls = choice.get("tool_calls", [])
                    self.last_used_provider = "colibri_local"
                    return {"role": "assistant", "content": content, "tool_calls": tool_calls}
        except Exception as e:
            print(f"[CLOUD-BRAIN] Colibri local bypass note: {e}")

        print("[CLOUD-BRAIN] ⚠️ Initiating local Ollama fallback...")
        return self._fallback_to_ollama(messages, tools, token_callback)

    def _fallback_to_ollama(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        token_callback: Callable[[str], None] | None = None,
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
            "options": {"temperature": 0.2, "num_ctx": OLLAMA_NUM_CTX},
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
                return {"role": "assistant", "content": msg.get("content", ""), "tool_calls": msg.get("tool_calls", [])}
            return {"role": "assistant", "content": f"[Ollama Error {res.status_code}]: {res.text}", "tool_calls": []}
        except Exception as err:
            return {
                "role": "assistant",
                "content": f"Both Cloud and Local LLMs were unreachable. Error: {err!s}",
                "tool_calls": [],
            }
