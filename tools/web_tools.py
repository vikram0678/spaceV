"""
Web and media automation tools for Windows.
"""
import urllib.parse
import webbrowser
from tools.gui_tools import safety, gui_play_youtube, gui_search_google_browser

def search_google(query: str) -> str:
    """
    Searches Google in the default web browser for the given query.
    """
    if safety.autonomous_mode_enabled:
        return gui_search_google_browser(query)
        
    from core.platform_adapter import PlatformAdapter
    try:
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded_query}"
        PlatformAdapter.open_url(url)
        return f"Opened Google search for: '{query}'"
    except Exception as e:
        return f"Failed to search Google: {e!s}"

def play_youtube(video_query: str) -> str:
    """
    Searches for and plays a video on YouTube in the default web browser.
    """
    if safety.autonomous_mode_enabled:
        return gui_play_youtube(video_query)

    from core.platform_adapter import PlatformAdapter
    try:
        encoded_query = urllib.parse.quote_plus(video_query)
        url = f"https://www.youtube.com/results?search_query={encoded_query}"
        PlatformAdapter.open_url(url)
        return f"Opening YouTube to play: '{video_query}'"
    except Exception as e:
        return f"Failed to open YouTube: {e!s}"

def open_url(url: str) -> str:
    """
    Opens any website URL in the default web browser cross-platform.
    """
    from core.platform_adapter import PlatformAdapter
    try:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        PlatformAdapter.open_url(url)
        return f"Opened website: {url}"
    except Exception as e:
        return f"Failed to open website: {e!s}"


# ============================================================================
# STEALTH BROWSER & DOM INTEGER INDEXING (Upgrades #22 & #23)
# ============================================================================

_STEALTH_CONTROLLER = None

def _get_stealth_controller():
    global _STEALTH_CONTROLLER
    if _STEALTH_CONTROLLER is None:
        try:
            from hybrid_agent.stealth_browser import StealthBrowserController
            _STEALTH_CONTROLLER = StealthBrowserController(headless=False)
        except Exception:
            _STEALTH_CONTROLLER = None
    return _STEALTH_CONTROLLER


def browse_website_stealth(url: str, extract_dom_indices: bool = True) -> str:
    """
    Navigates to URL using Camoufox-grade stealth anti-detect browser and extracts
    DOM integer indices [1], [2], [3] for token-efficient autonomous interaction.
    """
    controller = _get_stealth_controller()
    if controller is None:
        return open_url(url)

    try:
        current_url, title = controller.navigate(url)
        if not extract_dom_indices:
            return f"Stealth navigation complete: '{title}' ({current_url})"

        elements, summary = controller.get_dom_state()
        res = f"Stealth navigation to '{title}' ({current_url}):\n\n"
        res += "Interactive DOM Elements (Use index to click or type):\n"
        res += summary if summary else "No interactive elements detected on page."
        return res
    except Exception as e:
        return f"Stealth navigation failed ({e}), opening in standard browser:\n{open_url(url)}"


def click_dom_element(index: int) -> str:
    """
    Clicks a webpage interactive element by its DOM integer index [1], [2], etc.
    """
    controller = _get_stealth_controller()
    if controller is None:
        return "Stealth browser is not active."
    try:
        success = controller.click_element_by_index(index)
        return f"Successfully clicked DOM element [{index}]." if success else f"Could not find or click DOM element [{index}]."
    except Exception as e:
        return f"Error clicking DOM element [{index}]: {str(e)}"


def type_dom_element(index: int, text: str) -> str:
    """
    Types text into a webpage input field by its DOM integer index.
    """
    controller = _get_stealth_controller()
    if controller is None:
        return "Stealth browser is not active."
    try:
        success = controller.type_into_element(index, text)
        return f"Successfully typed text into DOM element [{index}]." if success else f"Could not type into DOM element [{index}]."
    except Exception as e:
        return f"Error typing into DOM element [{index}]: {str(e)}"
