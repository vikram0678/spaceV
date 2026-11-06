"""
Tool Registry and Schema Definitions for Ollama native function calling.
"""
import json
import re
from collections.abc import Callable
from typing import Any

from core.vision_grounding import gui_click_text, read_screen_text
from tools.file_tools import (
    create_file,
    create_folder,
    list_desktop_files,
    list_workspace_files,
    open_folder,
    open_text_editor,
    read_file_content,
)
from tools.gui_tools import (
    gui_draw_in_paint,
    gui_human_search_and_open,
    gui_open_and_search_app,
    gui_open_browser_urls,
    gui_play_youtube,
    gui_search_google_browser,
    gui_type_text,
)
from tools.scraper_tools import fetch_news_headlines, get_weather, get_wikipedia_summary, scrape_jobs
from tools.career_tools import (
    search_and_harvest_jobs,
    track_career_application,
    list_career_applications,
    prepare_job_application,
    analyze_job_description,
    tailor_careerflow_resume,
    apply_to_job,
    create_career_goal,
    get_career_goal,
    activate_career_goal,
    record_career_activity,
    update_career_plan_task,
    get_career_daily_review,
    create_career_reminder,
    list_career_reminders,
    cancel_career_reminder,
    snooze_career_reminder,
    list_career_opportunities,
    track_career_opportunity,
    delete_career_assistant_data,
)
from tools.system_tools import (
    activate_workspace_mode,
    empty_recycle_bin,
    execute_code_block,
    execute_in_vscode_terminal,
    execute_terminal_command,
    get_current_time,
    get_network_info,
    get_system_stats,
    kill_process_by_name,
    list_active_timers,
    list_running_apps,
    lock_workstation,
    media_control,
    open_application,
    optimize_system_memory,
    run_python_script,
    set_timer,
)
from tools.vision_tools import get_active_window_info, read_clipboard_text, take_screen_snapshot, write_clipboard_text
from tools.web_tools import open_browser_urls, open_url, play_youtube, read_web_page, search_google


def search_memory(query: str) -> str:
    """Searches past notes, instructions, and desktop context using semantic vector retrieval."""
    from core.vector_memory import vector_memory
    items = vector_memory.search(query, top_k=3)
    if not items:
        return f"No memories found matching '{query}', Sir."
    res = f"Found {len(items)} matching memory entries, Sir:\n"
    for idx, item in enumerate(items, 1):
        res += f"{idx}. [{item['domain'].upper()}] {item['content']}\n"
    return res.strip()


def search_clipboard_history(query: str) -> str:
    """Searches continuous temporal clipboard history for copied links, snippets, or errors."""
    from core.temporal_memory import temporal_memory
    items = temporal_memory.search_events(query, event_type="clipboard", limit=3)
    if not items:
        return f"No clipboard history found matching '{query}', Sir."
    res = f"Found {len(items)} matching clipboard items, Sir:\n"
    for idx, item in enumerate(items, 1):
        res += f"{idx}. [{item['time']}] {item['content'][:150]}\n"
    return res.strip()


def get_activity_timeline(minutes: int = 60) -> str:
    """Retrieves the recent workflow activity timeline (windows visited and clipboard items)."""
    from core.temporal_memory import temporal_memory
    items = temporal_memory.get_timeline(minutes=minutes, limit=10)
    if not items:
        return f"No activity recorded in the past {minutes} minutes yet, Sir."
    res = f"Activity Timeline (Past {minutes} minutes):\n"
    for item in items:
        res += f"• [{item['time']}] ({item['type']}) {item['title'][:80]}\n"
    return res.strip()


def toggle_ghost_mode(enable: bool = True) -> str:
    """Toggles Ghost Mode dual-plane background automation."""
    from core.ghost_mode import ghost_manager
    return ghost_manager.enable() if enable else ghost_manager.disable()


def get_ghost_mode_status() -> str:
    """Checks whether Ghost Mode background automation is active."""
    from core.ghost_mode import ghost_manager
    return ghost_manager.get_status()


