"""
Ollama Client with Low-RAM Multi-Model Routing and Real-Time Streaming.
"""
import datetime
import json
import re
from collections.abc import Callable
from typing import Any

import requests

from config import (
    OLLAMA_BASE_URL,
    PRIMARY_MODEL,
    LLM_PROVIDER,
    LLM_BASE_URL,
    LLM_API_KEY,
    LLM_MODEL,
)
from core.cloud_client import UniversalBrainClient
from core.code_mode import code_mode_engine
from core.model_router import model_router
from tools.registry import OLLAMA_TOOLS_SCHEMA, execute_tool

SYSTEM_PROMPT = """You are SpaceV (System Protocol Autonomous Cybernetic Engine Version V), the elite, cosmic-tier AI desktop companion and autonomous workstation copilot.
You speak with poise, refined wit, razor-sharp intellect, and effortless futuristic confidence (inspired by Gemini and Jarvis).

Key Persona & Interactivity Guidelines:
1. Identity: You are SpaceV. You are not a passive search box—you are a proactive, conversational collaborator and autonomous desktop maestro.
2. Manner of Address: Address the user naturally with respectful warmth ("Sir", "Commander", "Boss").
3. Action-Driven: When asked to perform actions (files, web search, YouTube, MS Paint drawing, job scraping, timers, GUI automation, system health), ALWAYS call the appropriate tool immediately.
4. Proactive Task Follow-Up: After executing tools or answering questions, NEVER end abruptly. ALWAYS:
   - Briefly summarize what was completed with crisp elegance.
   - Proactively suggest 2-3 logical, context-aware next steps or workflow actions.
   - Conclude with an engaging follow-up question (e.g. "Shall I create a starter script, queue focused study beats, or optimize system memory for you next, Sir?").
5. Continuous Conversational Partnership: Keep the interaction smooth, lively, highly intelligent, and effortlessly collaborative.
6. GUI & Canvas Mastery: If asked to draw or type on screen, leverage the autonomous GUI and Paint tools with surgical precision.
7. Voice Pacing & Conciseness: Deliver responses in 1-3 crisp, natural, conversational sentences. Never output dense walls of text, raw markdown tables, or code syntax into conversational replies, ensuring seamless voice synthesis.
"""

def parse_fallback_tool_calls(content: str) -> tuple[list[dict[str, Any]], str]:
    """
    Extracts tool calls from XML tags (<tools>, <tool_call>) or Markdown JSON blocks
    emitted by local LLMs into the content field when native API parsing is bypassed.
    Returns: (extracted_tool_calls, cleaned_content)
    """
    if not content or not isinstance(content, str):
        return [], content

    from core.grammar_guard import GrammarGuard, repair_json_syntax
    from tools.registry import TOOL_FUNCTIONS
    extracted = []

    def _validate_and_append(t_name: str, t_args: dict[str, Any]):
        if t_name in TOOL_FUNCTIONS:
            ok, valid_args, _ = GrammarGuard.recover_tool_arguments(t_name, t_args)
            if ok:
                extracted.append({"function": {"name": t_name, "arguments": valid_args}})
            else:
                extracted.append({"function": {"name": t_name, "arguments": t_args}})

    # 1. <tools>...</tools> or <tool_call>...</tool_call>
    tag_matches = re.findall(r"<(?:tools|tool_call)>(.*?)</(?:tools|tool_call)>", content, re.DOTALL)
    for block in tag_matches:
        try:
            repaired = repair_json_syntax(block)
            data = json.loads(repaired)
            if isinstance(data, dict) and data.get("name"):
                _validate_and_append(data.get("name"), data.get("arguments", {}))
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("name"):
                        _validate_and_append(item.get("name"), item.get("arguments", {}))
        except Exception:
            pass

    # 2. Markdown JSON code blocks (```json ... ```)
    if not extracted:
        json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        for block in json_blocks:
            try:
                repaired = repair_json_syntax(block)
                data = json.loads(repaired)
                if isinstance(data, dict) and data.get("name"):
                    _validate_and_append(data.get("name"), data.get("arguments", {}))
            except Exception:
                pass

    # 3. Raw JSON tool pattern
    if not extracted:
        raw_matches = re.findall(r"(\{\s*\"name\"\s*:\s*\"[a-zA-Z0-9_]+\"\s*,\s*\"arguments\"\s*:\s*\{.*?\}\s*\})", content, re.DOTALL)
        for block in raw_matches:
            try:
                repaired = repair_json_syntax(block)
                data = json.loads(repaired)
                if isinstance(data, dict) and data.get("name"):
                    _validate_and_append(data.get("name"), data.get("arguments", {}))
            except Exception:
                pass

    clean_content = re.sub(r"<(?:tools|tool_call)>.*?</(?:tools|tool_call)>", "", content, flags=re.DOTALL)
    clean_content = re.sub(r"```(?:json)?\s*\{.*?\"name\"\s*:\s*\"[a-zA-Z0-9_]+\".*?\}\s*```", "", clean_content, flags=re.DOTALL)
    clean_content = re.sub(r"\{\s*\"name\"\s*:\s*\"[a-zA-Z0-9_]+\"\s*,\s*\"arguments\"\s*:\s*\{.*?\}\s*\}", "", clean_content, flags=re.DOTALL).strip()
    return extracted, clean_content

