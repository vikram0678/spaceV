"""
Tool Registry and Schema Definitions for Ollama native function calling.
"""
import json
from typing import Dict, Any, Callable
from tools.file_tools import create_folder, open_folder, create_file, list_desktop_files, read_file_content
from tools.web_tools import search_google, play_youtube, open_url
from tools.system_tools import (
    get_current_time, open_application, get_system_stats,
    activate_workspace_mode, optimize_system_memory,
    media_control, lock_workstation, empty_recycle_bin,
    get_network_info, list_running_apps, kill_process_by_name,
    set_timer, list_active_timers
)
from tools.gui_tools import gui_open_and_search_app, gui_search_google_browser, gui_type_text, gui_play_youtube, gui_draw_in_paint
from tools.scraper_tools import scrape_jobs, fetch_news_headlines, get_weather, get_wikipedia_summary
from tools.vision_tools import get_active_window_info, take_screen_snapshot, read_clipboard_text, write_clipboard_text
from core.vision_grounding import gui_click_text, read_screen_text


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
TOOL_FUNCTIONS: Dict[str, Callable] = {
    "create_folder": create_folder,
    "open_folder": open_folder,
    "create_file": create_file,
    "list_desktop_files": list_desktop_files,
    "read_file_content": read_file_content,
    "search_google": search_google,
    "play_youtube": play_youtube,
    "open_url": open_url,
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
    "gui_type_text": gui_type_text,
    "gui_play_youtube": gui_play_youtube,
    "gui_draw_in_paint": gui_draw_in_paint,
    "gui_click_text": gui_click_text,
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
    "detonate_in_sandbox": lambda command: __import__("tools.sandbox_tools", fromlist=["detonate_in_sandbox"]).detonate_in_sandbox(command),
    "run_sandboxed_workflow": lambda workflow_name="celesto_deployment_pipeline": __import__("tools.sandbox_tools", fromlist=["run_sandboxed_workflow"]).run_sandboxed_workflow(workflow_name),
    "audit_sandbox_containment": lambda attack_type="prompt_injection_exfil": __import__("tools.sandbox_tools", fromlist=["audit_sandbox_containment"]).audit_sandbox_containment(attack_type),
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
            "description": "Scrapes live tech and remote job listings for any role (e.g. 'python developer', 'data scientist', 'frontend') and optionally saves them to a CSV on the user's Desktop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "The job role or keyword to search for (e.g. 'python', 'react', 'machine learning')."
                    },
                    "location": {
                        "type": "string",
                        "description": "Location or 'remote'."
                    },
                    "save_to_desktop": {
                        "type": "boolean",
                        "description": "Whether to export findings to a CSV on the Desktop (defaults to True)."
                    }
                },
                "required": ["role"]
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
            "name": "detonate_in_sandbox",
            "description": "Executes untrusted or dangerous shell commands inside an isolated Celesto MicroVM sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to detonate inside the isolated guest microVM."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_sandboxed_workflow",
            "description": "Executes a 10-step autonomous workflow inside Celesto MicroVM with automatic Step 7 failure detection and snapshot rollback recovery.",
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
            "description": "Executes an adversarial prompt injection containment audit inside Celesto MicroVM and generates Contract 8 evidence.",
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
    }
]


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Executes a registered tool function with Pydantic validation and type coercion.
    """
    func = TOOL_FUNCTIONS.get(tool_name)
    if not func:
        return f"Error: Tool '{tool_name}' is not recognized."
    
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
        schema_cls = PYDANTIC_TOOL_MODELS.get(tool_name)
        if schema_cls:
            try:
                validated_model = schema_cls(**arguments)
                arguments = validated_model.model_dump()
            except Exception as val_err:
                print(f"[Pydantic] Validation note for {tool_name}: {val_err}")

        result = func(**arguments)
        return str(result)
    except TypeError as e:
        # Fallback without args if tool takes none
        try:
            result = func()
            return str(result)
        except Exception:
            return f"Error executing tool '{tool_name}': {str(e)}"
    except Exception as e:
        return f"Error executing tool '{tool_name}': {str(e)}"
