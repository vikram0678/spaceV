"""
File and folder management tools for Windows.
"""
import os
from pathlib import Path

from config import USER_DESKTOP_DIR


WORKSPACE_DIR = Path(__file__).resolve().parent.parent


def resolve_path(path_str: str) -> Path:
    """Helper to resolve friendly paths like 'Desktop', 'Downloads', 'Workspace', or full paths."""
    clean = (path_str or "").strip()
    clean_lower = clean.lower()

    if not clean or clean_lower in ["desktop", "the desktop", "~/desktop"]:
        return USER_DESKTOP_DIR
    elif clean_lower in ["downloads", "the downloads", "~/downloads"]:
        return Path(os.path.expanduser("~")) / "Downloads"
    elif clean_lower in ["documents", "the documents", "~/documents"]:
        return Path(os.path.expanduser("~")) / "Documents"
    elif clean_lower in ["workspace", "project", "repo", "repository", "cwd", "agentspace", "current directory", "."]:
        return WORKSPACE_DIR

    if clean_lower.startswith("desktop/") or clean_lower.startswith("desktop\\"):
        return USER_DESKTOP_DIR / clean[8:]
    if clean_lower.startswith("workspace/") or clean_lower.startswith("workspace\\"):
        return WORKSPACE_DIR / clean[10:]
    if clean_lower.startswith("project/") or clean_lower.startswith("project\\"):
        return WORKSPACE_DIR / clean[8:]

    p = Path(os.path.expanduser(clean))
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
        return f"Failed to create folder '{folder_name}': {e!s}"

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
        return f"Failed to open folder: {e!s}"

def create_file(file_name: str, content: str = "", location: str = "Desktop") -> str:
    """
    Creates a new file with optional content at the specified location (defaults to Desktop).
    Empirically verifies file creation and records exact file size on disk.
    """
    try:
        base_dir = resolve_path(location)
        target_path = base_dir / file_name

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        stat = target_path.stat()
        file_size = stat.st_size
        abs_path = target_path.resolve()
        if file_size == 0:
            return f"Created empty file '{file_name}' (0 bytes) at: {abs_path}. Note: No content was provided."
        return f"Successfully created file '{file_name}' (size: {file_size} bytes) at: {abs_path}"
    except Exception as e:
        return f"Failed to create file '{file_name}': {e!s}"

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
        return f"Failed to list desktop items: {e!s}"

def list_workspace_files(subfolder: str = "", max_files: int = 50) -> str:
    """
    Lists the files and directories inside the active SpaceV project workspace,
    excluding cache, build, virtualenv, and internal tracking directories.
    """
    try:
        base_dir = WORKSPACE_DIR
        if subfolder:
            clean_sub = subfolder.strip().lstrip("/\\")
            base_dir = (WORKSPACE_DIR / clean_sub).resolve()
            if not base_dir.exists():
                return f"Subfolder '{subfolder}' does not exist in workspace: {base_dir}"

        ignored_dirs = {
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
            ".gemini", "node_modules", ".idea", ".vscode", "scratch", "dist", "build", "Stirling-PDF",
            "opensourcetools"
        }
        found_files = []
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
            rel_root = Path(root).relative_to(WORKSPACE_DIR)
            for f in sorted(files):
                if f.endswith((".pyc", ".pyo", ".pyd")) or f.startswith("."):
                    continue
                rel_path = str(rel_root / f) if str(rel_root) != "." else f
                found_files.append(rel_path)
                if len(found_files) >= max_files:
                    break
            if len(found_files) >= max_files:
                break

        if not found_files:
            return f"No matching files found in workspace ({base_dir.name})."

        display_list = found_files[:max_files]
        summary = f"Workspace files ({len(display_list)} items):\n" + "\n".join(f"- {f}" for f in display_list)
        if len(found_files) >= max_files:
            summary += f"\n... [Truncated at {max_files} files]"
        return summary
    except Exception as e:
        return f"Failed to list workspace files: {e!s}"

