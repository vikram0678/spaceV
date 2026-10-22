"""
SpaceV Web Subsystem: Noise-Filtered High-Density LLM Content Extractor.
Engineered from Crawl4AI content filtering & table preservation strategies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ExtractedContent:
    title: str
    markdown: str
    raw_token_estimate: int
    compressed_token_estimate: int
    compression_ratio: float
    tables_found: int


class ContentExtractor:
    """
    Strips DOM noise (ads, navbars, cookie consent, tracking scripts) and produces
    dense, token-optimized Markdown for LLM reasoning.
    """

    # Elements to completely discard
    _STRIP_TAGS = re.compile(
        r"<(script|style|nav|footer|noscript|svg|iframe|header|aside)[^>]*>.*?</\1>",
        re.IGNORECASE | re.DOTALL,
    )

    # Cookie and ad containers
    _JUNK_SELECTORS = re.compile(
        r'<div[^>]*(id|class)=["\'][^"\']*(cookie|banner|ad-|advert|popup|modal)[^"\']*["\'][^>]*>.*?</div>',
        re.IGNORECASE | re.DOTALL,
    )

    @classmethod
    def extract_title(cls, html: str) -> str:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else "Untitled Page"

    @classmethod
    def extract_tables(cls, html: str) -> tuple[str, int]:
        """Converts HTML <table> elements into clean Markdown tables."""
        tables_found = 0

        def table_replacer(match: re.Match) -> str:
            nonlocal tables_found
            tables_found += 1
            table_html = match.group(0)
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.IGNORECASE | re.DOTALL)
            if not rows:
                return ""

            md_rows: List[str] = []
            for r_idx, row in enumerate(rows):
                cells = re.findall(r"<(th|td)[^>]*>(.*?)</\1>", row, re.IGNORECASE | re.DOTALL)
                clean_cells = [re.sub(r"<[^>]+>", "", c[1]).strip() for c in cells]
                if clean_cells:
                    md_rows.append("| " + " | ".join(clean_cells) + " |")
                    if r_idx == 0:
                        md_rows.append("| " + " | ".join(["---"] * len(clean_cells)) + " |")

            return "\n\n" + "\n".join(md_rows) + "\n\n"

        html_with_tables = re.sub(r"<table[^>]*>.*?</table>", table_replacer, html, flags=re.IGNORECASE | re.DOTALL)
        return html_with_tables, tables_found

    @classmethod
    def to_clean_markdown(cls, html: str) -> ExtractedContent:
        raw_tokens = len(html) // 4
        title = cls.extract_title(html)

        # 1. Strip script, style, nav, footer, header
        cleaned = cls._STRIP_TAGS.sub("", html)
        # 2. Strip cookie dialogs & ads
        cleaned = cls._JUNK_SELECTORS.sub("", cleaned)
        # 3. Extract and preserve tables
        cleaned, tables_count = cls.extract_tables(cleaned)

        # 4. Convert headers
        cleaned = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n# \1\n", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", cleaned, flags=re.IGNORECASE | re.DOTALL)

        # 5. Convert lists
        cleaned = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", cleaned, flags=re.IGNORECASE | re.DOTALL)

        # 6. Strip all remaining tags
        text = re.sub(r"<[^>]+>", " ", cleaned)

        # 7. Normalize whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        final_md = f"# {title}\n\n{text}"
        compressed_tokens = max(1, len(final_md) // 4)
        ratio = round(1.0 - (compressed_tokens / max(1, raw_tokens)), 3)

        return ExtractedContent(
            title=title,
            markdown=final_md,
            raw_token_estimate=raw_tokens,
            compressed_token_estimate=compressed_tokens,
            compression_ratio=ratio,
            tables_found=tables_count,
        )
