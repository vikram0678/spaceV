"""
File and folder management tools for Windows.
"""
import os
import subprocess
from pathlib import Path
from config import USER_DESKTOP_DIR

def resolve_path(path_str: str) -> Path:
    """Helper to resolve friendly paths like 'Desktop', 'Downloads', or full paths."""
    if not path_str or path_str.lower() in ["desktop", "the desktop", "~/desktop"]:
        return USER_DESKTOP_DIR
    elif path_str.lower() in ["downloads", "the downloads", "~/downloads"]:
        return Path(os.path.expanduser("~")) / "Downloads"
    elif path_str.lower() in ["documents", "the documents", "~/documents"]:
        return Path(os.path.expanduser("~")) / "Documents"
    
    p = Path(os.path.expanduser(path_str))
    if not p.is_absolute():
        p = USER_DESKTOP_DIR / p
    return p

def create_folder(folder_name: str, location: str = "Desktop") -> str:
    """
    Creates a new folder at the specified location (defaults to Desktop).
    """
    try:
        base_dir = resolve_path(location)
        target_path = base_dir / folder_name
        
        target_path.mkdir(parents=True, exist_ok=True)
        return f"Successfully created folder '{folder_name}' at: {target_path}"
    except Exception as e:
        return f"Failed to create folder '{folder_name}': {str(e)}"

def open_folder(folder_path: str = "Desktop") -> str:
    """
    Opens a folder in Windows File Explorer.
    """
    try:
        target = resolve_path(folder_path)
        if not target.exists():
            return f"Folder does not exist: {target}"
        
        # Open in Windows Explorer
        os.startfile(str(target))
        return f"Opened folder in Windows Explorer: {target}"
    except Exception as e:
        return f"Failed to open folder: {str(e)}"

def create_file(file_name: str, content: str = "", location: str = "Desktop") -> str:
    """
    Creates a new file with optional content at the specified location (defaults to Desktop).
    """
    try:
        base_dir = resolve_path(location)
        target_path = base_dir / file_name
        
        base_dir.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully created file '{file_name}' at: {target_path}"
    except Exception as e:
        return f"Failed to create file '{file_name}': {str(e)}"

def list_desktop_files() -> str:
    """
    Lists the names of items currently on the Desktop.
    """
    try:
        items = os.listdir(USER_DESKTOP_DIR)
        if not items:
            return "Desktop is currently empty."
        return f"Items on Desktop: {', '.join(items[:20])}" + ("..." if len(items) > 20 else "")
    except Exception as e:
        return f"Failed to list desktop items: {str(e)}"

def read_file_content(file_name_or_path: str, location: str = "Desktop", max_lines: int = 40) -> str:
    """
    Reads the text/code content of a specified file on the Desktop or disk.
    """
    try:
        target = resolve_path(file_name_or_path)
        if not target.exists():
            base_dir = resolve_path(location)
            target = base_dir / file_name_or_path
            
        if not target.exists():
            return f"File '{file_name_or_path}' could not be found at {target}."
            
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            
        total_lines = len(lines)
        snippet = "".join(lines[:max_lines])
        
        truncated_note = f"\n\n... [Showing first {max_lines} of {total_lines} lines]" if total_lines > max_lines else ""
        return f"Content of '{target.name}' ({total_lines} lines):\n\n```\n{snippet}\n```{truncated_note}"
    except Exception as e:
        return f"Failed to read file '{file_name_or_path}': {str(e)}"

