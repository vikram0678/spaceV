"""
Universal Dual-Brain Hybrid Orchestrator for SpaceV.
Coordinates:
1. Cloud Brain Gateway (Groq, Cerebras, Google Gemini, OpenRouter, SambaNova, Mistral, ZAI)
2. Local Free Offline Models (Ollama, Qwen-2.5-Coder, Llama-3, DeepSeek)
3. Tool Virtualization (Cloudflare MCP Code Mode Pattern: 81% token reduction)
4. Automatic Failover and Circuit-Breakers
"""
import datetime
import json
import re
import uuid
from collections.abc import Callable
from typing import Any

import requests

from config import (
    ENABLE_CODE_MODE,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    PRIMARY_MODEL,
)
from core.cloud_client import UniversalBrainClient
from core.code_mode import CODE_MODE_META_TOOLS, code_mode_engine
from core.model_router import model_router
from core.scratchpad import active_scratchpad
from core.token_optimizer import token_optimizer
from tools.registry import OLLAMA_TOOLS_SCHEMA, execute_tool, get_scoped_tools

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
8. Software Development & Editor Pipelines: When instructed to write a program, script, or algorithm in an editor (e.g. "write the anagram program in python3 in the vscode"):
   - ALWAYS use `create_file` first to write the complete, functional, well-commented code to a file (e.g., 'anagram.py').
   - Then use `open_text_editor(file_name='anagram.py', editor='code')` or `open_application('vscode')` to open the file in the editor for the user.
   - Never open an empty editor or pretend to write code without creating the file on disk.
9. Script Execution & Workstation Pipelines: When instructed to run, execute, or test a script, code file, or program (e.g. "now execute that program", "run the python script", "execute that in vscode"):
   - Resolve the target file from the conversation context, working memory notes (e.g. `last_file_name`), or recent file creations.
   - Use `run_python_script(file_name_or_path='...')` to execute Python scripts or `execute_terminal_command(command='...')` for shell/CLI execution.
   - If the user specifically requested executing or viewing it in an editor like VS Code, call `open_text_editor(file_name='...', editor='code')` to bring the file into focus alongside execution.
   - Do NOT repeatedly loop inspecting the scratchpad (`scratchpad_view`). Execute the action decisively.
10. Celesto Sandbox Containment Policy (MANDATORY):
   - When asked to clone external repositories (git clone), install untrusted packages (pip install), or execute downloaded scripts (curl | bash), ALWAYS call `detonate_in_sandbox` instead of `execute_terminal_command`.
   - External code must NEVER touch the host filesystem directly; all untrusted code is quarantined inside the Celesto microVM.
11. Workspace & Repository Exploration:
   - When asked to inspect, list, explore, or examine the SpaceV codebase, repository, or project files (e.g. "what files are in this project", "inspect my SpaceV project", "check main.py"):
   - ALWAYS use `list_workspace_files` to discover project files, and `read_file_content(file_name_or_path='...', location='Workspace')` to inspect project code.
   - Do NOT restrict repository or project queries to Desktop files.