# Tool execution mapping
TOOL_FUNCTIONS: dict[str, Callable] = {
    "create_folder": create_folder,
    "open_folder": open_folder,
    "create_file": create_file,
    "open_text_editor": open_text_editor,
    "list_desktop_files": list_desktop_files,
    "list_workspace_files": list_workspace_files,
    "read_file_content": read_file_content,
    "search_google": search_google,
    "play_youtube": play_youtube,
    "open_url": open_url,
    "open_browser_urls": open_browser_urls,
    "get_current_time": get_current_time,
    "open_application": open_application,
    "get_system_stats": get_system_stats,
    "activate_workspace_mode": activate_workspace_mode,
    "optimize_system_memory": optimize_system_memory,
    "media_control": media_control,
    "lock_workstation": lock_workstation,
    "empty_recycle_bin": empty_recycle_bin,
    "get_network_info": get_network_info,
    "list_running_apps": list_running_apps,
    "kill_process_by_name": kill_process_by_name,
    "set_timer": set_timer,
    "list_active_timers": list_active_timers,
    "gui_open_and_search_app": gui_open_and_search_app,
    "gui_search_google_browser": gui_search_google_browser,
    "gui_human_search_and_open": gui_human_search_and_open,
    "gui_open_browser_urls": gui_open_browser_urls,
    "gui_type_text": gui_type_text,
    "gui_play_youtube": gui_play_youtube,
    "gui_draw_in_paint": gui_draw_in_paint,
    "gui_click_text": gui_click_text,
    "gui_press_hotkey": lambda hotkeys: (
        __import__("core.host_bridge", fromlist=["host_bridge"]).host_bridge.press_host_hotkey(hotkeys if isinstance(hotkeys, list) else [hotkeys])
        and f"Dispatched hotkey combination: {hotkeys}"
        or f"Failed to dispatch hotkey combination: {hotkeys}"
    ),
    "set_system_brightness": lambda level=50, **kwargs: (
        __import__("tools.system_tools", fromlist=["set_system_brightness"]).set_system_brightness(level if level is not None else kwargs.get("brightness", 50))
    ),
    "gui_click_control": lambda target_name: __import__("core.uia_grounding", fromlist=["gui_click_control"]).gui_click_control(target_name),
    "gui_click_icon": lambda target_description: __import__("core.omniparser", fromlist=["omniparser"]).omniparser.gui_click_icon(target_description),
    "parse_screen_elements": lambda: str([(e.label, e.center, e.element_type) for e in __import__("core.omniparser", fromlist=["omniparser"]).omniparser.parse_screen()[:15]]),
    "ui_tars_navigate_and_act": lambda instruction: __import__("core.ui_tars", fromlist=["ui_tars_navigate_and_act"]).ui_tars_navigate_and_act(instruction),
    "ui_tars_computer_control": lambda instruction: __import__("core.ui_tars", fromlist=["ui_tars_navigate_and_act"]).ui_tars_navigate_and_act(instruction),
    "read_screen_text": read_screen_text,
    "browse_website_stealth": lambda url: __import__("tools.web_tools", fromlist=["browse_website_stealth"]).browse_website_stealth(url),
    "click_dom_element": lambda index: __import__("tools.web_tools", fromlist=["click_dom_element"]).click_dom_element(index),
    "type_dom_element": lambda index, text: __import__("tools.web_tools", fromlist=["type_dom_element"]).type_dom_element(index, text),
    "gui_click_som_index": lambda element_index: __import__("core.vision_grounding", fromlist=["gui_click_som_index"]).gui_click_som_index(element_index),

    "search_memory": search_memory,
    "search_clipboard_history": search_clipboard_history,
    "get_activity_timeline": get_activity_timeline,
    "toggle_ghost_mode": toggle_ghost_mode,
    "get_ghost_mode_status": get_ghost_mode_status,
    "scrape_jobs": scrape_jobs,
    "search_and_harvest_jobs": search_and_harvest_jobs,
    "track_career_application": track_career_application,
    "list_career_applications": list_career_applications,
    "prepare_job_application": prepare_job_application,
    "analyze_job_description": analyze_job_description,
    "tailor_careerflow_resume": tailor_careerflow_resume,
    "apply_to_job": apply_to_job,
    "create_career_goal": create_career_goal,
    "get_career_goal": get_career_goal,
    "activate_career_goal": activate_career_goal,
    "record_career_activity": record_career_activity,
    "update_career_plan_task": update_career_plan_task,
    "get_career_daily_review": get_career_daily_review,
    "create_career_reminder": create_career_reminder,
    "list_career_reminders": list_career_reminders,
    "cancel_career_reminder": cancel_career_reminder,
    "snooze_career_reminder": snooze_career_reminder,
    "list_career_opportunities": list_career_opportunities,
    "track_career_opportunity": track_career_opportunity,
    "delete_career_assistant_data": delete_career_assistant_data,
    "fetch_news_headlines": fetch_news_headlines,
    "get_weather": get_weather,
    "get_wikipedia_summary": get_wikipedia_summary,
    "get_active_window_info": get_active_window_info,
    "take_screen_snapshot": take_screen_snapshot,
    "read_clipboard_text": read_clipboard_text,
    "write_clipboard_text": write_clipboard_text,
    "scratchpad_set_plan": lambda steps: __import__("core.scratchpad", fromlist=["scratchpad_set_plan"]).scratchpad_set_plan(steps),
    "scratchpad_note": lambda key, value: __import__("core.scratchpad", fromlist=["scratchpad_note"]).scratchpad_note(key, value),
    "scratchpad_view": lambda: __import__("core.scratchpad", fromlist=["scratchpad_view"]).scratchpad_view(),
    "run_python_script": run_python_script,
    "execute_code_block": execute_code_block,
    "execute_terminal_command": execute_terminal_command,
    "execute_in_vscode_terminal": execute_in_vscode_terminal,
    "clone_public_repository": lambda repository_url, destination, approval_id="", approval_text="": __import__("tools.repo_tools", fromlist=["clone_public_repository"]).clone_public_repository(repository_url, destination, approval_id, approval_text),
    "detonate_in_sandbox": lambda command: __import__("tools.sandbox_tools", fromlist=["detonate_in_sandbox"]).detonate_in_sandbox(command),
    "create_sandbox_session": lambda task_description="", approval_id="", approval_text="": __import__("tools.sandbox_tools", fromlist=["create_sandbox_session"]).create_sandbox_session(task_description, approval_id, approval_text),
    "run_sandbox_session_command": lambda session_id, command: __import__("tools.sandbox_tools", fromlist=["run_sandbox_session_command"]).run_sandbox_session_command(session_id, command),
    "close_sandbox_session": lambda session_id: __import__("tools.sandbox_tools", fromlist=["close_sandbox_session"]).close_sandbox_session(session_id),
    "get_sandbox_status": lambda: __import__("tools.sandbox_tools", fromlist=["get_sandbox_status"]).get_sandbox_status(),
    "inspect_file_security": lambda file_path: __import__("tools.sandbox_tools", fromlist=["inspect_file_security"]).inspect_file_security(file_path),
    "run_sandboxed_workflow": lambda workflow_name="celesto_deployment_pipeline": __import__("tools.sandbox_tools", fromlist=["run_sandboxed_workflow"]).run_sandboxed_workflow(workflow_name),
    "get_run_ledger_summary": lambda: __import__("core.run_ledger", fromlist=["get_run_ledger_summary"]).get_run_ledger_summary(),
    "spacev_search_tools": lambda query="": __import__("core.code_mode", fromlist=["code_mode_engine"]).code_mode_engine.search_tools(query),
    "spacev_execute_script": lambda script="": __import__("core.code_mode", fromlist=["code_mode_engine"]).code_mode_engine.execute_script(script),
    "browse_interactive_dom": lambda url="": __import__("tools.web_tools", fromlist=["browse_interactive_dom"]).browse_interactive_dom(url),
    "read_web_page": read_web_page,
    "scrape_web_page_crawl4ai": lambda url="", **kwargs: __import__("tools.scraper_tools", fromlist=["scrape_web_page_crawl4ai"]).scrape_web_page_crawl4ai(url=url, **kwargs),
    "query_code_graph": lambda query, depth=2, **kwargs: __import__("core.code_graph_engine", fromlist=["code_graph_engine"]).code_graph_engine.query_graph(query, depth=depth),
    "get_code_node": lambda label, **kwargs: json.dumps(__import__("core.code_graph_engine", fromlist=["code_graph_engine"]).code_graph_engine.get_node(label)),
    "get_code_neighbors": lambda label, direction="both", **kwargs: json.dumps(__import__("core.code_graph_engine", fromlist=["code_graph_engine"]).code_graph_engine.get_neighbors(label, direction=direction)),
    "get_code_blast_radius": lambda symbol_or_path, depth=2, **kwargs: json.dumps(__import__("core.code_graph_engine", fromlist=["code_graph_engine"]).code_graph_engine.compute_blast_radius(symbol_or_path, depth=depth)),
}

