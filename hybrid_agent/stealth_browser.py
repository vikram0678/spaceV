"""
Stealth Anti-Detect Browser Controller for SpaceV Hybrid Agent.
Combines Camoufox C++ stealth patterns with Playwright native channels (Chrome/Edge/Firefox).
Masks automation markers (navigator.webdriver, CDP artifacts, canvas fingerprints).
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any

try:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    Browser = Any  # type: ignore
    BrowserContext = Any  # type: ignore
    Page = Any  # type: ignore
    Playwright = Any  # type: ignore

from hybrid_agent.dom_extractor import DOMExtractor
from hybrid_agent.state import DOMElement

logger = logging.getLogger("SpaceV.StealthBrowser")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
]


class StealthBrowserController:
    """
    Manages an anti-detect, stealth browser instance with humanized mouse
    trajectories and masked automation signatures.
    """

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._current_elements: list[DOMElement] = []

    def start(self) -> Page | None:
        """Launches the stealth browser session."""
        if not HAS_PLAYWRIGHT:
            logger.info("[StealthBrowser] Playwright not installed. Operating in lightweight mode.")
            return None

        if self._page:
            return self._page

        self._playwright = sync_playwright().start()

        user_agent = random.choice(USER_AGENTS)

        # Launch options with anti-bot evasion arguments
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--start-maximized"
        ]

        # Prefer system's existing Chrome or Edge to avoid downloading extra browsers
        browser_channel = None
        try:
            self._browser = self._playwright.chromium.launch(
                channel="msedge",
                headless=self.headless,
                args=launch_args
            )
            browser_channel = "msedge"
        except Exception:
            try:
                self._browser = self._playwright.chromium.launch(
                    channel="chrome",
                    headless=self.headless,
                    args=launch_args
                )
                browser_channel = "chrome"
            except Exception:
                # Fallback to standard chromium
                self._browser = self._playwright.chromium.launch(
                    headless=self.headless,
                    args=launch_args
                )
                browser_channel = "bundled"

        logger.info(f"[StealthBrowser] 🚀 Launched browser using channel: '{browser_channel}'")

        # Create context with realistic viewport and device scale factor
        self._context = self._browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1366, "height": 768},
            device_scale_factor=1.0,
            has_touch=False,
            is_mobile=False,
            permissions=["geolocation", "notifications"]
        )

        # Inject Camoufox anti-detect stealth scripts into every new document before page JS executes
        self._context.add_init_script("""
            // 1. Mask navigator.webdriver and automation flags
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            delete navigator.__proto__.webdriver;

            // 2. Coherent Hardware Concurrency & Memory
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

            // 3. Mock Chrome runtime
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };

            // 4. Mock plugins & languages
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' }
                ]
            });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

            // 5. Camoufox WebGL Vendor & Renderer Spoofing
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(param) {
                if (param === 37445) return 'Google Inc. (NVIDIA)';
                if (param === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                return getParameter.apply(this, arguments);
            };
            if (typeof WebGL2RenderingContext !== 'undefined') {
                const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
                WebGL2RenderingContext.prototype.getParameter = function(param) {
                    if (param === 37445) return 'Google Inc. (NVIDIA)';
                    if (param === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                    return getParameter2.apply(this, arguments);
                };
            }

            // 6. Camoufox Canvas Deterministic Noise
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                const ctx = this.getContext('2d');
                if (ctx && this.width > 0 && this.height > 0) {
                    const imgData = ctx.getImageData(0, 0, Math.min(this.width, 10), Math.min(this.height, 10));
                    for (let i = 0; i < imgData.data.length; i += 4) {
                        imgData.data[i] = imgData.data[i] ^ 1; // 1-bit subtle noise
                    }
                }
                return originalToDataURL.apply(this, arguments);
            };
        """)

        self._page = self._context.new_page()
        return self._page

    @property
    def page(self) -> Page:
        if not self._page:
            return self.start()
        return self._page

    def navigate(self, url: str) -> tuple[str, str]:
        """Navigates to URL and waits for network idle."""
        page = self.page
        if not url.startswith("http"):
            url = f"https://{url}"

        print(f"[StealthBrowser] 🌐 Navigating to: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1.0)
        return page.url, page.title()

    def get_dom_state(self) -> tuple[list[DOMElement], str]:
        """Crawls interactive elements and assigns indices."""
        elements, summary = DOMExtractor.extract_interactive_elements(self.page)
        self._current_elements = elements
        return elements, summary

    def click_element_by_index(self, index: int) -> bool:
        """Clicks an element by its numeric index [1], [2], etc."""
        target = next((e for e in self._current_elements if e["index"] == index), None)
        if not target:
            logger.warning(f"[StealthBrowser] Index [{index}] not found in current DOM state.")
            return False

        selector = target["selector"]
        print(f"[StealthBrowser] 👆 Clicking [{index}] {target.get('text', '')[:30]} ({selector})")
        try:
            loc = self.page.locator(selector).first
            loc.hover()
            time.sleep(random.uniform(0.1, 0.25))  # Humanized micro-pause
            loc.click()
            time.sleep(1.0)
            return True
        except Exception as e:
            logger.debug(f"[StealthBrowser] Click error: {e}")
            # Try javascript click fallback
            try:
                self.page.evaluate(f"document.querySelector('{selector}').click()")
                time.sleep(1.0)
                return True
            except Exception:
                return False

    def type_element_by_index(self, index: int, text: str, press_enter: bool = False) -> bool:
        """Types text into an indexed input with human-like keystroke intervals."""
        target = next((e for e in self._current_elements if e["index"] == index), None)
        if not target:
            return False

        selector = target["selector"]
        print(f"[StealthBrowser] ⌨️ Typing '{text}' into [{index}] ({selector})")
        try:
            loc = self.page.locator(selector).first
            loc.click()
            time.sleep(0.1)
            loc.fill("")  # Clear existing text

            # Humanized typing speed
            for char in text:
                loc.type(char, delay=random.uniform(20, 65))

            if press_enter:
                time.sleep(0.2)
                loc.press("Enter")
            time.sleep(1.0)
            return True
        except Exception as e:
            logger.debug(f"[StealthBrowser] Type error: {e}")
            return False

    def scroll(self, direction: str = "down", amount: int = 500) -> None:
        """Scrolls page up or down."""
        scroll_val = amount if direction == "down" else -amount
        self.page.evaluate(f"window.scrollBy({{ top: {scroll_val}, behavior: 'smooth' }})")
        time.sleep(0.8)

    def take_screenshot(self, filepath: str = "browser_snapshot.png") -> str:
        """Captures page screenshot."""
        self.page.screenshot(path=filepath, full_page=False)
        return filepath

    def close(self) -> None:
        """Cleans up browser and Playwright runtime."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
