import logging
import urllib.parse
import urllib.request

logger = logging.getLogger("SpaceV.WebTools")


def search_google(query: str) -> str:
    """
    Searches Google in the default web browser for the given query.
    """
    from core.platform_adapter import PlatformAdapter
    from tools.gui_tools import HAS_PYAUTOGUI, gui_search_google_browser, safety
    if safety.autonomous_mode_enabled and HAS_PYAUTOGUI and not PlatformAdapter.is_wsl():
        return gui_search_google_browser(query)

    try:
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded_query}"
        PlatformAdapter.open_url(url)
        return f"Opened Google search for: '{query}'"
    except Exception as e:
        return f"Failed to search Google: {e!s}"


def _resolve_youtube_top_video_id(video_query: str) -> str | None:
    """
    Resolves the top YouTube video ID in <1s using standard library urllib and regex.
    Enables direct instant autoplay (https://www.youtube.com/watch?v={id}&autoplay=1).
    """
    import re
    import urllib.parse
    import urllib.request
    try:
        clean = video_query.strip()
        if not clean:
            return None
        encoded = urllib.parse.quote_plus(clean)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
        )
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
        for vid in video_ids:
            if len(vid) == 11 and vid not in ["dQw4w9WgXcQ"]:
                return vid
        return None
    except Exception:
        return None


def play_youtube(video_query: str) -> str:
    """
    Searches for and plays a video on YouTube with direct instant autoplay cross-platform.
    """
    from core.platform_adapter import PlatformAdapter
    from tools.gui_tools import HAS_PYAUTOGUI, gui_play_youtube, safety

    # If autonomous mode is enabled on native Windows with real PyAutoGUI, run GUI cursor flow
    if safety.autonomous_mode_enabled and HAS_PYAUTOGUI and not PlatformAdapter.is_wsl():
        return gui_play_youtube(video_query)

    try:
        encoded_query = urllib.parse.quote_plus(video_query)
        top_id = _resolve_youtube_top_video_id(video_query)
        if top_id:
            url = f"https://www.youtube.com/watch?v={top_id}&autoplay=1"
            PlatformAdapter.open_url(url)
            return f"Playing '{video_query}' on YouTube: {url}"
        else:
            url = f"https://www.youtube.com/results?search_query={encoded_query}"
            PlatformAdapter.open_url(url)
            return f"Opening YouTube search for: '{video_query}'"
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


