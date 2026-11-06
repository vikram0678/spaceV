"""
Pydantic Validation Schemas for SpaceV Tools.
Provides strict type-checking, automatic coercion, and clean JSON schemas.
"""
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Dict, Optional, Union
import uuid
from datetime import datetime, timezone

# --- Normalized Tool Execution Contract ---
class ToolResult(BaseModel):
    """
    Standardized, normalized result envelope for all SpaceV tool executions.
    Distinguishes success, failure, blocked execution, and work waiting for user input.
    """
    success: bool = True
    status: str = "success"  # includes 'needs_input' when a tool requires clarification
    data: Any = ""
    error: Optional[str] = None
    execution_id: str = Field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:8]}")
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def __str__(self) -> str:
        if self.status in ("failed", "blocked", "invocation_error", "execution_error"):
            return self.error or str(self.data) or f"Tool execution {self.status}"
        return str(self.data)



# --- File & Folder Schemas ---
class CreateFolderInput(BaseModel):
    folder_name: str = Field(..., description="The name of the new folder to create.")
    location: str = Field(default="Desktop", description="Location to create folder in (defaults to 'Desktop').")


class OpenFolderInput(BaseModel):
    folder_path: str = Field(default="Desktop", description="Path or folder to open in File Explorer.")


class CreateFileInput(BaseModel):
    file_name: str = Field(default="", description="The name of the file to create (e.g. 'notes.txt', 'script.py').")
    content: str = Field(default="", description="The complete code or text to write inside the file. NEVER leave empty when creating scripts or code files.")
    location: str = Field(default="Desktop", description="Location to save the file (defaults to 'Desktop', use 'Workspace' for project repository).")

    @model_validator(mode='before')
    @classmethod
    def normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "file_name" not in data or not data["file_name"]:
                for alt in ("filename", "file_path", "path", "name"):
                    if data.get(alt):
                        data["file_name"] = str(data[alt])
                        break
        return data


class OpenTextEditorInput(BaseModel):
    file_name: str = Field(default="notes.txt", description="The name or path of the file to edit.")
    content: str = Field(default="", description="The text or code content to write inside the file.")
    editor: str = Field(default="notepad", description="Text editor application to launch (notepad, code, gedit).")
    location: str = Field(default="Desktop", description="Location of the file (defaults to 'Desktop').")

    @model_validator(mode='before')
    @classmethod
    def normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "file_name" not in data or not data["file_name"]:
                for alt in ("file_path", "filename", "path"):
                    if data.get(alt):
                        data["file_name"] = str(data[alt])
                        break
        return data


class ReadFileInput(BaseModel):
    file_name_or_path: str = Field(default="", description="The name or path of the file to read.")
    location: str = Field(default="Desktop", description="Location of the file (defaults to 'Desktop').")
    max_lines: int = Field(default=40, ge=1, le=400, description="Maximum number of lines to read (1-400).")
    start_line: int = Field(default=1, ge=1, description="1-based first line to read; use this to inspect a later function or section.")

    @model_validator(mode='before')
    @classmethod
    def normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "file_name_or_path" not in data or not data["file_name_or_path"]:
                for alt in ("file_path", "path", "filename", "file_name", "target_file"):
                    if data.get(alt):
                        data["file_name_or_path"] = str(data[alt])
                        break
        return data


class ListWorkspaceFilesInput(BaseModel):
    subfolder: str = Field(default="", description="Optional subfolder within the workspace to list files from.")
    max_files: int = Field(default=50, description="Maximum number of files to return.")


# --- Web & Online Schemas ---
class SearchGoogleInput(BaseModel):
    query: str = Field(..., description="The search term or question to search on Google.")


class PlayYoutubeInput(BaseModel):
    video_query: str = Field(default="", description="The song, video title, or artist to play on YouTube.")

    @model_validator(mode='before')
    @classmethod
    def normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "video_query" not in data or not data["video_query"]:
                for alt in ("query", "song_name", "title", "name"):
                    if data.get(alt):
                        data["video_query"] = str(data[alt])
                        break
        return data


class OpenUrlInput(BaseModel):
    url: str = Field(..., description="The website URL to open in browser.")


class OpenBrowserUrlsInput(BaseModel):
    urls: Union[list[str], str] = Field(..., description="List of website URLs (or comma/newline-separated string of URLs) to open in browser tabs.")
    delay_sec: float = Field(default=0.5, description="Delay in seconds between opening each tab.")