# Resilient Canonical Tool Aliases (prevents model hallucination failures across providers)
TOOL_ALIASES: dict[str, str] = {
    # Natural names commonly emitted by models for an already-approved guest
    # command. These remain bound to the session tool, never the host shell.
    "run_guest_command": "run_sandbox_session_command",
    "execute_guest_command": "run_sandbox_session_command",
    "sandbox_command": "run_sandbox_session_command",
    "run_command_in_sandbox": "run_sandbox_session_command",
    "run_command_in_vm": "run_sandbox_session_command",
    "code_graph": "query_code_graph",
    "blast_radius": "get_code_blast_radius",
    "inspect_symbol": "get_code_node",
    "crawl4ai": "scrape_web_page_crawl4ai",
    "crawl4ai_scrape": "scrape_web_page_crawl4ai",
    "resilient_scrape": "scrape_web_page_crawl4ai",
    "adjust_brightness": "set_system_brightness",
    "change_brightness": "set_system_brightness",
    "dim_screen": "set_system_brightness",
    "brightness_control": "set_system_brightness",
    "open_editor": "open_text_editor",
    "text_editor": "open_text_editor",
    "edit_file": "open_text_editor",
    "write_code": "open_text_editor",
    "open_code_editor": "open_text_editor",
    "code_editor": "open_text_editor",
    "notepad": "open_text_editor",
    "youtube": "play_youtube",
    "google": "search_google",
    "search": "search_google",
    "list_project_files": "list_workspace_files",
    "list_files": "list_workspace_files",
    "workspace_files": "list_workspace_files",
    "project_files": "list_workspace_files",
    "read_file": "read_file_content",
    "view_file": "read_file_content",
    "read_web": "read_web_page",
    "read_url": "read_web_page",
    "read_page": "read_web_page",
    "fetch_web_page": "read_web_page",
    "get_repo_info": "read_web_page",
    "summarize_web_page": "read_web_page",
    "web_read": "read_web_page",
    "crawl_url": "read_web_page",
    "terminal": "execute_terminal_command",
    "calculator": "open_application",
    "search_tools": "spacev_search_tools",
    "execute_script": "spacev_execute_script",
    "execute_code": "execute_code_block",
    "run_code": "execute_code_block",
    "run_code_block": "execute_code_block",
    "execute_code_block": "execute_code_block",
    "run_script": "run_python_script",
    "run_python": "run_python_script",
    "execute_python": "run_python_script",
    "run_python_file": "run_python_script",
    "execute_python_file": "run_python_script",
    "python_script": "run_python_script",
    "run_command": "execute_terminal_command",
    "execute_command": "execute_terminal_command",
    "bash": "execute_terminal_command",
    "shell": "execute_terminal_command",
    "browse_dom": "browse_interactive_dom",
    "interactive_dom": "browse_interactive_dom",
    "vscode_terminal": "execute_in_vscode_terminal",
    "run_in_vscode_terminal": "execute_in_vscode_terminal",
    "run_in_vscode": "execute_in_vscode_terminal",
    "execute_in_vscode": "execute_in_vscode_terminal",
    "clone_repo": "clone_public_repository",
    "git_clone": "clone_public_repository",
    "install_package": "detonate_in_sandbox",
    "run_untrusted": "detonate_in_sandbox",
    "sandbox_detonate": "detonate_in_sandbox",
    "verify_file_security": "inspect_file_security",
    "scan_file_security": "inspect_file_security",
    "check_file_security": "inspect_file_security",
    "harvest_jobs": "search_and_harvest_jobs",
    "search_jobs": "search_and_harvest_jobs",
    "find_jobs": "search_and_harvest_jobs",
    "job_search": "search_and_harvest_jobs",
    "apply_job": "track_career_application",
    "track_job": "track_career_application",
    "track_application": "track_career_application",
    "list_applications": "list_career_applications",
    "get_applications": "list_career_applications",
    "application_status": "list_career_applications",
    "draft_application": "prepare_job_application",
    "prepare_application": "prepare_job_application",
    "analyze_jd": "analyze_job_description",
    "parse_jd": "analyze_job_description",
    "tailor_resume": "tailor_careerflow_resume",
    "careerflow_tailor": "tailor_careerflow_resume",
    "apply_job_wingman": "apply_to_job",
    "submit_application": "apply_to_job",
    "open_urls": "open_browser_urls",
    "open_links": "open_browser_urls",
    "batch_open_urls": "open_browser_urls",
    "open_all_urls": "open_browser_urls",
    "open_all_links": "open_browser_urls",
    "open_tabs": "open_browser_urls",
    "human_search": "gui_human_search_and_open",
    "human_search_and_open": "gui_human_search_and_open",
    "search_and_open": "gui_human_search_and_open",
    "browse_and_open": "gui_human_search_and_open",
}

