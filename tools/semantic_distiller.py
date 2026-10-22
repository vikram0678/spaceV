"""
Semantic Web Distiller & Token Compressor for SpaceV.
Inspired by opensourcetools/crawl4ai.
Converts noisy HTML pages into clean, LLM-ready semantic Markdown,
stripping navigation, ads, SVG noise, scripts, and styling to achieve 95%+ token reduction.
"""
import re

import markdownify
from bs4 import BeautifulSoup


def distill_html_to_markdown(raw_html: str, max_chars: int = 12000) -> str:
    """
    Parses raw HTML, strips boilerplate/clutter elements, and converts the
    remaining substantive content into compact, high-density Markdown.
    """
    if not raw_html or not raw_html.strip():
        return ""

    try:
        soup = BeautifulSoup(raw_html, "html.parser")

        # 1. Strip non-content / boilerplate tags
        tags_to_remove = [
            "script", "style", "noscript", "svg", "canvas", "iframe",
            "nav", "footer", "header", "aside", "form"
        ]
        for tag in soup.find_all(tags_to_remove):
            tag.decompose()

        # 2. Strip elements with common noise class/id patterns (ads, cookies, tracking)
        noise_pattern = re.compile(
            r"(cookie|banner|advertisement|modal|popup|newsletter|sidebar|tracker|analytics|social-share)",
            re.I
        )
        for noise in soup.find_all(attrs={"class": noise_pattern}):
            noise.decompose()
        for noise in soup.find_all(attrs={"id": noise_pattern}):
            noise.decompose()

        # 3. Target main content container if present
        main_content = soup.find("main") or soup.find("article") or soup.find("div", {"id": re.compile(r"content|main", re.I)}) or soup.body or soup

        # 4. Convert cleanly to Markdown
        md_text = markdownify.markdownify(
            str(main_content),
            heading_style="ATX",
            strip=["a", "img"]  # Strip inline links & images to preserve context tokens
        )

        # 5. Clean up excessive whitespace and blank lines
        md_clean = re.sub(r"\n{3,}", "\n\n", md_text).strip()

        # 6. Apply character bound to prevent context overflow (~3,000 tokens max)
        if len(md_clean) > max_chars:
            md_clean = md_clean[:max_chars] + "\n\n...[Content truncated for token efficiency]..."

        return md_clean

    except Exception:
        # Graceful fallback: regex-based tag stripping
        clean_text = re.sub(r"<[^>]+>", " ", raw_html)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        return clean_text[:max_chars]