# --- System & Hardware Schemas ---
class OpenAppInput(BaseModel):
    app_name: str = Field(default="", description="The name of the application to open (e.g. 'calc', 'notepad', 'chrome').")

    @model_validator(mode='before')
    @classmethod
    def normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "app_name" not in data or not data["app_name"]:
                for alt in ("application", "application_name", "app", "name"):
                    if data.get(alt):
                        data["app_name"] = str(data[alt])
                        break
        return data


class ActivateWorkspaceInput(BaseModel):
    mode: str = Field(..., description="The mode to activate (e.g. 'coding', 'research', 'focus').")

class MediaControlInput(BaseModel):
    action: str = Field(..., description="Action: 'play', 'pause', 'next', 'previous', 'mute', 'volume_up', or 'volume_down'.")

class SetTimerInput(BaseModel):
    minutes: float = Field(..., description="Timer duration in minutes (e.g. 5, 0.5, 10).")
    label: str = Field(default="Timer", description="Title or label for the timer.")

    @field_validator('minutes', mode='before')
    @classmethod
    def parse_minutes(cls, v):
        try:
            return float(v)
        except Exception:
            return 5.0


class CreateCareerGoalInput(BaseModel):
    goal: str = ""
    target_roles: list[str] = Field(default_factory=list)
    location: str = ""
    deadline: str = Field(default="", description="Goal deadline as YYYY-MM-DD.")
    duration_days: int = Field(default=0, description="Relative deadline, such as 20, when user gave a duration rather than a calendar date.")
    available_hours: float = 0
    plan_items: list[dict[str, Any]] = Field(default_factory=list, description="Proposed tasks with title, due_date, and optional estimated_minutes/category.")
    resume_path: str = ""


class RecordCareerActivityInput(BaseModel):
    activity: str = ""
    minutes: int = 0
    task_id: str = ""
    notes: str = ""


class UpdateCareerPlanTaskInput(BaseModel):
    task_id: str = ""
    title: str = ""
    due_date: str = ""
    estimated_minutes: Optional[int] = None
    status: str = ""


class DailyCareerReviewInput(BaseModel):
    day: str = ""


class CreateCareerReminderInput(BaseModel):
    title: str = ""
    due_at: str = Field(default="", description="ISO datetime with UTC offset, e.g. 2026-11-04T18:30:00+05:30.")
    repeat_rule: str = "none"
    goal_id: str = ""
    purpose: str = "notification"
    timezone_name: str = Field(default="", description="IANA timezone for recurring reminders, e.g. Asia/Kolkata.")


class ListCareerRemindersInput(BaseModel):
    include_completed: bool = False


class ReminderIdInput(BaseModel):
    reminder_id: str = ""


class SnoozeCareerReminderInput(BaseModel):
    reminder_id: str = ""
    due_at: str = Field(default="", description="New ISO datetime with UTC offset.")


class ListCareerOpportunitiesInput(BaseModel):
    status: str = "new"
    limit: int = 25
    opportunity_type: str = ""


class DeleteCareerAssistantDataInput(BaseModel):
    confirm: bool = False

class KillProcessInput(BaseModel):
    process_name: str = Field(..., description="The process or application name to terminate.")

# --- Scraping & Intelligence Schemas ---
class ScrapeJobsInput(BaseModel):
    role: str = Field(default="", description="Role requested by the user; ask if missing instead of guessing.")
    location: str = Field(default="", description="Target location/work mode requested by the user; ask if missing.")
    save_to_desktop: bool = Field(default=False, description="Export results only when the user asks.")

class SearchAndHarvestJobsInput(BaseModel):
    role: str = Field(default="", description="Role/keywords requested by the user. If absent, ask the user instead of assuming a role.")
    location: str = Field(default="", description="User's target location or work mode. If absent, ask instead of assuming remote.")
    min_exp: int = Field(default=0, description="Optional minimum experience filter; do not infer if the user did not specify it.")
    limit: int = Field(default=10, description="Maximum number of job listings to retrieve.")
    save_to_desktop: bool = Field(default=False, description="Export results to CSV only when the user asks.")

class TrackCareerApplicationInput(BaseModel):
    job_title: str = Field(..., description="Job title / role applied or wishlisted.")
    company: str = Field(..., description="Company name.")
    job_url: str = Field(default="", description="URL of the job posting.")
    status: str = Field(default="Wishlist", description="Stage: 'Wishlist', 'Applied', 'Interview', 'Offer', 'Rejected'.")
    notes: str = Field(default="", description="Optional personal notes, interview date, or contact info.")

