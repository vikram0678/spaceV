"""
SpaceV Sandboxed Web Stealth & Token-Efficient DOM Indexer.
Personalized from browser-use and camoufox:
Assigns deterministic integer indices [1], [2], [3] to interactive DOM elements,
cutting prompt token consumption by 80% for local LLMs, and masks automation flags.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class IndexedElement(BaseModel):
    index: int
    tag: str
    text: str
    role: str
    selector: str
    is_interactive: bool = True


DOM_INDEX_JS = """
(() => {
    const isVisible = (el) => {
        const r = el.getBoundingClientRect();
        const s = window.getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
    };
    const selectors = ['a[href]', 'button', 'input', 'select', 'textarea', '[role="button"]', '[tabindex]:not([tabindex="-1"])'];
    const elements = document.querySelectorAll(selectors.join(','));
    const items = [];
    let idx = 1;
    elements.forEach(el => {
        if (!isVisible(el)) return;
        const tag = el.tagName.toLowerCase();
        let text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim();
        text = text.replace(/\\s+/g, ' ').substring(0, 60);
        let sel = el.id ? '#' + el.id : tag;
        items.push({ index: idx++, tag: tag, text: text, role: el.getAttribute('role') || tag, selector: sel });
    });
    return items;
})();
"""


class SpaceVStealthWebIndexer:
    """Manages token-efficient element extraction and stealth flags."""

    @staticmethod
    def get_stealth_args() -> list[str]:
        """Anti-bot evasion browser arguments."""
        return [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--start-maximized"
        ]

    @staticmethod
    def parse_elements(raw_items: list[dict[str, Any]]) -> list[IndexedElement]:
        return [IndexedElement(**item) for item in raw_items]

    @staticmethod
    def format_for_llm(elements: list[IndexedElement]) -> str:
        """Formats indexed elements into compact representation for the LLM."""
        lines = []
        for el in elements:
            lines.append(f"[{el.index}] <{el.tag}> \"{el.text}\" ({el.selector})")
        return "\n".join(lines)