# Standard Ollama JSON Tool Schemas
OLLAMA_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": "Creates a new folder on the Windows desktop or specified path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_name": {
                        "type": "string",
                        "description": "The name of the new folder to create."
                    },
                    "location": {
                        "type": "string",
                        "description": "Location to create folder in (defaults to 'Desktop')."
                    }
                },
                "required": ["folder_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_folder",
            "description": "Opens a folder in Windows File Explorer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_path": {
                        "type": "string",
                        "description": "Path or folder to open (e.g., 'Desktop', 'Downloads', or specific folder path)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Creates a new text or code file with optional content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "The name of the file to create (e.g., 'notes.txt', 'script.py')."
                    },
                    "content": {
                        "type": "string",
                        "description": "The text or code content to write inside the file."
                    },
                    "location": {
                        "type": "string",
                        "description": "Location to save the file (defaults to 'Desktop')."
                    }
                },
                "required": ["file_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_text_editor",
            "description": "Opens a desktop text editor (e.g. Notepad, VS Code, Gedit) and writes code or notes into the specified file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "The name or path of the file to create and edit (e.g., 'script.py', 'notes.txt'). Default is 'notes.txt'."
                    },
                    "content": {
                        "type": "string",
                        "description": "The text or code content to write inside the file."
                    },
                    "editor": {
                        "type": "string",
                        "description": "The text editor application to launch (e.g. 'notepad', 'code', 'gedit'). Defaults to 'notepad'."
                    },
                    "location": {
                        "type": "string",
                        "description": "Location to save the file (defaults to 'Desktop')."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_desktop_files",
            "description": "Lists the files and folders currently on the user's Desktop.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_workspace_files",
            "description": "Lists the files and directories inside the active SpaceV project workspace, excluding cache, virtual environments, and internal tracking folders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subfolder": {
                        "type": "string",
                        "description": "Optional subfolder within the workspace to list files from."
                    },
                    "max_files": {
                        "type": "integer",
                        "description": "Maximum number of files to return (defaults to 50)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_google",
            "description": "Opens the default browser and performs a Google search for the query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search term or question to search on Google."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_youtube",
            "description": "Searches for and plays a music track or video on YouTube in the web browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_query": {
                        "type": "string",
                        "description": "The name of the song, artist, video title, or topic to play on YouTube."
                    }
                },
                "required": ["video_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Opens any web address in the user's web browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full website URL to open (e.g. 'github.com', 'reddit.com')."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_browser_urls",
            "description": "Opens multiple website URLs sequentially in the user's default browser (Chrome/Edge/Firefox) tabs with smooth pacing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of URLs to open in new browser tabs."
                    },
                    "delay_sec": {
                        "type": "number",
                        "description": "Delay in seconds between opening tabs (default 0.5s)."
                    }
                },
                "required": ["urls"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Gets the current system date, time, and day of week.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Launches a Windows application on the computer like Calculator, Notepad, Chrome, VS Code, Paint, Task Manager.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "The name of the application to open (e.g. 'calculator', 'notepad', 'chrome', 'paint', 'vscode')."
                    }
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_stats",
            "description": "Gets the current computer system health metrics (CPU usage, RAM memory usage, Battery status).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_open_and_search_app",
            "description": "Autonomously controls the mouse and keyboard to visibly click the Windows Start menu, type the application name, launch it, and optionally type text inside it like a human.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "The application to search and open (e.g. 'notepad', 'calculator', 'paint')."
                    },
                    "text_to_type": {
                        "type": "string",
                        "description": "Optional text to type inside the opened app (e.g. notes, shopping list)."
                    }
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_search_google_browser",
            "description": "Visibly opens the browser using cursor movements, navigates to the address bar, and types the Google search query like a human.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search term to type into Google."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_type_text",
            "description": "Types text at the current cursor position with human-like typing speed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to type."
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_play_youtube",
            "description": "Autonomously glides the mouse cursor to open Chrome, types YouTube search URL, and clicks the top video result to start playing music/video like a human.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_query": {
                        "type": "string",
                        "description": "The song name, video title, or artist to search and play on YouTube."
                    }
                },
                "required": ["video_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_jobs",
            "description": "Searches jobs using a role and location stated by the user. If either is missing or nothing matches, ask rather than assuming defaults or loosening filters. CSV export is opt-in.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "Role from the user; if missing, ask instead of guessing."
                    },
                    "location": {
                        "type": "string",
                        "description": "Target location/work mode from the user; do not assume remote."
                    },
                    "save_to_desktop": {
                        "type": "boolean",
                        "description": "Export to Desktop only when the user explicitly asks."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_career_goal",
            "description": "Save a user's career goal and proposed dated plan as a draft. First clarify target roles, location/work mode, deadline, and daily available time when missing. Draft realistic editable tasks from the conversation; show the plan and wait for explicit user approval before calling activate_career_goal; never promise a job outcome.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "target_roles": {"type": "array", "items": {"type": "string"}},
                    "location": {"type": "string"},
                    "deadline": {"type": "string", "description": "YYYY-MM-DD"},
                    "duration_days": {"type": "integer", "description": "Relative deadline in days if the user said, for example, 'in 20 days'."},
                    "available_hours": {"type": "number", "description": "Realistic hours available on a typical day."},
                    "resume_path": {"type": "string", "description": "Optional path to a real resume file provided by the user."},
                    "plan_items": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "due_date": {"type": "string"}, "estimated_minutes": {"type": "integer"}, "category": {"type": "string"}}, "required": ["title", "due_date"]}}
                },
                "required": []
            }
        }
    },
    {"type": "function", "function": {"name": "get_career_goal", "description": "Read the active saved career goal and its dated tasks.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "activate_career_goal", "description": "Activate a saved draft career goal only after the user has reviewed the dated plan and explicitly said to start it.", "parameters": {"type": "object", "properties": {"goal_id": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "record_career_activity", "description": "Record only an activity the user explicitly says they completed. Do not infer progress from screen, app, or clipboard data. Link task_id when the user identifies a plan task.", "parameters": {"type": "object", "properties": {"activity": {"type": "string"}, "minutes": {"type": "integer"}, "task_id": {"type": "string"}, "notes": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "update_career_plan_task", "description": "Edit a dated task from the active career plan. Use the task_id returned by get_career_goal; change only fields the user asked to change.", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}, "title": {"type": "string"}, "due_date": {"type": "string"}, "estimated_minutes": {"type": "integer"}, "status": {"type": "string", "description": "planned, completed, paused, or cancelled"}}, "required": []}}},
    {"type": "function", "function": {"name": "get_career_daily_review", "description": "Compare today's dated tasks with user-confirmed activity and identify due, overdue, and upcoming items. State clearly that unreported work is unknown, not necessarily undone.", "parameters": {"type": "object", "properties": {"day": {"type": "string", "description": "Optional date in YYYY-MM-DD."}}, "required": []}}},
    {"type": "function", "function": {"name": "create_career_reminder", "description": "Save a persistent local reminder for a job application, follow-up, study session, or check-in. Ask for date/time and timezone if unclear. For a scheduled goal progress check-in, set purpose=daily_review. Repeat rule: none, daily, weekdays, weekly. Repeating reminders require an IANA timezone such as Asia/Kolkata.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "due_at": {"type": "string", "description": "ISO datetime; include a UTC offset unless timezone_name is supplied."}, "repeat_rule": {"type": "string"}, "goal_id": {"type": "string"}, "purpose": {"type": "string", "description": "notification or daily_review."}, "timezone_name": {"type": "string", "description": "IANA timezone for recurring reminders, e.g. Asia/Kolkata."}}, "required": []}}},
    {"type": "function", "function": {"name": "list_career_reminders", "description": "List saved career reminders and their due times/status.", "parameters": {"type": "object", "properties": {"include_completed": {"type": "boolean"}}, "required": []}}},
    {"type": "function", "function": {"name": "cancel_career_reminder", "description": "Cancel a saved reminder by reminder_id.", "parameters": {"type": "object", "properties": {"reminder_id": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "snooze_career_reminder", "description": "Move a saved reminder to a new timezone-aware date/time.", "parameters": {"type": "object", "properties": {"reminder_id": {"type": "string"}, "due_at": {"type": "string", "description": "ISO datetime with timezone offset."}}, "required": []}}},
    {"type": "function", "function": {"name": "list_career_opportunities", "description": "List persisted job opportunities harvested by SpaceV; stored records include when the source was last checked, not a guarantee that a job is still open.", "parameters": {"type": "object", "properties": {"status": {"type": "string", "description": "new, wishlist, shortlisted, preparing, applied, interview, offer, rejected, or closed; empty for all."}, "limit": {"type": "integer"}, "opportunity_type": {"type": "string", "description": "Optional job, internship, or hackathon filter."}}, "required": []}}},
    {"type": "function", "function": {"name": "track_career_opportunity", "description": "Save a user-provided opportunity link as a job, internship, or hackathon. Ask for missing title, URL, or type; do not claim the link is active unless verified.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "url": {"type": "string"}, "opportunity_type": {"type": "string", "description": "job, internship, or hackathon"}, "company": {"type": "string"}, "location": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "delete_career_assistant_data", "description": "Permanently delete locally saved career goals, plan tasks, progress events, reminders, job leads, and application tracker. Always ask for explicit user confirmation before confirm=true.", "parameters": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": []}}},
    {
        "type": "function",
        "function": {
            "name": "search_and_harvest_jobs",
            "description": "Searches job sources using the user's stated role and location. Never assume a role/location or relax filters silently. If either is missing or no matching jobs are found, return a clarification question. CSV export is opt-in.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "Role/keywords from the user. Leave empty if missing so SpaceV can ask; do not invent a role."
                    },
                    "location": {
                        "type": "string",
                        "description": "Target location/work mode from the user. Leave empty if missing so SpaceV can ask; do not assume remote."
                    },
                    "min_exp": {
                        "type": "integer",
                        "description": "Minimum years of experience filter (0 for freshers / entry-level)."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of listings to return (default 10)."
                    },
                    "save_to_desktop": {
                        "type": "boolean",
                        "description": "Export to a Desktop CSV only if the user explicitly asks."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_job_description",
            "description": "Fetches and reports the available full job description without inventing details. Optionally compares detected job skills against an actual resume file. If page details or resume input are unavailable, asks the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url_or_text": {"type": "string", "description": "Public job listing URL or pasted job description."},
                    "resume_path": {"type": "string", "description": "Path to the user's real .pdf/.docx/.txt/.md resume when comparing."},
                    "compare_resume": {"type": "boolean", "description": "Set true when the user asks for a resume comparison; if no resume path was provided, SpaceV will ask for it."}
                },
                "required": ["url_or_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "track_career_application",
            "description": "Tracks a job application in the local Career ATS Kanban pipeline (.spacev/career_applications.jsonl). Stages: Wishlist, Applied, Interview, Offer, Rejected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_title": {
                        "type": "string",
                        "description": "The job title or role applied for."
                    },
                    "company": {
                        "type": "string",
                        "description": "The company name."
                    },
                    "job_url": {
                        "type": "string",
                        "description": "URL to the job posting or application link."
                    },
                    "status": {
                        "type": "string",
                        "description": "Stage in the pipeline: 'Wishlist', 'Applied', 'Interview', 'Offer', or 'Rejected'."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes or details about the application."
                    }
                },
                "required": ["job_title", "company"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_career_applications",
            "description": "Lists all tracked job applications from the local Career ATS Kanban, grouped by status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "description": "Optional status filter ('Wishlist', 'Applied', 'Interview', 'Offer', 'Rejected')."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_job_application",
            "description": "Prepares a tailored job application pitch, cold email cover letter, and candidate qualification highlights.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_title": {
                        "type": "string",
                        "description": "The target job title."
                    },
                    "company": {
                        "type": "string",
                        "description": "The company name."
                    },
                    "candidate_name": {
                        "type": "string",
                        "description": "Applicant's name."
                    },
                    "skills": {
                        "type": "string",
                        "description": "Key skills or projects to highlight in the application."
                    }
                },
                "required": ["job_title", "company"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_news_headlines",
            "description": "Fetches the latest top news stories and technology headlines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic or industry to fetch news for (e.g. 'technology', 'ai', 'crypto')."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Gets current weather conditions, temperature, humidity, and wind speed for any city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "The name of the city to get weather for (e.g. 'London', 'New York', 'Tokyo')."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_wikipedia_summary",
            "description": "Searches Wikipedia and returns a factual, concise summary of any concept, person, country, or event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The topic or query to summarize from Wikipedia."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_window_info",
            "description": "Perceives and reports what active window, app, or document the user is currently looking at.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screen_snapshot",
            "description": "Takes a full screen snapshot and saves it as an image to the user's Desktop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Filename for screenshot (e.g. 'screen.png')."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_clipboard_text",
            "description": "Reads text or code currently copied to the user's Windows clipboard.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_clipboard_text",
            "description": "Copies text, code snippets, or notes directly onto the Windows clipboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text or code to copy to clipboard."
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_content",
            "description": "Reads and inspects the contents of a text or code file on the Desktop or custom location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name_or_path": {
                        "type": "string",
                        "description": "The name or path of the file to read (e.g. 'notes.txt', 'script.py')."
                    },
                    "location": {
                        "type": "string",
                        "description": "Location of the file (defaults to 'Desktop')."
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Maximum number of lines to return (1-400; defaults to 40)."
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "1-based line number to begin reading from (defaults to 1)."
                    }
                },
                "required": ["file_name_or_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "activate_workspace_mode",
            "description": "Activates preset workflow modes ('coding', 'research', 'focus').",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "description": "The mode to activate (e.g. 'coding', 'research', 'focus')."
                    }
                },
                "required": ["mode"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_system_memory",
            "description": "Flushes system memory handles and performs garbage collection to free RAM.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "media_control",
            "description": "Controls audio playback and volume via physical Windows media keys (play, pause, next, previous, mute, volume_up, volume_down).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "The media action: 'play', 'pause', 'next', 'previous', 'mute', 'volume_up', or 'volume_down'."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lock_workstation",
            "description": "Immediately locks the Windows computer workstation.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "empty_recycle_bin",
            "description": "Empties and purges the Windows Recycle Bin.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_info",
            "description": "Reports local IP address, hostname, and internet connection diagnostics.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_running_apps",
            "description": "Lists currently open active applications and high RAM processes.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process_by_name",
            "description": "Terminates any frozen or unwanted application by name (e.g. 'notepad', 'calc').",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_name": {
                        "type": "string",
                        "description": "The application or process name to close (e.g. 'notepad', 'calc')."
                    }
                },
                "required": ["process_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Sets a countdown timer for a specified duration in minutes with a label or message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {
                        "type": "number",
                        "description": "The duration of the timer in minutes (e.g. 5, 0.5, 15)."
                    },
                    "label": {
                        "type": "string",
                        "description": "The title or reminder note for the timer (e.g. 'Tea', 'Team Meeting', 'Drink Water')."
                    }
                },
                "required": ["minutes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_active_timers",
            "description": "Lists all currently active countdown timers and their remaining times.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_draw_in_paint",
            "description": "Autonomously opens MS Paint, maximizes the window, and draws illustrations, diagrams, or shapes (house, heart, star, smiley face, car, tree, sun, rocket, cat, flower, sailboat) using pure human-like mouse cursor movements with a glowing real-time HUD.",
            "parameters": {
                "type": "object",
                "properties": {
                    "shape_or_prompt": {
                        "type": "string",
                        "description": "The shape, diagram, or object to draw (e.g. 'house', 'heart', 'star', 'smiley face', 'car', 'tree', 'sun', 'rocket', 'cat', 'flower', 'sailboat')."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_click_text",
            "description": "Visually locates any button label, text, or link on screen using Windows Native OCR and clicks it with precision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_text": {
                        "type": "string",
                        "description": "The exact or approximate word, button label, or link to visually find on screen and click."
                    }
                },
                "required": ["target_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_screen_text",
            "description": "Performs full-screen OCR transcription, reading and returning all visible on-screen text.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Searches past user notes, instructions, and desktop context using semantic vector full-text retrieval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords or topic to search across past notes and preferences."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ui_tars_navigate_and_act",
            "description": "Autonomous GUI computer control and mouse navigation powered by UI-TARS (OSWorld SOTA). Takes a visual desktop screenshot and executes grounded mouse clicks, typing, or shortcuts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": "Natural language instruction of what UI element to navigate, click, or manipulate on screen."
                    }
                },
                "required": ["instruction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scratchpad_set_plan",
            "description": "Initializes or updates the agent's multi-step execution plan and checklist in working memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of clear, sequential step descriptions to complete the complex user goal."
                    }
                },
                "required": ["steps"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scratchpad_note",
            "description": "Stores an intermediate fact, URL, window handle, or extracted variable into the agent's working memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Identifier name (e.g. 'downloaded_file', 'current_url', 'target_window')."
                    },
                    "value": {
                        "type": "string",
                        "description": "The information or variable content to remember."
                    }
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scratchpad_view",
            "description": "Inspects the current agent scratchpad, plan progress, and working memory notes.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clone_public_repository",
            "description": "Approval-gated, source-only clone of a public GitHub repository to a new absolute destination outside the SpaceV project. First call only presents the exact URL/path and waits for user approval; second call requires the same URL/path, returned approval_id, and exact user approval_text. It does not install dependencies or run repository code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repository_url": {"type": "string", "description": "Public HTTPS GitHub URL in owner/repository form."},
                    "destination": {"type": "string", "description": "New absolute checkout directory outside the SpaceV project."},
                    "approval_id": {"type": "string", "description": "Empty for the proposal call; use the returned ID only after the user approves."},
                    "approval_text": {"type": "string", "description": "After approval, pass the exact user phrase: approve clone <approval_id>."}
                },
                "required": ["repository_url", "destination"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detonate_in_sandbox",
            "description": "Runs a command in a disposable real Celesto computer selected by CELESTO_PROVIDER and CELESTO_BACKEND in .env, when get_sandbox_status reports it ready. Set CELESTO_PROVIDER=simulation to disable real execution. Never treat simulation output as proof of execution or containment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to run in the configured Celesto computer; simulation mode executes no command."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_sandbox_session",
            "description": "Proposes a task-scoped reusable Celesto VM. First call requires task_description and only asks for approval. After the user supplies the exact approval phrase, call again with approval_id and approval_text; task_description may be omitted because the exact approved task is loaded from the pending approval record. Any task_description sent on approval is ignored in favor of the stored task. Reuse the returned session_id for commands, then close it. One active session maximum; 15-minute idle timeout and 1-hour maximum lifetime.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {"type": "string", "description": "Required for the proposal call (8-800 characters). On approval, the task stored for approval_id is authoritative; this field may be omitted."},
                    "approval_id": {"type": "string", "description": "Empty to propose the task; use the returned ID only after approval."},
                    "approval_text": {"type": "string", "description": "After user approval, exact phrase: approve sandbox task <approval_id>."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_sandbox_session_command",
            "description": "Executes one audited command inside an existing approved Celesto VM without creating a new VM. Use this for guest commands even if the user calls it a sandbox command, guest command, or VM command. For missing executables/package managers, inspect /etc/os-release in this same session; never fall back to the host or assume apt/apk. Returns command and cumulative session timings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID returned by create_sandbox_session."},
                    "command": {"type": "string", "description": "One command for the approved task; max 10000 characters."}
                },
                "required": ["session_id", "command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_sandbox_session",
            "description": "Deletes an active approved Celesto session and reports VM startup, command, cleanup, and total task timings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID returned by create_sandbox_session."}
                },
                "required": ["session_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sandbox_status",
            "description": "Read-only diagnostic: reports whether the sandbox tool is registered, which backend is wired, and whether the Celesto SDK/configuration appear ready. Does not start a VM or execute commands.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_file_security",
            "description": "Performs sub-millisecond Google Magika deep learning content-type inspection to verify file safety and detect masqueraded malware (e.g. ELF/PE disguised as .png, .csv, .txt).",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the target file to inspect with Google Magika neural network."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_sandboxed_workflow",
            "description": "Runs a deterministic sandbox workflow simulation. It does not start a real Celesto VM; use get_sandbox_status for the current backend diagnostic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_name": {
                        "type": "string",
                        "description": "The name or identifier of the workflow."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "audit_sandbox_containment",
            "description": "Runs a containment simulation and writes simulation-only evidence. It does not prove real Celesto VM isolation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "attack_type": {
                        "type": "string",
                        "description": "The attack vector: 'prompt_injection_exfil', 'destructive_command', or 'suspicious_package'."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_run_ledger_summary",
            "description": "Inspects the active Celesto microVM sandbox run ledger and evaluation benchmark statistics (success rate, median latency, p90 wall clock).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spacev_search_tools",
            "description": "Searches the SpaceV dynamic tool registry for capabilities matching a query. Returns tool signatures on demand (Cloudflare Code Mode).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords describing the capability needed (e.g. 'web scrape', 'bash command', 'create file')"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spacev_execute_script",
            "description": "Executes a sandboxed Python script to orchestrate SpaceV tools without multiple conversational roundtrips. Access tools via 'tools.<tool_name>(**kwargs)'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": "Python script invoking tools.<name>() and printing or storing final results."
                    }
                },
                "required": ["script"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browse_interactive_dom",
            "description": "Navigates to URL and returns an indexed semantic DOM tree [1], [2], [3] for high-precision, coordinate-free autonomous interaction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Target webpage URL to navigate to and inspect."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_code_block",
            "description": "Executes a block of Python or Bash code directly on the machine with automatic file persistence, stdin input, and stdout/stderr capture.",
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "description": "Runtime language: 'python' or 'bash'."
                    },
                    "code": {
                        "type": "string",
                        "description": "The script source code to execute."
                    },
                    "file_name": {
                        "type": "string",
                        "description": "Optional filename to save the code to (e.g. 'reverse_number.py')."
                    },
                    "input_data": {
                        "type": "string",
                        "description": "Optional stdin string to pass to interactive script inputs."
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_python_script",
            "description": "Executes a Python program or script file on the local machine and returns the execution output and exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name_or_path": {
                        "type": "string",
                        "description": "The name or path of the Python script to execute (e.g. 'reverse_number.py', 'Desktop/reverse_number.py')."
                    },
                    "args": {
                        "type": "string",
                        "description": "Optional CLI arguments or inputs to pass to the Python script."
                    }
                },
                "required": ["file_name_or_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_terminal_command",
            "description": "Executes a shell or terminal command directly on the host operating system with timeout protection and returns captured output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command line string to execute in the terminal (e.g. 'python reverse_number.py', 'pip list')."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_in_vscode_terminal",
            "description": "Opens and executes a script or command directly in the Visual Studio Code integrated terminal workstation environment, ensuring output is visible in the editor window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command or script file to run in the VS Code terminal (e.g. 'python3 reverse_number.py 1234555')."
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional file path to open in VS Code editor before running."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_web_page",
            "description": "Fetches, distills, and returns the full readable text, documentation, and markdown content of any website, documentation page, or GitHub repository. Use this whenever the user wants to read, summarize, or know what is inside a URL or project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The web URL or GitHub repository link to read and summarize (e.g. 'https://github.com/unclecode/crawl4AI')."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_system_brightness",
            "description": "Adjusts the primary display screen brightness level directly (0 to 100%) via native OS hardware interface without opening GUI applications.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "description": "Brightness percentage level from 0 to 100 (e.g. 50, 75, 100)."
                    }
                },
                "required": ["level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_web_page_crawl4ai",
            "description": "High-throughput resilient web extraction inspired by crawl4ai. Fetches URL and distills semantic Markdown, stripping boilerplate without browser overhead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The target website URL to scrape and distill."
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum character limit for distilled content (default 12000)."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_code_graph",
            "description": "Performs zero-token AST semantic graph search to answer questions about functions, classes, calls, and codebase topology.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The natural language question or symbol to locate in the code graph."
                    },
                    "depth": {
                        "type": "integer",
                        "description": "BFS traversal depth from seed nodes (default 2)."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_code_node",
            "description": "Inspects structural details of a function, class, or module in the codebase including exact file location and degree.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Symbol name (e.g. 'TruthGatekeeper', 'query_graph') or file path."
                    }
                },
                "required": ["label"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_code_neighbors",
            "description": "Inspects incoming and outgoing callers, dependencies, or definitions for a given symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Symbol name to query."
                    },
                    "direction": {
                        "type": "string",
                        "description": "Direction to traverse: 'in' (callers), 'out' (callees), or 'both'."
                    }
                },
                "required": ["label"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_code_blast_radius",
            "description": "Computes the downstream blast radius and impacted test suites for any modified symbol or file before running tests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_or_path": {
                        "type": "string",
                        "description": "The function name, class name, or file path being modified."
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Reverse traversal depth (default 2)."
                    }
                },
                "required": ["symbol_or_path"]
            }
        }
    }
]