class ListCareerApplicationsInput(BaseModel):
    status_filter: str = Field(default="", description="Optional filter by status ('Wishlist', 'Applied', 'Interview', 'Offer', 'Rejected').")

class PrepareJobApplicationInput(BaseModel):
    job_title: str = Field(..., description="Target job title.")
    company: str = Field(..., description="Target company.")
    candidate_name: str = Field(default="Applicant", description="Applicant name.")
    skills: str = Field(default="", description="Key skills or achievements to emphasize.")

class FetchNewsInput(BaseModel):
    topic: str = Field(default="technology", description="News topic or industry.")

class GetWeatherInput(BaseModel):
    city: str = Field(default="", description="City name to get weather for.")

class GetWikipediaInput(BaseModel):
    query: str = Field(..., description="Topic or query to summarize from Wikipedia.")

# --- Vision & Clipboard Schemas ---
class TakeScreenshotInput(BaseModel):
    filename: str = Field(default="spacev_snapshot.png", description="Filename for the screenshot image.")

class WriteClipboardInput(BaseModel):
    text: str = Field(..., description="The text or code to copy to the Windows clipboard.")

# --- GUI Autonomous Cursor Schemas ---
class GuiOpenAppInput(BaseModel):
    app_name: str = Field(..., description="The application to search and open in Windows Start menu.")
    text_to_type: str = Field(default="", description="Optional text to type inside the opened app.")

class GuiSearchGoogleInput(BaseModel):
    query: str = Field(..., description="The search term to type into Google.")

class GuiHumanSearchAndOpenInput(BaseModel):
    query: str = Field(..., description="The search term to type into Google browser like a human.")
    click_first_result: bool = Field(default=True, description="Whether to smoothly glide cursor and click the first organic search result.")

class GuiTypeTextInput(BaseModel):
    text: str = Field(..., description="The text to type at current cursor position.")

class GuiPlayYoutubeInput(BaseModel):
    video_query: str = Field(..., description="The song, video title, or artist to search and play on YouTube.")

class GuiDrawInPaintInput(BaseModel):
    shape_or_prompt: str = Field(default="house", description="The shape, object, or illustration to draw in MS Paint (e.g. 'house', 'heart', 'star', 'smiley face', 'car', 'tree', 'sun', 'rocket', 'cat', 'flower', 'sailboat').")

class GuiClickTextInput(BaseModel):
    target_text: str = Field(..., description="The word, button label, or link text to find on screen and click.")

class GuiClickIconInput(BaseModel):
    target_description: str = Field(..., description="Description of the icon, button, or UI widget to click (e.g. 'settings', 'gear', 'play', 'close', 'search', 'menu', 'profile', 'download', 'add').")

class ParseScreenElementsInput(BaseModel):
    pass

class SearchMemoryInput(BaseModel):
    query: str = Field(..., description="Keywords or topic to search across past notes and preferences.")

class UiTarsNavigateInput(BaseModel):
    instruction: str = Field(..., description="Natural language instruction of what UI element to navigate, click, or manipulate on screen.")

class ScratchpadSetPlanInput(BaseModel):
    steps: list[str] = Field(..., description="Ordered list of step descriptions to achieve the task goal.")

class ScratchpadNoteInput(BaseModel):
    key: str = Field(..., description="Identifier or variable name (e.g. 'download_path', 'target_window').")
    value: str = Field(..., description="The value or fact to store in working memory.")

class ScratchpadViewInput(BaseModel):
    pass

class RunPythonScriptInput(BaseModel):
    file_name_or_path: str = Field(default="", description="The Python script file name or path to execute (e.g. 'reverse_number.py').")
    args: str = Field(default="", description="Optional arguments to pass to the script.")
    input_data: str = Field(default="", description="Optional input string or test input to pipe into stdin if the script prompts the user.")
    timeout: int = Field(default=30, description="Execution timeout in seconds.")

    @model_validator(mode='before')
    @classmethod
    def normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "file_name_or_path" not in data or not data["file_name_or_path"]:
                for alt in ("file_path", "script_name", "file", "path", "name", "filename"):
                    if data.get(alt):
                        data["file_name_or_path"] = str(data[alt])
                        break
            if "input_data" not in data or not data["input_data"]:
                for alt in ("stdin", "input", "test_input"):
                    if data.get(alt):
                        data["input_data"] = str(data[alt])
                        break
        return data

