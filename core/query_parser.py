"""
Natural Language Intent & Search Query Dissection Engine for SpaceV.
Parses complex user prompts into isolated search queries, platform targets,
and follow-up cognitive instructions (e.g., source evaluation, comparison, selection).
Prevents full-sentence leaking into Google Search.
"""
from __future__ import annotations

import re
from typing import Any, Optional


def parse_search_intent(text: str) -> tuple[str, Optional[str], dict[str, Any]]:
    """
    Dissects a conversational search prompt like a human assistant:
    - Isolates target search query (e.g. 'ml basic learn')
    - Extracts follow-up request (e.g. 'ask me which is better which link and source')
    - Detects platform target (e.g. 'chrome', 'browser')
    """
    clean = (text or "").strip()
    if not clean:
        return "", None, {}

    # 1. Strip leading trigger keywords
    m_lead = re.match(
        r"^(?:hey\s+|hi\s+|spacev\s+|can\s+you\s+(?:please\s+)?|please\s+)?"
        r"(?:(?:take\s*m[ye]\s+to|takem\s+to|go\s+to|navigate\s+to|bring\s+up)\s+(?:the\s+)?|"
        r"(?:open\s+(?:browser|browswer|chrome|web\s+browser)\s+and\s+)?"
        r"(?:search\s+(?:google\s+(?:for\s+)?|the\s+web\s+(?:for\s+)?|online\s+(?:for\s+)?|for\s+)?|google\s+))(.+)$",
        clean,
        re.IGNORECASE,
    )
    body = m_lead.group(1).strip() if m_lead else clean

    # 2. Extract follow-up intention / comparison request
    followup = None
    m_follow = re.search(
        r"\s+(?:and\s+)?((?:(?:ask\s+me|tell\s+me|find\s+out|check|see|compare|recommend|suggest)\s+(?:which|what)?\s*(?:is\s+better|is\s+best|link|source|are\s+the\s+best|one).*|which\s+(?:is\s+better|link|source).*))$",
        body,
        re.IGNORECASE,
    )
    if m_follow:
        followup = m_follow.group(1).strip()
        body = body[: m_follow.start()].strip()

    # 3. Strip platform / app specifier (e.g. 'in the chrome', 'in chrome', 'on browser')
    body = re.sub(
        r"\s+(?:in|on|using)\s+(?:the\s+)?(?:chrome|browser|web\s+browser|google)\b",
        "",
        body,
        flags=re.IGNORECASE,
    ).strip()
    body = re.sub(r"^(?:for\s+)", "", body, flags=re.IGNORECASE).strip()
    body = re.sub(r"\s+on\s+google$", "", body, flags=re.IGNORECASE).strip()

    meta = {
        "raw_prompt": text,
        "clean_query": body,
        "followup": followup,
        "has_comparison": bool(
            followup
            and any(
                k in followup.lower()
                for k in ["which", "better", "best", "compare", "source", "link"]
            )
        ),
    }
    return body, followup, meta


def get_curated_learning_sources(query: str) -> list[tuple[str, str, str, str]]:
    """
    Returns curated, verified links and source evaluations for machine learning and technical topics.
    Returns: list of (title, organization, link, description)
    """
    q_low = query.lower()
    if any(k in q_low for k in ["ml", "machine learning", "deep learning", "ai", "data science"]):
        return [
            (
                "Kaggle Learn: Intro to Machine Learning",
                "Kaggle / Google",
                "https://www.kaggle.com/learn/intro-to-machine-learning",
                "Best for hands-on, practical coding in free browser notebooks. Builds working models in minutes without setup.",
            ),
            (
                "Coursera: Machine Learning Specialization",
                "DeepLearning.AI / Andrew Ng",
                "https://www.coursera.org/specializations/machine-learning-introduction",
                "The world's gold standard for understanding foundational math, intuition, and algorithm mechanics.",
            ),
            (
                "Google Developers: ML Crash Course",
                "Google Developers",
                "https://developers.google.com/machine-learning/crash-course",
                "Fast-paced visual fundamentals with interactive exercises, TensorFlow APIs, and real Google case studies.",
            ),
            (
                "Fast.ai: Practical Deep Learning for Coders",
                "Fast.ai",
                "https://course.fast.ai",
                "Best top-down, coder-first curriculum. Great for training state-of-the-art models before diving into math.",
            ),
        ]
    elif any(k in q_low for k in ["python", "py"]):
        return [
            (
                "Official Python Tutorial",
                "Python Software Foundation",
                "https://docs.python.org/3/tutorial/",
                "The definitive, comprehensive reference straight from Python's creators.",
            ),
            (
                "Real Python",
                "Real Python",
                "https://realpython.com/",
                "High-quality, practical articles with clear code walkthroughs.",
            ),
            (
                "W3Schools Python",
                "W3Schools",
                "https://www.w3schools.com/python/",
                "Quick beginner reference with instant interactive code tryouts.",
            ),
        ]
    return []