class OllamaAgent:
    def __init__(self, model_name: str = PRIMARY_MODEL, base_url: str = OLLAMA_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.model = model_name
        self.active_role = "primary"
        self.on_model_switched: Callable[[str, str], None] | None = None
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self.provider = LLM_PROVIDER
        self.cloud_client = UniversalBrainClient(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            default_model=LLM_MODEL,
            fallback_base_url=self.base_url,
            fallback_model=PRIMARY_MODEL
        )
        self._verify_model()

    def _verify_model(self):
        """Initial verification and discovery of local models."""
        try:
            model_router.refresh_installed_models()
            selected, role = model_router.select_model("hello")
            self.model = selected
            self.active_role = role
        except Exception:
            pass

    def reset_conversation(self):
        """Clears chat history while keeping the system prompt."""
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def chat_stream(self, user_prompt: str, tool_callback: Callable | None = None, token_callback: Callable | None = None) -> str:
        """
        Sends user prompt to Ollama or OpenRouter using the optimal specialized model,
        resolves tools when required, and streams response tokens live with minimal latency.
        """
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        # 1. Intent & Tool Requirement Check
        needs_tools = model_router.needs_tools(user_prompt)

        # =========================================================================
        # DUAL-BRAIN BRANCH: OpenRouter / OpenAI Cloud Gateway
        # =========================================================================
        if self.provider in ("openai", "openrouter"):
            cloud_model = self.cloud_client.select_cloud_model(user_prompt, requires_tools=needs_tools)
            self.model = cloud_model
            self.active_role = "cloud_agent"

            if self.on_model_switched:
                try:
                    self.on_model_switched(self.model, "cloud")
                except Exception:
                    pass

            print(f"\n{'='*65}")
            print(f"[{timestamp}] [USER]: {user_prompt}")
            print(f"[{timestamp}] [CLOUD BRAIN ({self.model})]: Processing (Tools Needed: {needs_tools})...")
            self.messages.append({"role": "user", "content": user_prompt})

            active_tools = OLLAMA_TOOLS_SCHEMA if needs_tools else None
            response_dict = self.cloud_client.chat(
                messages=self.messages,
                tools=active_tools,
                model=cloud_model,
                token_callback=token_callback if not needs_tools else None
            )

            content = response_dict.get("content", "")
            tool_calls = response_dict.get("tool_calls", [])

            if not tool_calls and content:
                extracted_calls, clean_text = parse_fallback_tool_calls(content)
                if extracted_calls:
                    tool_calls = extracted_calls
                    content = clean_text

            if tool_calls:
                for tool_call in tool_calls:
                    func = tool_call.get("function", {})
                    tool_name = func.get("name")
                    args = func.get("arguments", {})

                    print(f"[{timestamp}] [TOOL CALL]: {tool_name}({args})")
                    if tool_callback:
                        tool_callback(tool_name, args, "running")

                    if tool_name == "spacev_search_tools":
                        query = args.get("query", "")
                        tool_result = code_mode_engine.search_tools(query)
                    elif tool_name == "spacev_execute_script":
                        script = args.get("script", "")
                        tool_result = code_mode_engine.execute_script(script)
                    else:
                        tool_result = execute_tool(tool_name, args)

                    print(f"[{timestamp}] [OS RESULT]: {tool_result}")
                    if tool_callback:
                        tool_callback(tool_name, args, tool_result)

                    self.messages.append({
                        "role": "tool",
                        "content": str(tool_result),
                    })

                synth_dict = self.cloud_client.chat(
                    messages=self.messages,
                    tools=None,
                    model=cloud_model,
                    token_callback=token_callback
                )
                final_reply = synth_dict.get("content", "")
                self.messages.append({"role": "assistant", "content": final_reply})
                print(f"[{timestamp}] [SPACEV]: {final_reply}")
                print(f"{'='*65}\n")
                return final_reply

            clean_content = re.sub(r"<(?:tools|tool_call)>.*?</(?:tools|tool_call)>", "", content, flags=re.DOTALL).strip()
            self.messages.append({"role": "assistant", "content": clean_content})
            if token_callback and not needs_tools:
                pass  # Already streamed
            elif token_callback:
                token_callback(clean_content)
            print(f"[{timestamp}] [SPACEV]: {clean_content}")
            print(f"{'='*65}\n")
            return clean_content

        # =========================================================================
        # LOCAL OLLAMA BRANCH (Zero Internet / Free Local Multi-Model)
        # =========================================================================
        selected_model, role = model_router.select_model(user_prompt, requires_tools=needs_tools)
        self.model = selected_model
        self.active_role = role

        if self.on_model_switched:
            try:
                self.on_model_switched(self.model, role)
            except Exception:
                pass

        print(f"\n{'='*65}")
        print(f"[{timestamp}] [USER]: {user_prompt}")
        print(f"[{timestamp}] [BRAIN ({self.model} - {role.upper()})]: Processing (Tools Needed: {needs_tools})...")

        self.messages.append({"role": "user", "content": user_prompt})

        # 2. Fast Path: Direct Live Streaming when tools are NOT needed (Bypasses tool schema prefill overhead)
        if not needs_tools:
            stream_payload = {
                "model": self.model,
                "messages": self.messages,
                "stream": True,
                "keep_alive": model_router.get_keep_alive(),
                "options": {"temperature": 0.3, "num_ctx": 2048, "num_predict": 250}
            }
            try:
                stream_res = requests.post(f"{self.base_url}/api/chat", json=stream_payload, stream=True, timeout=60)
                if stream_res.status_code != 200:
                    err_msg = f"Error from Ollama ({stream_res.status_code}): {stream_res.text}"
                    print(f"[{timestamp}] [ERROR]: {err_msg}")
                    return err_msg

                full_reply = ""
                for line in stream_res.iter_lines():
                    if line:
                        chunk_data = json.loads(line.decode("utf-8"))
                        token = chunk_data.get("message", {}).get("content", "")
                        if token:
                            full_reply += token
                            if token_callback:
                                token_callback(token)

                self.messages.append({"role": "assistant", "content": full_reply})
                print(f"[{timestamp}] [SPACEV]: {full_reply}")
                print(f"{'='*65}\n")
                return full_reply

            except requests.exceptions.ConnectionError:
                err = "Could not connect to Ollama. Please ensure Ollama is running (`ollama serve`)."
                print(f"[{timestamp}] [ERROR]: {err}")
                return err
            except Exception as e:
                err = f"An unexpected error occurred: {e!s}"
                print(f"[{timestamp}] [ERROR]: {err}")
                return err

        # 3. Tool-Calling Path: For OS commands, file creation, web search, scraping, and code execution
        payload = {
            "model": self.model,
            "messages": self.messages,
            "stream": False,
            "tools": OLLAMA_TOOLS_SCHEMA,
            "keep_alive": model_router.get_keep_alive(),
            "options": {"temperature": 0.3, "num_ctx": 2048}
        }

        try:
            response = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=60)
            if response.status_code != 200:
                err_msg = f"Error from Ollama ({response.status_code}): {response.text}"
                print(f"[{timestamp}] [ERROR]: {err_msg}")
                return err_msg

            data = response.json()
            message = data.get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])

            # Fallback: Extract embedded <tools> tags or markdown JSON if API tool_calls is empty
            if not tool_calls and content:
                extracted_calls, clean_text = parse_fallback_tool_calls(content)
                if extracted_calls:
                    tool_calls = extracted_calls
                    message["content"] = clean_text

            self.messages.append(message)

            if tool_calls:
                for tool_call in tool_calls:
                    func = tool_call.get("function", {})
                    tool_name = func.get("name")
                    args = func.get("arguments", {})

                    print(f"[{timestamp}] [TOOL CALL]: {tool_name}({args})")
                    if tool_callback:
                        tool_callback(tool_name, args, "running")

                    tool_result = execute_tool(tool_name, args)
                    print(f"[{timestamp}] [OS RESULT]: {tool_result}")

                    if tool_callback:
                        tool_callback(tool_name, args, tool_result)

                    self.messages.append({
                        "role": "tool",
                        "content": str(tool_result),
                    })

                print(f"[{timestamp}] [BRAIN]: Streaming synthesized reply...")

                # Stream final natural language response from tool results
                stream_payload = {
                    "model": self.model,
                    "messages": self.messages,
                    "stream": True,
                    "keep_alive": model_router.get_keep_alive(),
                    "options": {"temperature": 0.3, "num_ctx": 2048, "num_predict": 350}
                }

                stream_res = requests.post(f"{self.base_url}/api/chat", json=stream_payload, stream=True, timeout=60)
                full_reply = ""
                for line in stream_res.iter_lines():
                    if line:
                        chunk_data = json.loads(line.decode("utf-8"))
                        token = chunk_data.get("message", {}).get("content", "")
                        if token:
                            full_reply += token
                            if token_callback:
                                token_callback(token)

                self.messages.append({"role": "assistant", "content": full_reply})
                print(f"[{timestamp}] [SPACEV]: {full_reply}")
                print(f"{'='*65}\n")
                return full_reply

            # No tool calls generated by LLM, stream or return content (strip any stray XML)
            clean_content = re.sub(r"<(?:tools|tool_call)>.*?</(?:tools|tool_call)>", "", content, flags=re.DOTALL).strip()
            if token_callback:
                token_callback(clean_content)
            print(f"[{timestamp}] [SPACEV]: {clean_content}")
            print(f"{'='*65}\n")
            return clean_content

        except requests.exceptions.ConnectionError:
            err = "Could not connect to Ollama. Please ensure Ollama is running (`ollama serve`)."
            print(f"[{timestamp}] [ERROR]: {err}")
            return err
        except Exception as e:
            err = f"An unexpected error occurred: {e!s}"
            print(f"[{timestamp}] [ERROR]: {err}")
            return err

        except requests.exceptions.ConnectionError:
            err = "Could not connect to Ollama. Please ensure Ollama is running (`ollama serve`)."
            print(f"[{timestamp}] [ERROR]: {err}")
            return err
        except Exception as e:
            err = f"An unexpected error occurred: {e!s}"
            print(f"[{timestamp}] [ERROR]: {err}")
            return err