class ExecuteTerminalCommandInput(BaseModel):
    command: str = Field(default="", description="The shell/terminal command to execute.")
    timeout: int = Field(default=30, description="Command execution timeout in seconds.")

    @model_validator(mode='before')
    @classmethod
    def normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "command" not in data or not data["command"]:
                for alt in ("cmd", "shell_command", "script"):
                    if data.get(alt):
                        data["command"] = str(data[alt])
                        break
        return data


class ClonePublicRepositoryInput(BaseModel):
    """Inputs for the source-only, exact-approval GitHub clone tool."""

    repository_url: str = Field(..., min_length=1, max_length=500)
    destination: str = Field(..., min_length=1, max_length=1000)
    approval_id: str = Field(default="", max_length=32)
    approval_text: str = Field(default="", max_length=80)


class CreateSandboxSessionInput(BaseModel):
    """Create a reusable Celesto VM only after exact approval of the task scope."""

    task_description: str = Field(default="", max_length=800, description="Required on the proposal call. On approval, the task stored for approval_id is authoritative; this field may be omitted.")
    approval_id: str = Field(default="", max_length=32)
    approval_text: str = Field(default="", max_length=80)


class RunSandboxSessionCommandInput(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)
    command: str = Field(..., min_length=1, max_length=10000)


class CloseSandboxSessionInput(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)

class ExecuteInVscodeTerminalInput(BaseModel):
    command: str = Field(default="", description="The command or script to execute in VS Code terminal.")
    file_path: str = Field(default="", description="Optional script or file path.")

    @model_validator(mode='before')
    @classmethod
    def normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "command" not in data or not data["command"]:
                for alt in ("cmd", "script", "file_name_or_path", "file_path", "file", "path"):
                    if data.get(alt):
                        data["command"] = str(data[alt])
                        break
        return data


class ExecuteCodeBlockInput(BaseModel):
    language: str = Field(default="python", description="Language runtime: 'python' or 'bash'.")
    code: str = Field(default="", description="The script source code to execute directly.")
    file_name: str = Field(default="", description="Optional script filename (e.g. 'reverse_number.py').")
    input_data: str = Field(default="", description="Optional stdin string to pass to the script.")
    timeout: int = Field(default=15, description="Execution timeout in seconds.")

    @model_validator(mode='before')
    @classmethod
    def normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "code" not in data or not data["code"]:
                for alt in ("script", "source", "content", "body"):
                    if data.get(alt):
                        data["code"] = str(data[alt])
                        break
            if "file_name" not in data or not data["file_name"]:
                for alt in ("filename", "file_path", "file_name_or_path", "name"):
                    if data.get(alt):
                        data["file_name"] = str(data[alt])
                        break
            if "input_data" not in data or not data["input_data"]:
                for alt in ("stdin", "input", "test_input", "args"):
                    if data.get(alt):
                        data["input_data"] = str(data[alt])
                        break
        return data


class ReadWebPageInput(BaseModel):
    url: str = Field(default="", description="The URL or GitHub repository to read and summarize.")

    @model_validator(mode='before')
    @classmethod
    def normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "url" not in data or not data["url"]:
                for alt in ("link", "repo_url", "web_url", "target_url", "site"):
                    if data.get(alt):
                        data["url"] = str(data[alt])
                        break
        return data

class SetSystemBrightnessInput(BaseModel):
    level: int = Field(default=50, description="Display brightness percentage from 0 to 100.")

    @model_validator(mode='before')
    @classmethod
    def normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "level" not in data or data["level"] is None:
                for alt in ("brightness", "percent", "pct", "val", "value"):
                    if data.get(alt) is not None:
                        try:
                            data["level"] = int(data[alt])
                        except Exception:
                            pass
                        break
        return data


class ScrapeWebPageCrawl4aiInput(BaseModel):
    url: str = Field(default="", description="The URL of the webpage to scrape and distill into Markdown.")
    max_chars: int = Field(default=12000, description="Maximum character limit for distilled markdown.")

    @model_validator(mode='before')
    @classmethod
    def normalize_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "url" not in data or not data["url"]:
                for alt in ("target_url", "link", "web_url", "site"):
                    if data.get(alt):
                        data["url"] = str(data[alt])
                        break
        return data


class QueryCodeGraphInput(BaseModel):
    query: str = Field(..., description="Natural language question or symbols to search in the code knowledge graph.")
    depth: int = Field(default=2, description="BFS expansion depth from seed nodes.")