def read_file_content(file_name_or_path: str = "", location: str = "Desktop", max_lines: int = 40, **kwargs) -> str:
    """
    Reads the text/code content of a specified file on the Desktop, Workspace, or disk.
    """
    try:
        if not file_name_or_path:
            for alt in ("file_path", "path", "filename", "file_name", "target_file"):
                val = kwargs.get(alt)
                if val:
                    file_name_or_path = str(val)
                    break
        if not file_name_or_path:
            return "Failed to read file: no file path or name specified."

        # Cross-Zone Translation: check if target refers to an isolated Celesto MicroVM guest path
        candidate_guest = file_name_or_path
        if location and any(k in location for k in ("quarantine", "sandbox", "/workspace")):
            candidate_guest = f"{location.rstrip('/')}/{file_name_or_path.lstrip('/')}"
        guest_markers = ("/workspace/quarantine", "/tmp/spacev", "/workspace/", "quarantine/")
        if any(candidate_guest.startswith(m) or candidate_guest.lstrip("./").startswith(m) for m in guest_markers):
            from tools.sandbox_tools import sandbox_runner
            clean_guest_target = candidate_guest if candidate_guest.startswith("/") else f"/{candidate_guest.lstrip('./')}"
            res = sandbox_runner.run_in_sandbox(f"cat '{clean_guest_target}'")
            if res.exit_code == 0 and not res.blocked:
                lines = res.stdout.splitlines(keepends=True)
                total_lines = len(lines)
                snippet = "".join(lines[:max_lines])
                truncated_note = f"\n\n... [Showing first {max_lines} of {total_lines} lines]" if total_lines > max_lines else ""
                file_basename = Path(clean_guest_target).name
                return f"Content of quarantined guest file '{file_basename}' ({total_lines} lines) in Celesto Sandbox:\n\n```\n{snippet}\n```{truncated_note}"
            elif res.blocked:
                return f"🛡️ [SANDBOX CONTAINMENT ALERT] Quarantined file read blocked: {res.stderr}"
            return f"File '{file_name_or_path}' could not be found in Celesto MicroVM sandbox at {clean_guest_target}."

        loc_clean = (location or "").strip().lower()
        if loc_clean not in ("", "desktop", "the desktop", "~/desktop"):
            base_dir = resolve_path(location)
            target = base_dir / file_name_or_path if not Path(file_name_or_path).is_absolute() else Path(file_name_or_path)
        else:
            target = resolve_path(file_name_or_path)
            # Automatic fallback: if not on Desktop, check workspace root if it exists
            if not target.exists():
                workspace_target = WORKSPACE_DIR / file_name_or_path
                if workspace_target.exists():
                    target = workspace_target

        if not target.exists():
            return f"File '{file_name_or_path}' could not be found at {target}."

        with open(target, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        snippet = "".join(lines[:max_lines])

        truncated_note = f"\n\n... [Showing first {max_lines} of {total_lines} lines]" if total_lines > max_lines else ""
        return f"Content of '{target.name}' ({total_lines} lines):\n\n```\n{snippet}\n```{truncated_note}"
    except Exception as e:
        return f"Failed to read file '{file_name_or_path}': {e!s}"



def open_text_editor(
    file_name: str = "notes.txt",
    content: str = "",
    editor: str = "notepad",
    location: str = "Desktop"
) -> str:
    """
    Creates or updates a file on the Desktop or specified path and opens it
    in the desktop text editor (Notepad, VS Code, Gedit, etc.).
    """
    from core.platform_adapter import PlatformAdapter
    try:
        base_dir = resolve_path(location)
        if os.path.isabs(file_name):
            target_path = Path(file_name)
        else:
            target_path = base_dir / file_name

        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Write or update file content if provided or if creating new file
        if content or not target_path.exists():
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)

        launch_res = PlatformAdapter.open_file(target_path, editor=editor)
        action_desc = f"written ({len(content)} characters)" if content else "ready"
        return f"File '{target_path.name}' is {action_desc} at {target_path}. Status: {launch_res}"
    except Exception as e:
        return f"Failed to open text editor for '{file_name}': {e!s}"