def execute_tool_normalized(tool_name: str, arguments: dict[str, Any]) -> Any:
    """
    Executes a registered tool function and returns a standardized ToolResult envelope.
    Tags execution environment (host_process vs celesto_microvm) and enforces strict validation.
    """
    import time
    from datetime import datetime, timezone
    from tools.schemas import ToolResult

    t_start = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    canonical_name = TOOL_ALIASES.get(tool_name, tool_name)
    func = TOOL_FUNCTIONS.get(canonical_name)

    if canonical_name in {
        "get_sandbox_status", "create_sandbox_session", "run_sandbox_session_command", "close_sandbox_session"
    }:
        env = "sandbox_control_plane"
    elif canonical_name in SANDBOX_EXECUTION_TOOL_NAMES:
        env = "sandbox_simulator"
    else:
        env = "host_process"

    if not func:
        return ToolResult(
            success=False,
            status="invocation_error",
            error=f"Error: Tool '{tool_name}' is not recognized.",
            metadata={"environment": env, "tool_name": tool_name}
        )

    try:
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except Exception:
                arguments = {}

        if not isinstance(arguments, dict):
            arguments = {}

        # Validate & Coerce arguments using Pydantic Schema if available
        from tools.schemas import PYDANTIC_TOOL_MODELS
        schema_cls = PYDANTIC_TOOL_MODELS.get(canonical_name)
        if schema_cls:
            try:
                validated_model = schema_cls(**arguments)
                arguments = validated_model.model_dump()
            except Exception as val_err:
                err_str = f"Invalid arguments for tool '{tool_name}': {val_err}"
                # If required field is missing completely, return invocation_error
                if "Field required" in str(val_err) or "validation error" in str(val_err).lower():
                    return ToolResult(
                        success=False,
                        status="invocation_error",
                        error=f"Error: {err_str}",
                        metadata={"environment": env, "tool_name": tool_name}
                    )
                print(f"[Pydantic] Coercion note for {tool_name}: {val_err}")

        result = func(**arguments)
        dur_s = time.perf_counter() - t_start
        finished_at = datetime.now(timezone.utc).isoformat()
        res_str = str(result)

        if canonical_name == "run_sandbox_session_command" and res_str.startswith("[CELESTO SESSION EXECUTION]"):
            env = "celesto_microvm"
        elif canonical_name == "detonate_in_sandbox":
            if res_str.startswith("[CELESTO SDK EXECUTION]"):
                env = "celesto_microvm"
            elif "SIMULATION ONLY" in res_str:
                env = "sandbox_simulator"

        needs_input = res_str.startswith("SPACEV_NEEDS_USER_INPUT:")
        is_failed = res_str.startswith(("Error:", "Failed:", "BLOCKED:", "Folder does not exist:"))
        # Sandbox helpers return structured human-readable receipts. Treat a
        # non-zero guest exit or failed VM deletion as a failed tool call too.
        if canonical_name in {"detonate_in_sandbox", "run_sandbox_session_command"}:
            exit_code_match = re.search(r"\bexit code:\s*(-?\d+)", res_str, flags=re.IGNORECASE)
            if exit_code_match and int(exit_code_match.group(1)) != 0:
                is_failed = True
        if re.search(r"\b(?:cleanup_state|state):\s*cleanup_failed\b", res_str, flags=re.IGNORECASE):
            is_failed = True
        status = "needs_input" if needs_input else ("failed" if is_failed else "success")

        return ToolResult(
            success=not is_failed and not needs_input,
            status=status,
            data=res_str,
            error=res_str if is_failed else None,
            started_at=started_at,
            finished_at=finished_at,
            metadata={"environment": env, "duration_s": dur_s, "tool_name": canonical_name}
        )
    except TypeError as e:
        try:
            result = func()
            dur_s = time.perf_counter() - t_start
            return ToolResult(
                success=True,
                status="success",
                data=str(result),
                metadata={"environment": env, "duration_s": dur_s, "tool_name": canonical_name}
            )
        except Exception as fallback_err:
            return ToolResult(
                success=False,
                status="execution_error",
                error=f"Error executing tool '{tool_name}': {fallback_err!s}",
                metadata={"environment": env, "tool_name": canonical_name}
            )
    except Exception as e:
        return ToolResult(
            success=False,
            status="execution_error",
            error=f"Error executing tool '{tool_name}': {e!s}",
            metadata={"environment": env, "tool_name": canonical_name}
        )


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    """
    Executes a registered tool function with Pydantic validation and type coercion.
    Returns normalized string representation for backward compatibility.
    """
    normalized = execute_tool_normalized(tool_name, arguments)
    return str(normalized)