class GetCodeNodeInput(BaseModel):
    label: str = Field(..., description="Function name, class name, or file path to inspect in the code graph.")


class GetCodeNeighborsInput(BaseModel):
    label: str = Field(..., description="Symbol name to query incoming/outgoing relations for.")
    direction: str = Field(default="both", description="Direction of relations to inspect ('in', 'out', or 'both').")


class GetCodeBlastRadiusInput(BaseModel):
    symbol_or_path: str = Field(..., description="Function name, class name, or file path to compute downstream blast radius for.")
    depth: int = Field(default=2, description="Maximum traversal depth across reverse caller arcs.")


# Mapping tool names to their Pydantic validator models
PYDANTIC_TOOL_MODELS = {
    "create_folder": CreateFolderInput,
    "open_folder": OpenFolderInput,
    "create_file": CreateFileInput,
    "open_text_editor": OpenTextEditorInput,
    "read_file_content": ReadFileInput,
    "list_workspace_files": ListWorkspaceFilesInput,
    "search_google": SearchGoogleInput,
    "play_youtube": PlayYoutubeInput,
    "open_url": OpenUrlInput,
    "open_browser_urls": OpenBrowserUrlsInput,
    "open_application": OpenAppInput,
    "activate_workspace_mode": ActivateWorkspaceInput,
    "media_control": MediaControlInput,
    "set_timer": SetTimerInput,
    "create_career_goal": CreateCareerGoalInput,
    "record_career_activity": RecordCareerActivityInput,
    "update_career_plan_task": UpdateCareerPlanTaskInput,
    "get_career_daily_review": DailyCareerReviewInput,
    "create_career_reminder": CreateCareerReminderInput,
    "list_career_reminders": ListCareerRemindersInput,
    "cancel_career_reminder": ReminderIdInput,
    "snooze_career_reminder": SnoozeCareerReminderInput,
    "list_career_opportunities": ListCareerOpportunitiesInput,
    "delete_career_assistant_data": DeleteCareerAssistantDataInput,
    "kill_process_by_name": KillProcessInput,
    "scrape_jobs": ScrapeJobsInput,
    "fetch_news_headlines": FetchNewsInput,
    "get_weather": GetWeatherInput,
    "get_wikipedia_summary": GetWikipediaInput,
    "take_screen_snapshot": TakeScreenshotInput,
    "write_clipboard_text": WriteClipboardInput,
    "gui_open_and_search_app": GuiOpenAppInput,
    "gui_search_google_browser": GuiSearchGoogleInput,
    "gui_human_search_and_open": GuiHumanSearchAndOpenInput,
    "gui_type_text": GuiTypeTextInput,
    "gui_play_youtube": GuiPlayYoutubeInput,
    "gui_draw_in_paint": GuiDrawInPaintInput,
    "gui_click_text": GuiClickTextInput,
    "gui_click_icon": GuiClickIconInput,
    "parse_screen_elements": ParseScreenElementsInput,
    "search_memory": SearchMemoryInput,
    "ui_tars_navigate_and_act": UiTarsNavigateInput,
    "ui_tars_computer_control": UiTarsNavigateInput,
    "scratchpad_set_plan": ScratchpadSetPlanInput,
    "scratchpad_note": ScratchpadNoteInput,
    "scratchpad_view": ScratchpadViewInput,
    "run_python_script": RunPythonScriptInput,
    "execute_code_block": ExecuteCodeBlockInput,
    "execute_terminal_command": ExecuteTerminalCommandInput,
    "clone_public_repository": ClonePublicRepositoryInput,
    "create_sandbox_session": CreateSandboxSessionInput,
    "run_sandbox_session_command": RunSandboxSessionCommandInput,
    "close_sandbox_session": CloseSandboxSessionInput,
    "execute_in_vscode_terminal": ExecuteInVscodeTerminalInput,
    "read_web_page": ReadWebPageInput,
    "set_system_brightness": SetSystemBrightnessInput,
    "scrape_web_page_crawl4ai": ScrapeWebPageCrawl4aiInput,
    "query_code_graph": QueryCodeGraphInput,
    "get_code_node": GetCodeNodeInput,
    "get_code_neighbors": GetCodeNeighborsInput,
    "get_code_blast_radius": GetCodeBlastRadiusInput,
    "search_and_harvest_jobs": SearchAndHarvestJobsInput,
    "track_career_application": TrackCareerApplicationInput,
    "list_career_applications": ListCareerApplicationsInput,
    "prepare_job_application": PrepareJobApplicationInput,
}


