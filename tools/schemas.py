"""
Pydantic Validation Schemas for SpaceV Tools.
Provides strict type-checking, automatic coercion, and clean JSON schemas.
"""
from typing import Optional
from pydantic import BaseModel, Field, field_validator

# --- File & Folder Schemas ---
class CreateFolderInput(BaseModel):
    folder_name: str = Field(..., description="The name of the new folder to create.")
    location: str = Field(default="Desktop", description="Location to create folder in (defaults to 'Desktop').")

class OpenFolderInput(BaseModel):
    folder_path: str = Field(default="Desktop", description="Path or folder to open in File Explorer.")

class CreateFileInput(BaseModel):
    file_name: str = Field(..., description="The name of the file to create (e.g. 'notes.txt', 'script.py').")
    content: str = Field(default="", description="The text or code content to write inside the file.")
    location: str = Field(default="Desktop", description="Location to save the file (defaults to 'Desktop').")

class ReadFileInput(BaseModel):
    file_name_or_path: str = Field(..., description="The name or path of the file to read.")
    location: str = Field(default="Desktop", description="Location of the file (defaults to 'Desktop').")
    max_lines: int = Field(default=40, description="Maximum number of lines to read.")

# --- Web & Online Schemas ---
class SearchGoogleInput(BaseModel):
    query: str = Field(..., description="The search term or question to search on Google.")

class PlayYoutubeInput(BaseModel):
    video_query: str = Field(..., description="The song, video title, or artist to play on YouTube.")

class OpenUrlInput(BaseModel):
    url: str = Field(..., description="The website URL to open in browser.")

# --- System & Hardware Schemas ---
class OpenAppInput(BaseModel):
    app_name: str = Field(..., description="The name of the application to open (e.g. 'calc', 'notepad', 'chrome').")

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

class KillProcessInput(BaseModel):
    process_name: str = Field(..., description="The process or application name to terminate.")

# --- Scraping & Intelligence Schemas ---
class ScrapeJobsInput(BaseModel):
    role: str = Field(default="python", description="Job keyword or role to search for (e.g. 'python', 'react').")
    location: str = Field(default="remote", description="Location or 'remote'.")
    save_to_desktop: bool = Field(default=True, description="Whether to export results to a CSV on Desktop.")

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

class GuiTypeTextInput(BaseModel):
    text: str = Field(..., description="The text to type at current cursor position.")

class GuiPlayYoutubeInput(BaseModel):
    video_query: str = Field(..., description="The song, video title, or artist to search and play on YouTube.")

class GuiDrawInPaintInput(BaseModel):
    shape_or_prompt: str = Field(default="house", description="The shape, object, or illustration to draw in MS Paint (e.g. 'house', 'heart', 'star', 'smiley face', 'car', 'tree', 'sun', 'rocket', 'cat', 'flower', 'sailboat').")

class GuiClickTextInput(BaseModel):
    target_text: str = Field(..., description="The word, button label, or link text to find on screen and click.")

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

# Mapping tool names to their Pydantic validator models
PYDANTIC_TOOL_MODELS = {
    "create_folder": CreateFolderInput,
    "open_folder": OpenFolderInput,
    "create_file": CreateFileInput,
    "read_file_content": ReadFileInput,
    "search_google": SearchGoogleInput,
    "play_youtube": PlayYoutubeInput,
    "open_url": OpenUrlInput,
    "open_application": OpenAppInput,
    "activate_workspace_mode": ActivateWorkspaceInput,
    "media_control": MediaControlInput,
    "set_timer": SetTimerInput,
    "kill_process_by_name": KillProcessInput,
    "scrape_jobs": ScrapeJobsInput,
    "fetch_news_headlines": FetchNewsInput,
    "get_weather": GetWeatherInput,
    "get_wikipedia_summary": GetWikipediaInput,
    "take_screen_snapshot": TakeScreenshotInput,
    "write_clipboard_text": WriteClipboardInput,
    "gui_open_and_search_app": GuiOpenAppInput,
    "gui_search_google_browser": GuiSearchGoogleInput,
    "gui_type_text": GuiTypeTextInput,
    "gui_play_youtube": GuiPlayYoutubeInput,
    "gui_draw_in_paint": GuiDrawInPaintInput,
    "gui_click_text": GuiClickTextInput,
    "search_memory": SearchMemoryInput,
    "ui_tars_navigate_and_act": UiTarsNavigateInput,
    "ui_tars_computer_control": UiTarsNavigateInput,
    "scratchpad_set_plan": ScratchpadSetPlanInput,
    "scratchpad_note": ScratchpadNoteInput,
    "scratchpad_view": ScratchpadViewInput,
}