SANDBOX_SESSION_TOOL_NAMES = {
    "get_sandbox_status",
    "create_sandbox_session",
    "run_sandbox_session_command",
    "close_sandbox_session",
}

CORE_TOOL_NAMES = {
    "create_file", "read_file_content", "run_python_script", "execute_code_block",
    "execute_terminal_command", "list_workspace_files", "scratchpad_view",
    "scratchpad_note", "scratchpad_set_plan", "spacev_search_tools", "spacev_execute_script"
}

GUI_TOOL_NAMES = {
    "gui_open_and_search_app", "gui_type_text", "gui_draw_in_paint", "gui_click_text",
    "gui_press_hotkey", "get_active_window_info", "take_screen_snapshot", "read_clipboard_text",
    "write_clipboard_text", "read_screen_text", "ui_tars_navigate_and_act", "gui_click_control",
    "gui_click_icon", "parse_screen_elements", "gui_click_som_index"
}

WEB_TOOL_NAMES = {
    "search_google", "play_youtube", "open_url", "open_browser_urls", "gui_search_google_browser",
    "gui_play_youtube", "scrape_jobs", "fetch_news_headlines", "get_weather",
    "get_wikipedia_summary", "browse_interactive_dom", "read_web_page",
    "browse_website_stealth", "click_dom_element", "type_dom_element", "scrape_web_page_crawl4ai"
}

