import logging
import json
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger("SpaceV.WebTools")


def search_google(query: str, click_first_result: bool = False) -> str:
    """
    Searches Google in the default web browser for the given query.
    When autonomous cursor mode is active, navigates Chrome like a human and optionally clicks the first result.
    Automatically parses out conversational and platform noise (e.g. 'in chrome and ask me...').
    """
    import re
    from core.platform_adapter import PlatformAdapter
    from core.query_parser import parse_search_intent
    from tools.gui_tools import HAS_PYAUTOGUI, gui_human_search_and_open, gui_search_google_browser, safety

    # Pure query isolation: strips 'in the chrome', 'and ask me...', etc.
    clean_q, _, _ = parse_search_intent(query)
    target_q = clean_q or query

    if safety.autonomous_mode_enabled and HAS_PYAUTOGUI and not PlatformAdapter.is_wsl():
        if click_first_result or any(k in target_q.lower() for k in ["click", "first result", "open result", "like human", "like a human"]):
            clean_click_q = re.sub(r"\b(?:and\s+)?(?:click|open)\s+(?:the\s+)?(?:first|top)?\s*results?\b", "", target_q, flags=re.IGNORECASE).strip()
            return gui_human_search_and_open(clean_click_q or target_q, click_first_result=True)
        return gui_search_google_browser(target_q)

    try:
        encoded_query = urllib.parse.quote_plus(target_q)
        url = f"https://www.google.com/search?q={encoded_query}"
        PlatformAdapter.open_url(url)
        return f"Opened Google search for: '{target_q}'"
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
    When autonomous cursor mode is active, uses human-like browser navigation.
    """
    from core.platform_adapter import PlatformAdapter
    from tools.gui_tools import HAS_PYAUTOGUI, gui_open_browser_urls, sanitize_url_tokens, safety

    clean_u = sanitize_url_tokens(url.strip())
    if not clean_u.startswith("http://") and not clean_u.startswith("https://"):
        clean_u = "https://" + clean_u

    if safety.autonomous_mode_enabled and HAS_PYAUTOGUI and not PlatformAdapter.is_wsl():
        return gui_open_browser_urls([clean_u])

    try:
        PlatformAdapter.open_url(clean_u)
        return f"Opened website: {clean_u}"
    except Exception as e:
        return f"Failed to open website: {e!s}"


def open_browser_urls(urls: list[str] | str, delay_sec: float = 0.5) -> str:
    """
    Opens multiple URLs sequentially in the user's default browser (Chrome/Edge/Firefox)
    with human-like pacing to avoid overwhelming system resources.
    When autonomous cursor mode is active, glides mouse and types in Chrome like a real human.
    """
    import time
    from core.platform_adapter import PlatformAdapter
    from tools.gui_tools import HAS_PYAUTOGUI, gui_open_browser_urls, sanitize_url_tokens, safety

    target_urls: list[str] = []
    if isinstance(urls, str):
        clean = urls.strip()
        if clean.startswith("[") and clean.endswith("]"):
            try:
                import json
                target_urls = [str(u) for u in json.loads(clean)]
            except Exception:
                target_urls = [u.strip().strip("'\"") for u in clean.strip("[]").split(",") if u.strip()]
        elif "\n" in clean:
            target_urls = [u.strip().strip("'\"") for u in clean.split("\n") if u.strip()]
        elif "," in clean:
            target_urls = [u.strip().strip("'\"") for u in clean.split(",") if u.strip()]
        else:
            target_urls = [clean]
    elif isinstance(urls, list):
        target_urls = [str(u).strip() for u in urls if str(u).strip()]

    if not target_urls:
        return "No valid URLs provided to open."

    # When Cursor Mode is active, execute physical human mouse and keyboard navigation
    if safety.autonomous_mode_enabled and HAS_PYAUTOGUI and not PlatformAdapter.is_wsl():
        return gui_open_browser_urls(target_urls, delay_sec=delay_sec)

    clamped = target_urls[:20]
    opened = 0
    pacing = max(0.1, min(delay_sec, 5.0))

    for idx, raw_u in enumerate(clamped, 1):
        clean_u = sanitize_url_tokens(raw_u)
        if not clean_u.startswith("http://") and not clean_u.startswith("https://"):
            clean_u = "https://" + clean_u
        try:
            PlatformAdapter.open_url(clean_u)
            opened += 1
            if idx < len(clamped):
                time.sleep(pacing)
        except Exception as e:
            logger.warning(f"Failed to open URL '{clean_u}': {e}")

    return f"Successfully opened {opened} of {len(target_urls)} links in your browser."


def fetch_github_repo_summary(url: str) -> str | None:
    """
    Zero-browser high-speed GitHub repository distiller (Crawl4AI pattern).
    Fetches raw README markdown and API metadata in <100ms with zero browser overhead.
    """
    import urllib.request

    parsed = urllib.parse.urlsplit(url)
    if (parsed.hostname or "").lower() not in {"github.com", "www.github.com"}:
        return None
    path_parts = [urllib.parse.unquote(part) for part in parsed.path.strip("/").split("/") if part]
    # This fast path is only for repository roots. Issue, pull-request, file,
    # and API URLs must keep their full path and use their own reader below.
    if len(path_parts) != 2:
        return None
    owner, repo = path_parts
    repo = repo.removesuffix(".git")
    if not owner or not repo:
        return None

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


def _github_issue_api_url(url: str) -> str | None:
    """Map a GitHub issue URL to its REST API resource without losing path parts."""
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    parts = [urllib.parse.unquote(part) for part in parsed.path.strip("/").split("/") if part]

    if host in {"github.com", "www.github.com"}:
        if len(parts) >= 4 and parts[2] == "issues" and parts[3].isdigit():
            suffix = "/comments" if len(parts) >= 5 and parts[4] == "comments" else ""
            return f"https://api.github.com/repos/{parts[0]}/{parts[1]}/issues/{parts[3]}{suffix}"
        return None

    if host == "api.github.com" and len(parts) >= 5 and parts[:1] == ["repos"] and parts[3] == "issues" and parts[4].isdigit():
        # Preserve caller-supplied API query parameters and subresources.
        return urllib.parse.urlunsplit(("https", "api.github.com", parsed.path, parsed.query, ""))
    return None


def _github_api_get_json(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "SpaceV-Cybernetic-Agent/2.0",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def fetch_github_issue_content(url: str) -> str:
    """Read an issue and its discussion from GitHub's API, preserving issue identity."""
    api_url = _github_issue_api_url(url)
    if not api_url:
        return f"Failed: URL is not a supported GitHub issue URL: {url}"

    try:
        payload = _github_api_get_json(api_url)
        if isinstance(payload, list):
            lines = [f"GitHub issue comments from {api_url}"]
            for comment in payload[:30]:
                author = (comment.get("user") or {}).get("login", "unknown")
                lines.extend([f"\n### @{author}", str(comment.get("body") or "(empty comment)")])
            if len(payload) > 30:
                lines.append(f"\n[Showing 30 of {len(payload)} comments]")
            return "\n".join(lines)

        if not isinstance(payload, dict) or "title" not in payload:
            return f"Failed: GitHub API returned an unexpected issue response for {api_url}."

        issue_url = str(payload.get("html_url") or url)
        lines = [
            f"# {payload.get('title', '(untitled issue)')}",
            f"Issue: {issue_url}",
            f"State: {payload.get('state', 'unknown')}",
            f"Author: @{(payload.get('user') or {}).get('login', 'unknown')}",
            f"Created: {payload.get('created_at', 'unknown')}",
            "\n## Issue description\n",
            str(payload.get("body") or "(No issue description.)"),
        ]

        comments_count = int(payload.get("comments") or 0)
        if comments_count:
            # Build the comments endpoint from the validated issue API URL.
            endpoint = api_url.split("?", 1)[0].rstrip("/") + "/comments?per_page=30"
            try:
                comments = _github_api_get_json(endpoint)
                if isinstance(comments, list):
                    lines.append(f"\n## Discussion ({min(len(comments), 30)} of {comments_count} comments shown)\n")
                    for comment in comments[:30]:
                        author = (comment.get("user") or {}).get("login", "unknown")
                        lines.extend([f"### @{author}", str(comment.get("body") or "(empty comment)")])
            except Exception as exc:
                lines.append(f"\n[Issue comments could not be fetched: {type(exc).__name__}: {exc}]")
        content = "\n".join(lines)
        if len(content) > 12000:
            content = content[:12000] + "\n...[Issue content truncated at 12000 characters]..."
        return content
    except Exception as exc:
        return f"Failed to fetch GitHub issue at {url}: {type(exc).__name__}: {exc}"


def fetch_github_api_content(url: str) -> str:
    """Return a bounded, readable representation of a GitHub API response."""
    try:
        payload = _github_api_get_json(url)
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(content) > 12000:
            content = content[:12000] + "\n...[GitHub API response truncated]..."
        return f"=== GitHub API response: {url} ===\n\n{content}"
    except Exception as exc:
        return f"Failed to fetch GitHub API URL {url}: {type(exc).__name__}: {exc}"


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

    # Preserve API/issue resource paths before considering the repo README shortcut.
    parsed_url = urllib.parse.urlsplit(url)
    if (parsed_url.hostname or "").lower() == "api.github.com":
        if _github_issue_api_url(url):
            return fetch_github_issue_content(url)
        return fetch_github_api_content(url)
    if _github_issue_api_url(url):
        return fetch_github_issue_content(url)

    # Tier 1: Specialized GitHub repository-root fast path only.
    if (parsed_url.hostname or "").lower() in {"github.com", "www.github.com"}:
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

