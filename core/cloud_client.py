"""
Universal Cloud Brain Client for SpaceV Cybernetic AI Agent.
Provides native OpenAI / OpenRouter API communication with streaming,
tool calling, and automatic rate-limit (HTTP 429) fallback to local Ollama.
"""
import json
import os
import time
import uuid
from collections.abc import Callable
from typing import Any

import requests

from config import (
    AUTONOMOUS_AGENT_MODEL,
    BASE_DIR,
    CEREBRAS_API_KEY,
    CEREBRAS_API_KEYS,
    CEREBRAS_BASE_URL,
    CEREBRAS_FAST_MODEL,
    CEREBRAS_MODEL,
    CODING_ENGINEER_MODEL,
    FAST_CHAT_CLOUD_MODEL,
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
    ROUTING_MODE,
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
    High-performance, resilient OpenAI/OpenRouter client supporting
    both streaming token delivery and function calling with zero-downtime local fallback.
    """

    def __init__(
        self,
        base_url: str = GROQ_BASE_URL or LLM_BASE_URL,
        api_key: str = GROQ_API_KEY or LLM_API_KEY,
        groq_api_key_2: str = "",
        default_model: str = GROQ_MODEL or LLM_MODEL,
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
        routing_mode: str = ROUTING_MODE,
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
        if self.routing_mode == "direct" and not (self.api_key.startswith("mock_") or self.api_key.startswith("gsk_mock")):
            pipeline.append({
                "name": "Direct Paid API",
                "base_url": self.base_url,
                "api_key": self.api_key,
                "model": requested_model or self.default_model,
            })
            return pipeline

        # Track families rotated during this turn to advance each family once per request
        rotated_families: set[str] = set()

        # Helper to get active keys with pre-emptive round-robin rotation
        def get_pool_candidates(name_prefix: str, keys: list[str], base_url: str, model_id: str, family: str) -> list[dict[str, Any]]:
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
                candidates.append({
                    "name": prefix if i == 1 else f"{prefix} Pool {i}",
                    "base_url": base_url,
                    "api_key": k,
                    "model": target_model,
                    "family": family,
                })
            return candidates

        cerebras_candidates = get_pool_candidates("Cerebras", self.cerebras_keys, self.cerebras_base_url, self.cerebras_model, "cerebras")
        cerebras_fast_candidates = get_pool_candidates("Cerebras Fast", self.cerebras_keys, self.cerebras_base_url, CEREBRAS_FAST_MODEL, "cerebras")
        groq_candidates = get_pool_candidates("Groq", self.groq_keys, self.base_url, self.default_model, "groq")
        mistral_candidates = get_pool_candidates("Mistral", self.mistral_keys, MISTRAL_BASE_URL, MISTRAL_MODEL, "mistral")
        mistral_small_candidates = get_pool_candidates("Mistral Small", self.mistral_keys, MISTRAL_BASE_URL, MISTRAL_SMALL_MODEL, "mistral")
        gemini_candidates = get_pool_candidates("Google Gemini", self.gemini_keys, self.gemini_base_url, self.gemini_model, "gemini")

        # Fallback 8B candidates for Groq
        groq_fast_candidates = get_pool_candidates("Groq Fast", self.groq_keys, self.base_url, GROQ_FAST_MODEL, "groq")

        sambanova_provider = {
            "name": "SambaNova",
            "base_url": self.sambanova_base_url,
            "api_key": self.sambanova_api_key,
            "model": self.sambanova_model,
            "family": "sambanova",
        }

        openrouter_candidates = get_pool_candidates("OpenRouter", self.openrouter_keys, OPENROUTER_BASE_URL, OPENROUTER_MODEL, "openrouter")

        zai_provider = {
            "name": "ZAI Direct",
            "base_url": ZAI_BASE_URL,
            "api_key": ZAI_API_KEY,
            "model": ZAI_MODEL,
            "family": "zai",
        }

        if needs_gemini_first:
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
            p for p in pipeline
            if p["name"] not in self.disabled_providers
            and not self.is_in_cooldown(p.get("api_key", ""))
            and not self.is_in_cooldown(p["name"])
        ]

        if not pipeline:
            pipeline.append({
                "name": "Cloud API",
                "base_url": self.base_url,
                "api_key": self.api_key,
                "model": requested_model or self.default_model,
                "family": "groq",
            })

        return pipeline

    def select_cloud_model(self, prompt: str, requires_tools: bool = False) -> str:
        """Dynamically routes between top-tier free OpenRouter models based on task intent."""
        if "openrouter.ai" not in self.base_url.lower():
            return self.default_model
        prompt_lower = prompt.lower()
        if any(w in prompt_lower for w in ["code", "python", "script", "terminal", "debug", "test", "git", "bash", "compile"]):
            return CODING_ENGINEER_MODEL
        elif any(w in prompt_lower for w in ["screen", "click", "window", "gui", "see", "look", "desktop", "browser"]):
            return AUTONOMOUS_AGENT_MODEL
        elif not requires_tools and len(prompt.split()) < 15:
            return FAST_CHAT_CLOUD_MODEL
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

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        token_callback: Callable[[str], None] | None = None,
        timeout: int = 25
    ) -> dict[str, Any]:
        """
        Executes a chat completion against OpenRouter/OpenAI API with live streaming
        and automatic 429 rate limit fallback to local Ollama.
        """
        active_model = model or self.default_model

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
            elif role == "tool":
                if not msg_copy.get("tool_call_id"):
                    if pending_tool_call_ids:
                        msg_copy["tool_call_id"] = pending_tool_call_ids.pop(0)
                    else:
                        msg_copy["tool_call_id"] = f"call_{uuid.uuid4().hex[:8]}"
                if not isinstance(msg_copy.get("content"), str):
                    content_val = msg_copy.get("content", "")
                    msg_copy["content"] = json.dumps(content_val) if isinstance(content_val, (dict, list)) else str(content_val)
            sanitized_messages.append(msg_copy)

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
                print(f"[CLOUD-BRAIN] ⏳ {provider_name} at RPM/TPM limit. Pre-emptively failing over to next provider.")
                continue

            url = f"{provider['base_url']}/chat/completions"
            provider_key = provider["api_key"]
            provider_model = provider["model"]

            current_payload = dict(payload)
            current_payload["model"] = provider_model

            current_timeout = 15 if "sambanova" in provider_name.lower() else timeout

            try:
                res = requests.post(
                    url,
                    headers=self._get_headers(provider_key),
                    json=current_payload,
                    stream=use_stream,
                    timeout=current_timeout
                )

                # Check for Account/Payment Exhaustion (402)
                if res.status_code == 402 or "PAYMENT_METHOD_REQUIRED" in res.text:
                    print(f"[CLOUD-BRAIN] ⚠️ {provider_name} returned HTTP 402 (Payment/Credits Exhausted). Disabling provider for this session.")
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
                    is_daily = any(s in err_msg.lower() for s in ["tokens per day", "tpd", "requests per day", "rpd", "limit: 20", "daily"])
                    cooldown_sec = 86400.0 if is_daily else 35.0
                    cooldown_label = "24h daily quota" if is_daily else "35s sliding-window TPM"

                    # Trip circuit breaker for this key and rate limiter
                    rate_limiter.record_429(provider_name, retry_after=cooldown_sec)
                    if provider_key:
                        self._save_cooldown(provider_key, cooldown_sec)
                    else:
                        self._save_cooldown(provider_name, cooldown_sec)

                    print(f"[CLOUD-BRAIN] ⚠️ {provider_name} returned HTTP 429 ({cooldown_label}): {err_msg}. Sidelining and rotating to next provider...")

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
                                timeout=current_timeout
                            )
                            if res_fast.status_code == 200:
                                res = res_fast
                                provider_name = f"{provider_name} ({fallback_m})"
                                self.last_used_provider = provider_name
                                break

                    # 2. Short backoff retry if reset is small
                    if res.status_code == 429:
                        reset_header = res.headers.get("x-ratelimit-reset-tokens", "") or res.headers.get("retry-after", "")
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
                                timeout=current_timeout
                            )

                # Transient server overload (502 / 503) retry (common for Google Gemini)
                if res.status_code in (502, 503):
                    time.sleep(1.5)
                    res = requests.post(
                        url,
                        headers=self._get_headers(provider_key),
                        json=current_payload,
                        stream=use_stream,
                        timeout=current_timeout
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
                    print(f"[CLOUD-BRAIN] ⚠️ {provider_name} returned HTTP {res.status_code}: {err_msg}. Cascading to next cloud provider...")
                    continue

                if res.status_code != 200:
                    print(f"[CLOUD-BRAIN] ⚠️ {provider_name} error ({res.status_code}): {res.text[:160]}. Cascading to next cloud provider...")
                    continue

                self.last_used_provider = provider_name
                rate_limiter.record_consumption(provider_name, 1500)

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
                    if full_content:
                        from core.ollama_client import parse_fallback_tool_calls
                        extracted, clean = parse_fallback_tool_calls(full_content)
                        if extracted:
                            return {
                                "role": "assistant",
                                "content": clean,
                                "tool_calls": extracted
                            }
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
                        "id": tc.get("id", "") or f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": fn.get("name", ""),
                            "arguments": args
                        }
                    })

                # Resilient fallback parsing for open-weight models emitting XML/Markdown tools in content
                if not parsed_tool_calls and content:
                    from core.ollama_client import parse_fallback_tool_calls
                    extracted, clean = parse_fallback_tool_calls(content)
                    if extracted:
                        parsed_tool_calls = extracted
                        content = clean

                return {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": parsed_tool_calls
                }

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                print(f"[CLOUD-BRAIN] ⚠️ Connection to {provider_name} failed ({e!s}). Cascading to next cloud provider...")
                continue
            except Exception as e:
                print(f"[CLOUD-BRAIN] ⚠️ Error with {provider_name} ({e!s}). Cascading...")
                continue

        # If all cloud providers failed or returned error:
        print("[CLOUD-BRAIN] ⚠️ All cloud providers exhausted or unavailable. Initiating local Ollama fallback...")
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
            "options": {"temperature": 0.2, "num_ctx": OLLAMA_NUM_CTX}
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