SANDBOX_TOOL_NAMES = {
    "detonate_in_sandbox", "create_sandbox_session", "run_sandbox_session_command", "close_sandbox_session",
    "run_sandboxed_workflow", "audit_sandbox_containment",
    "get_run_ledger_summary", "get_sandbox_status"
}

SANDBOX_EXECUTION_TOOL_NAMES = {
    "detonate_in_sandbox", "run_sandboxed_workflow", "audit_sandbox_containment"
}

CAREER_TOOL_NAMES = {
    "search_and_harvest_jobs", "track_career_application", "list_career_applications",
    "prepare_job_application", "scrape_jobs", "analyze_job_description",
    "tailor_careerflow_resume", "apply_to_job", "create_career_goal", "get_career_goal", "activate_career_goal",
    "record_career_activity", "update_career_plan_task", "get_career_daily_review", "create_career_reminder",
    "list_career_reminders", "cancel_career_reminder", "snooze_career_reminder",
    "list_career_opportunities", "track_career_opportunity", "delete_career_assistant_data"
}

CODE_TOOL_NAMES = {
    "query_code_graph", "get_code_node", "get_code_neighbors", "get_code_blast_radius",
    "clone_public_repository"
}

SYSTEM_TOOL_NAMES = {
    "create_folder", "open_folder", "open_text_editor", "list_desktop_files",
    "get_current_time", "open_application", "get_system_stats", "activate_workspace_mode",
    "optimize_system_memory", "media_control", "lock_workstation", "empty_recycle_bin",
    "get_network_info", "list_running_apps", "kill_process_by_name", "set_timer",
    "list_active_timers", "search_memory", "search_clipboard_history", "get_activity_timeline",
    "toggle_ghost_mode", "get_ghost_mode_status", "set_system_brightness"
}