def fetch_github_repo_summary(url: str) -> str | None:
    """
    Zero-browser high-speed GitHub repository distiller (Crawl4AI pattern).
    Fetches raw README markdown and API metadata in <100ms with zero browser overhead.
    """
    import json
    import re
    import urllib.request

    m = re.search(r"github\.com/([^/\s]+)/([^/\s#?]+)", url)
    if not m:
        return None

    owner, repo = m.group(1), m.group(2)
    repo = repo.rstrip("/").removesuffix(".git")

    headers = {
        "User-Agent": "SpaceV-Cybernetic-Agent/2.0 (compatible; Mozilla/5.0; OpenSource Scraper)",
        "Accept": "application/vnd.github.v3+json, text/plain, */*"
    }

    # 1. Fetch repo metadata via public GitHub API
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    meta_info = ""
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            desc = data.get("description") or "No description provided."
            stars = data.get("stargazers_count", 0)
            forks = data.get("forks_count", 0)
            lang = data.get("language") or "Python"
            topics = ", ".join(data.get("topics", [])) or "None"
            license_name = (data.get("license") or {}).get("name", "Unknown")
            meta_info = (
                f"### GitHub Repository: {owner}/{repo}\n"
                f"- **Description:** {desc}\n"
                f"- **Language:** {lang} | **Stars:** {stars:,} | **Forks:** {forks:,}\n"
                f"- **License:** {license_name} | **Topics:** {topics}\n\n"
            )
    except Exception:
        meta_info = f"### GitHub Repository: {owner}/{repo}\n\n"

    # 2. Fetch raw README.md directly from raw.githubusercontent.com
    readme_text = ""
    for branch in ("main", "master"):
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
        try:
            req = urllib.request.Request(raw_url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                readme_text = resp.read().decode("utf-8", errors="replace")
                if readme_text:
                    break
        except Exception:
            continue

    if not readme_text:
        for alt_file in ("readme.md", "README.rst", "README"):
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{alt_file}"
            try:
                req = urllib.request.Request(raw_url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    readme_text = resp.read().decode("utf-8", errors="replace")
                    if readme_text:
                        break
            except Exception:
                continue

    if readme_text:
        sample = readme_text[:4500]
        if len(readme_text) > 4500:
            sample += "\n\n... [README truncated for token efficiency] ..."
        return f"{meta_info}#### README Content Overview:\n\n{sample}"

    return meta_info if meta_info else None


def read_web_page(url: str = "", **kwargs) -> str:
    """
    Fetches and reads content of any web page or GitHub repository, automatically stripping HTML/CSS clutter
    and returning distilled, LLM-ready semantic Markdown (Crawl4AI pattern).
    Gracefully supports file:// URIs and parameter redirection for local inspections.
    """
    from pathlib import Path
    import urllib.request

    from tools.semantic_distiller import distill_html_to_markdown

    target = url or kwargs.get("target_url") or kwargs.get("link") or kwargs.get("web_url") or ""

    # Delegated parameter recovery if model hallucinated tool purpose
    if not target:
        if kwargs.get("command"):
            from tools.system_tools import execute_terminal_command
            return execute_terminal_command(kwargs["command"])
        if kwargs.get("file_name_or_path") or kwargs.get("path"):
            from tools.file_tools import read_file_content
            return read_file_content(file_name_or_path=kwargs.get("file_name_or_path") or kwargs.get("path"))
        return "Failed: No URL provided."

    target_str = str(target).strip()

    # Local file:// scheme resolution
    if target_str.lower().startswith("file://"):
        local_path_str = target_str[7:]
        local_p = Path(local_path_str)
        if local_p.exists() and local_p.is_file():
            try:
                content = local_p.read_text(encoding="utf-8", errors="replace")
                return f"=== Local File Content ({local_p.name}) ===\n\n{content}"
            except Exception as fe:
                return f"Failed to read local file '{local_p}': {fe!s}"
        else:
            return f"Failed: Local file '{local_path_str}' does not exist."

    if not target_str.startswith("http://") and not target_str.startswith("https://"):
        target_str = "https://" + target_str

    url = target_str

    # Tier 1: Specialized GitHub Fast-Path
    if "github.com" in url.lower():
        gh_summary = fetch_github_repo_summary(url)
        if gh_summary:
            return f"=== Distilled Repository Content ===\n\n{gh_summary}"

    # Tier 2: General HTTP Semantic Extraction
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5"
            }
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            html = response.read().decode("utf-8", errors="replace")

        markdown_content = distill_html_to_markdown(html)
        if not markdown_content:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            markdown_content = text[:4000] if text else ""

        if not markdown_content:
            return f"Web page at {url} was fetched but contained no readable text."
        return f"=== Distilled Content from {url} ===\n\n{markdown_content}"
    except Exception as e:
        return f"Failed to read web page at {url}: {e!s}"


# ============================================================================
# STEALTH BROWSER & DOM INTEGER INDEXING (Upgrades #22 & #23)
# ============================================================================

_STEALTH_CONTROLLER = None

def _get_stealth_controller():
    global _STEALTH_CONTROLLER
    if _STEALTH_CONTROLLER is None:
        try:
            from hybrid_agent.stealth_browser import StealthBrowserController
            ctrl = StealthBrowserController(headless=False)
            if getattr(ctrl, "is_available", lambda: True)():
                _STEALTH_CONTROLLER = ctrl
            else:
                _STEALTH_CONTROLLER = None
        except Exception:
            _STEALTH_CONTROLLER = None
    return _STEALTH_CONTROLLER


def browse_website_stealth(url: str, extract_dom_indices: bool = True) -> str:
    """
    Navigates to URL using Camoufox-grade stealth anti-detect browser and extracts
    DOM integer indices [1], [2], [3] for token-efficient autonomous interaction.
    Seamlessly degrades to Crawl4AI semantic reader if live browser is unavailable.
    """
    controller = _get_stealth_controller()
    if controller is None:
        return read_web_page(url)

    try:
        current_url, title = controller.navigate(url)
        if not extract_dom_indices:
            return f"Stealth navigation complete: '{title}' ({current_url})"

        _elements, summary = controller.get_dom_state()
        res = f"Stealth navigation to '{title}' ({current_url}):\n\n"
        res += "Interactive DOM Elements (Use index to click or type):\n"
        res += summary if summary else "No interactive elements detected on page."
        return res
    except Exception as e:
        logger.info(f"[StealthBrowser] Live navigation failed ({e}); falling back to Crawl4AI semantic reader.")
        fallback_data = read_web_page(url)
        return (
            f"[Stealth Browser Degraded: Live browser session unavailable ({e}). "
            f"Retrieved content via Crawl4AI semantic reader]:\n\n{fallback_data}"
        )


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
        return f"Error clicking DOM element [{index}]: {e!s}"


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
        return f"Error typing into DOM element [{index}]: {e!s}"


def browse_interactive_dom(url: str) -> str:
    """
    Navigates to URL and returns an indexed semantic DOM tree [1], [2], [3]
    for high-precision, coordinate-free autonomous interaction (Browser-Use pattern).
    Gracefully degrades to Crawl4AI semantic reader if live browser cannot be launched.
    """
    controller = _get_stealth_controller()
    if controller is not None and getattr(controller, "is_available", lambda: True)():
        res = browse_website_stealth(url, extract_dom_indices=True)
        if "Degraded" not in res and "Interactive DOM Elements" in res:
            return res

    # Check CDP Bridge
    try:
        from spacev.web.cdp_bridge import CDPBridge
        cdp = CDPBridge()
        if cdp.is_browser_available():
            active_target = cdp.get_active_page()
            if active_target:
                return f"Connected to active browser via CDP (Target: '{active_target.title}' at {active_target.url})."
    except Exception:
        pass

    # Zero-failure fallback: return full distilled page/repo content via Crawl4AI semantic reader
    return read_web_page(url)