"""


def parse_fallback_tool_calls(content: str) -> tuple[list[dict[str, Any]], str]:
    """
    Extracts tool calls from XML tags (<tools>, <tool_call>) or Markdown JSON blocks
    emitted by LLMs into the content field when native API parsing is bypassed.
    Returns: (extracted_tool_calls, cleaned_content)
    """
    if not content or not isinstance(content, str):
        return [], content

    from core.grammar_guard import GrammarGuard, repair_json_syntax
    from tools.registry import TOOL_ALIASES, TOOL_FUNCTIONS
    extracted = []

    def _validate_and_append(t_name: str, t_args: dict[str, Any], is_xml: bool = False):
        canonical = TOOL_ALIASES.get(t_name, t_name)
        if canonical in TOOL_FUNCTIONS:
            ok, valid_args, _ = GrammarGuard.recover_tool_arguments(canonical, t_args)
            entry = {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {"name": canonical, "arguments": valid_args if ok else t_args},
                "intercepted_from_xml": is_xml
            }
            extracted.append(entry)

    # 0. Qwen / Llama XML function tag format
    qwen_tool_blocks = re.findall(r"<function(?:=|\s+name=[\"']?)([a-zA-Z0-9_]+)[\"']?>(.*?)</function>", content, re.DOTALL)
    for t_name, body in qwen_tool_blocks:
        t_args = {}
        param_matches = re.findall(r"<parameter(?:=|\s+name=[\"']?)([a-zA-Z0-9_]+)[\"']?>(.*?)</parameter>", body, re.DOTALL)
        for p_name, p_val in param_matches:
            val_clean = p_val.strip()
            if (val_clean.startswith("{") and val_clean.endswith("}")) or (val_clean.startswith("[") and val_clean.endswith("]")):
                try:
                    val_clean = json.loads(val_clean)
                except Exception:
                    pass
            t_args[p_name] = val_clean
        if t_name:
            _validate_and_append(t_name, t_args, is_xml=True)

    # 1. <tools>...</tools> or <tool_call>...</tool_call>
    tag_matches = re.findall(r"<(?:tools|tool_call)>(.*?)(?:</(?:tools|tool_call)>|$)", content, re.DOTALL)
    for block in tag_matches:
        block_str = block.strip()
        if not block_str:
            continue
        try:
            prefix_match = re.match(r"^([a-zA-Z0-9_]+)\s*(\{.*\})$", block_str, re.DOTALL)
            if prefix_match:
                t_name = prefix_match.group(1).strip()
                t_json = repair_json_syntax(prefix_match.group(2))
                t_args = json.loads(t_json)
                if isinstance(t_args, dict):
                    _validate_and_append(t_name, t_args, is_xml=True)
                    continue

            repaired = repair_json_syntax(block_str)
            data = json.loads(repaired)
            if isinstance(data, dict):
                name = data.get("name") or data.get("tool") or data.get("function", {}).get("name")
                args = data.get("arguments") or data.get("args") or data.get("function", {}).get("arguments", {})
                if name:
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {"raw_input": args}
                    _validate_and_append(name, args, is_xml=True)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        name = item.get("name") or item.get("tool") or item.get("function", {}).get("name")
                        args = item.get("arguments") or item.get("args") or item.get("function", {}).get("arguments", {})
                        if name:
                            _validate_and_append(name, args, is_xml=True)
        except Exception:
            pass

    # 2. Markdown JSON code blocks
    if not extracted:
        json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        for block in json_blocks:
            try:
                repaired = repair_json_syntax(block)
                data = json.loads(repaired)
                if isinstance(data, dict):
                    name = data.get("name") or data.get("tool")
                    args = data.get("arguments") or data.get("args") or {}
                    if name:
                        _validate_and_append(name, args, is_xml=False)
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
                    _validate_and_append(data.get("name"), data.get("arguments", {}), is_xml=False)
            except Exception:
                pass

    clean_content = re.sub(r"<function(?:=|\s+name=[\"']?)[a-zA-Z0-9_]+[\"']?>.*?</function>", "", content, flags=re.DOTALL)
    clean_content = re.sub(r"<(?:tools|tool_call)>.*?(?:</(?:tools|tool_call)>|$)", "", clean_content, flags=re.DOTALL)
    clean_content = re.sub(r"```(?:json)?\s*\{.*?\"name\"\s*:\s*\"[a-zA-Z0-9_]+\".*?\}\s*```", "", clean_content, flags=re.DOTALL)
    clean_content = re.sub(r"\{\s*\"name\"\s*:\s*\"[a-zA-Z0-9_]+\"\s*,\s*\"arguments\"\s*:\s*\{.*?\}\s*\}", "", clean_content, flags=re.DOTALL)
    clean_content = re.sub(r"</?(?:tools|tool_call|function|parameter)[^>]*>", "", clean_content).strip()
    return extracted, clean_content


class HybridBrainAgent:
    """
    Universal Cybernetic Agent Orchestrator for SpaceV.
    Seamlessly orchestrates Free Offline Local Models (Ollama)
    and High-Speed Cloud APIs (Groq, Cerebras, Google Gemini, OpenRouter, SambaNova).
    """

    def __init__(
        self,
        model_name: str = PRIMARY_MODEL,
        base_url: str = OLLAMA_BASE_URL,
        provider: str = LLM_PROVIDER
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model_name
        self.active_role = "primary"
        self.on_model_switched: Callable[[str, str], None] | None = None
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self.provider = provider
        self.cloud_client = UniversalBrainClient(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            default_model=LLM_MODEL,
            fallback_base_url=self.base_url,
            fallback_model=PRIMARY_MODEL
        )
        self.active_paused_frame: dict[str, Any] | None = None
        self._verify_model()

    def _verify_model(self):
        """Initial discovery of available models (safe on both cloud-only and offline machines)."""
        try:
            if self.provider == "ollama":
                model_router.refresh_installed_models()
                selected, role = model_router.select_model("hello")
                self.model = selected
                self.active_role = role
        except Exception:
            pass

    def reset_conversation(self):
        """Clears chat history while preserving the persona system prompt."""
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.active_paused_frame = None

    def _resolve_tools(self, user_prompt: str, needs_tools: bool) -> list[dict[str, Any]] | None:
        """
        Dynamically selects the optimal tool schema representation:
        - If ENABLE_CODE_MODE is active on cloud models: delivers 2 meta-tools (180 tokens).
        - Otherwise: dynamically slices required tools via get_scoped_tools to prevent TPM exhaustion.
        """
        if not needs_tools:
            return None
        if ENABLE_CODE_MODE and self.provider in ("openai", "openrouter"):
            return CODE_MODE_META_TOOLS
        return get_scoped_tools(user_prompt, OLLAMA_TOOLS_SCHEMA)

    def chat_stream(
        self,
        user_prompt: str,
        tool_callback: Callable | None = None,
        token_callback: Callable | None = None
    ) -> str:
        """
        Sends user prompt to optimal specialized brain (Cloud API or Local Free Ollama),
        resolves tools via Code Mode virtualization, and streams synthesized responses.
        """
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        # 0. Reload durable task planning state from disk (.spacev/task_plan.md)
        active_scratchpad.reload_from_disk()

        # 1. Intent & Tool Requirement Check
        needs_tools = model_router.needs_tools(user_prompt)

        # =========================================================================
        # CLOUD BRAIN BRANCH: Groq / Cerebras / Gemini / OpenRouter / SambaNova
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
            print(f"[{timestamp}] [UNIVERSAL CLOUD BRAIN ({self.model})]: Processing (Tools Needed: {needs_tools})...")
            self.messages.append({"role": "user", "content": user_prompt})

            active_tools = self._resolve_tools(user_prompt, needs_tools)
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

                    # Dispatch tool via Code Mode or direct registry
                    if tool_name in ("spacev_search_tools", "search_tools"):
                        query = args.get("query", "")
                        tool_result = code_mode_engine.search_tools(query)
                    elif tool_name in ("spacev_execute_script", "execute_script"):
                        script = args.get("script", "")
                        tool_result = code_mode_engine.execute_script(script)
                    else:
                        tool_result = execute_tool(tool_name, args)

                    active_scratchpad.record_tool_action(tool_name, args, str(tool_result))
                    print(f"[{timestamp}] [TOOL RESULT]: {tool_result}")
                    if tool_callback:
                        tool_callback(tool_name, args, tool_result)

                    compressed_result = token_optimizer.compress_tool_result(tool_name, tool_result)
                    call_id = tool_call.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": str(compressed_result),
                    })

                self.messages = token_optimizer.optimize_messages_for_cache(self.messages)
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
        # LOCAL OFFLINE BRANCH (Zero Internet / Free Local Multi-Model via Ollama)
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
        print(f"[{timestamp}] [LOCAL OFFLINE BRAIN ({self.model} - {role.upper()})]: Processing (Tools Needed: {needs_tools})...")

        self.messages.append({"role": "user", "content": user_prompt})

        # Fast Path: Direct Live Streaming when tools are NOT needed
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
                    err_msg = f"Error from local model ({stream_res.status_code}): {stream_res.text}"
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
                err = "Could not connect to local model daemon. Please ensure Ollama is running (`ollama serve`)."
                print(f"[{timestamp}] [ERROR]: {err}")
                return err
            except Exception as e:
                err = f"An unexpected error occurred: {e!s}"
                print(f"[{timestamp}] [ERROR]: {err}")
                return err

        # Tool-Calling Path for Local Offline Models
        scoped_local_tools = get_scoped_tools(user_prompt, OLLAMA_TOOLS_SCHEMA)
        payload = {
            "model": self.model,
            "messages": self.messages,
            "stream": False,
            "tools": scoped_local_tools,
            "keep_alive": model_router.get_keep_alive(),
            "options": {"temperature": 0.3, "num_ctx": 2048}
        }

        try:
            response = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=60)
            if response.status_code != 200:
                err_msg = f"Error from local model ({response.status_code}): {response.text}"
                print(f"[{timestamp}] [ERROR]: {err_msg}")
                return err_msg

            data = response.json()
            message = data.get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])

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

                    if tool_name in ("spacev_search_tools", "search_tools"):
                        query = args.get("query", "")
                        tool_result = code_mode_engine.search_tools(query)
                    elif tool_name in ("spacev_execute_script", "execute_script"):
                        script = args.get("script", "")
                        tool_result = code_mode_engine.execute_script(script)
                    else:
                        tool_result = execute_tool(tool_name, args)

                    active_scratchpad.record_tool_action(tool_name, args, str(tool_result))
                    print(f"[{timestamp}] [TOOL RESULT]: {tool_result}")
                    if tool_callback:
                        tool_callback(tool_name, args, tool_result)

                    compressed_result = token_optimizer.compress_tool_result(tool_name, tool_result)
                    self.messages.append({
                        "role": "tool",
                        "content": str(compressed_result),
                    })

                self.messages = token_optimizer.optimize_messages_for_cache(self.messages)
                print(f"[{timestamp}] [BRAIN]: Streaming synthesized reply...")

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

            clean_content = re.sub(r"<(?:tools|tool_call)>.*?</(?:tools|tool_call)>", "", content, flags=re.DOTALL).strip()
            if token_callback:
                token_callback(clean_content)
            print(f"[{timestamp}] [SPACEV]: {clean_content}")
            print(f"{'='*65}\n")
            return clean_content

        except requests.exceptions.ConnectionError:
            err = "Could not connect to local model daemon. Please ensure Ollama is running (`ollama serve`)."
            print(f"[{timestamp}] [ERROR]: {err}")
            return err
        except Exception as e:
            err = f"An unexpected error occurred: {e!s}"
            print(f"[{timestamp}] [ERROR]: {err}")
            return err


# Universal Aliases for Seamless Backward Compatibility
SpaceVAgent = HybridBrainAgent
OllamaAgent = HybridBrainAgent