DEFAULT_ESSENTIAL_TOOL_NAMES = {
    "create_folder", "list_desktop_files", "get_active_window_info", "search_google"
}


def get_scoped_tools(prompt: str = "", all_tools: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """
    Dynamically scopes tool schemas based on the intent of the prompt.
    Drastically reduces token payload per turn (from ~3,500 down to 600-900 tokens),
    preventing 6,000 TPM rate limits on cloud providers (Groq, Cerebras, OpenRouter).
    """
    source_tools = all_tools if all_tools is not None else OLLAMA_TOOLS_SCHEMA
    if not source_tools:
        return []

    # If already a small slice (< 16 tools), keep as-is
    if len(source_tools) <= 15:
        return source_tools

    p = (prompt or "").lower()
    selected_names = set(CORE_TOOL_NAMES) | SANDBOX_SESSION_TOOL_NAMES
    category_matched = False
    sandbox_matched = False

    # GUI / Vision
    gui_keywords = ["screen", "click", "mouse", "type", "press", "hotkey", "window", "gui", "paint", "draw", "clipboard", "desktop", "icon", "uia", "tars"]
    if any(k in p for k in gui_keywords):
        selected_names.update(GUI_TOOL_NAMES)
        category_matched = True

    # Web / Search / Scraper
    web_keywords = ["web", "search", "google", "browser", "youtube", "scrape", "crawl", "url", "http", "download", "weather", "news", "wikipedia", "job"]
    if any(k in p for k in web_keywords):
        selected_names.update(WEB_TOOL_NAMES)
        category_matched = True

    # Sandbox / Containment
    sandbox_keywords = ["sandbox", "celesto", "isolate", "detonate", "containment", "untrusted", "docker", "ledger"]
    if any(k in p for k in sandbox_keywords):
        selected_names.update(SANDBOX_TOOL_NAMES)
        category_matched = True
        sandbox_matched = True

    # Career / Job Search / Application Intelligence
    career_keywords = ["job", "career", "apply", "resume", "application", "interview", "hiring", "recruit", "internship", "wishlist", "goal", "progress", "reminder", "milestone", "check-in", "checkin", "career plan", "plan task"]
    if any(k in p for k in career_keywords):
        selected_names.update(CAREER_TOOL_NAMES)
        category_matched = True

    # Code Intelligence / AST Graph / Blast Radius
    code_keywords = ["graph", "ast", "blast", "impact", "callers", "callees", "codebase", "architecture", "dependencies", "god_nodes", "symbol", "affected", "clone", "repository", "checkout"]
    if any(k in p for k in code_keywords):
        selected_names.update(CODE_TOOL_NAMES)
        category_matched = True

    # System / OS
    system_keywords = ["folder", "dir", "directory", "timer", "process", "kill", "memory", "ram", "cpu", "stats", "network", "recycle", "brightness", "lock", "app", "application", "timeline", "ghost", "mode"]
    if any(k in p for k in system_keywords):
        selected_names.update(SYSTEM_TOOL_NAMES)
        category_matched = True

    if not category_matched:
        selected_names.update(DEFAULT_ESSENTIAL_TOOL_NAMES)

    # A sandbox request is a trust-boundary decision. Do not expose host-side
    # command/file tools alongside the guest controls where the model could
    # accidentally fall back to the host.
    if sandbox_matched:
        selected_names = set(SANDBOX_TOOL_NAMES)

    scoped = []
    for tool_entry in source_tools:
        name = ""
        if isinstance(tool_entry, dict):
            if "function" in tool_entry:
                name = tool_entry["function"].get("name", "")
            else:
                name = tool_entry.get("name", "")
        if name in selected_names:
            scoped.append(tool_entry)

    # Safety: always ensure at least 5 tools returned
    return scoped if len(scoped) >= 5 else source_tools

