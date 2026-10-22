"""
DOM Extraction and Interactive Element Indexer for SpaceV Hybrid Agent.
Inspired by browser-use: assigns deterministic integer indices [1], [2], [3]
to all interactive DOM nodes so local LLMs can execute actions with minimal tokens.
"""
from __future__ import annotations

from typing import Any

from hybrid_agent.state import DOMElement

EXTRACT_SCRIPT = """
() => {
    const isVisible = (el) => {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return (
            rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== 'hidden' &&
            style.display !== 'none' &&
            style.opacity !== '0'
        );
    };

    const interactiveSelectors = [
        'a[href]', 'button', 'input', 'select', 'textarea',
        '[role="button"]', '[role="link"]', '[role="checkbox"]',
        '[role="menuitem"]', '[role="tab"]', '[contenteditable="true"]',
        '[onclick]', '[tabindex]:not([tabindex="-1"])'
    ];

    const elements = document.querySelectorAll(interactiveSelectors.join(','));
    const results = [];
    let idx = 1;

    elements.forEach(el => {
        if (!isVisible(el)) return;
        const rect = el.getBoundingClientRect();
        
        let text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || el.title || '').trim();
        text = text.replace(/\\s+/g, ' ').substring(0, 80);

        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || tag;
        const href = el.getAttribute('href') || null;
        const inputType = el.getAttribute('type') || null;
        const placeholder = el.getAttribute('placeholder') || null;

        // Build a stable CSS/XPath locator
        let selector = '';
        if (el.id) {
            selector = '#' + CSS.escape(el.id);
        } else if (el.name) {
            selector = `${tag}[name="${CSS.escape(el.name)}"]`;
        } else if (placeholder) {
            selector = `${tag}[placeholder="${CSS.escape(placeholder)}"]`;
        } else {
            selector = `${tag}:nth-of-type(${Array.from(el.parentNode ? el.parentNode.children : []).indexOf(el) + 1})`;
        }

        results.push({
            index: idx++,
            tag: tag,
            text: text,
            role: role,
            selector: selector,
            href: href,
            placeholder: placeholder,
            input_type: inputType,
            rect: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            }
        });
    });

    return results;
}
"""


class DOMExtractor:
    """
    Extracts, summarizes, and maps interactable browser elements.
    """

    @staticmethod
    def extract_interactive_elements(page: Any) -> tuple[list[DOMElement], str]:
        """
        Executes in-page JS crawler and formats a high-density, low-token summary.
        """
        try:
            raw_elements = page.evaluate(EXTRACT_SCRIPT)
            elements: list[DOMElement] = []
            summary_lines = []

            for item in raw_elements[:60]:  # Cap at top 60 elements for LLM context limits
                elem: DOMElement = {
                    "index": item["index"],
                    "tag": item["tag"],
                    "text": item["text"],
                    "role": item["role"],
                    "selector": item["selector"],
                    "xpath": "",
                    "is_interactive": True,
                    "href": item.get("href"),
                    "placeholder": item.get("placeholder"),
                    "input_type": item.get("input_type"),
                }
                elements.append(elem)

                # Format compact LLM line: [1] <button> "Submit"
                desc = f"[{elem['index']}] <{elem['tag']}"
                if elem.get("input_type"):
                    desc += f' type="{elem["input_type"]}"'
                if elem.get("placeholder"):
                    desc += f' placeholder="{elem["placeholder"]}"'
                desc += ">"
                if elem.get("text"):
                    desc += f' "{elem["text"]}"'
                summary_lines.append(desc)

            summary = "\n".join(summary_lines)
            return elements, summary

        except Exception as e:
            return [], f"DOM extraction notice: {e}"
