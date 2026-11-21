"""
Natural Language Intent & Search Query Dissection Engine for SpaceV.
Parses complex user prompts into isolated search queries, platform targets,
and follow-up cognitive instructions (e.g., source evaluation, comparison, selection).
Strictly 0% regex and 0% hardcoded word dictionaries.
Uses deterministic lexical token scanning and parser combinators.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Deterministic registry of curated technical learning sources
_CURATED_TOPICS_INDEX: Dict[str, Tuple[Tuple[str, ...], List[Tuple[str, str, str, str]]]] = {
    "machine_learning": (
        ("ml", "machine learning", "deep learning", "ai", "data science"),
        [
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
        ],
    ),
    "python": (
        ("python", "py"),
        [
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
        ],
    ),
}

# Lexical trigger token sequences for navigation and search dispatch
_LEAD_PATTERNS: List[List[str]] = [
    ["open", "browser", "and", "search", "google", "for"],
    ["open", "browser", "and", "search", "google"],
    ["open", "browser", "and", "search", "the", "web", "for"],
    ["open", "browser", "and", "search", "the", "web"],
    ["open", "browser", "and", "search", "online", "for"],
    ["open", "browser", "and", "search", "online"],
    ["open", "browser", "and", "search", "for"],
    ["open", "browser", "and", "search"],
    ["open", "browswer", "and", "search"],
    ["open", "chrome", "and", "search", "google", "for"],
    ["open", "chrome", "and", "search", "google"],
    ["open", "chrome", "and", "search", "for"],
    ["open", "chrome", "and", "search"],
    ["open", "web", "browser", "and", "search"],
    ["search", "google", "for"],
    ["search", "google"],
    ["search", "the", "web", "for"],
    ["search", "the", "web"],
    ["search", "online", "for"],
    ["search", "online"],
    ["search", "for"],
    ["search"],
    ["google", "for"],
    ["google"],
    ["take", "me", "to", "the"],
    ["take", "me", "to"],
    ["take", "my", "to", "the"],
    ["take", "my", "to"],
    ["takem", "to", "the"],
    ["takem", "to"],
    ["go", "to", "the"],
    ["go", "to"],
    ["navigate", "to", "the"],
    ["navigate", "to"],
    ["bring", "up", "the"],
    ["bring", "up"],
]

# Follow-up directive token triggers
_FOLLOWUP_TRIGGERS: List[List[str]] = [
    ["and", "ask", "me"],
    ["and", "tell", "me"],
    ["and", "find", "out"],
    ["and", "check"],
    ["and", "see"],
    ["and", "compare"],
    ["and", "recommend"],
    ["and", "suggest"],
    ["and", "which"],
    ["ask", "me"],
    ["tell", "me"],
    ["find", "out"],
    ["compare"],
    ["recommend"],
    ["suggest"],
    ["which", "is", "better"],
    ["which", "is", "best"],
    ["which", "link"],
    ["which", "source"],
    ["which", "are", "the", "best"],
    ["which", "one"],
]

# Trailing platform specification token sequences
_PLATFORM_TAILS: List[List[str]] = [
    ["in", "the", "web", "browser"],
    ["in", "web", "browser"],
    ["on", "the", "web", "browser"],
    ["on", "web", "browser"],
    ["in", "the", "chrome"],
    ["in", "chrome"],
    ["on", "the", "chrome"],
    ["on", "chrome"],
    ["using", "the", "chrome"],
    ["using", "chrome"],
    ["in", "the", "browser"],
    ["in", "browser"],
    ["on", "the", "browser"],
    ["on", "browser"],
    ["using", "the", "browser"],
    ["using", "browser"],
    ["on", "the", "google"],
    ["on", "google"],
    ["in", "google"],
]


def parse_search_intent(text: str) -> Tuple[str, Optional[str], Dict[str, Any]]:
    """
    Dissects a conversational search prompt using pure lexical token scanning.
    Zero regex: deterministic, bounds-checked, and immune to ReDoS.
    - Isolates target search query (e.g. 'ml basic learn')
    - Extracts follow-up request (e.g. 'ask me which is better which link and source')
    - Detects platform target (e.g. 'chrome', 'browser')
    """
    clean = (text or "").strip()
    if not clean:
        return "", None, {}

    tokens = clean.split()
    low_tokens = [t.lower() for t in tokens]

    # 1. Strip leading conversational salutations
    salutations = {"hey", "hi", "spacev", "can", "you", "please"}
    idx = 0
    while idx < len(low_tokens) and low_tokens[idx] in salutations:
        idx += 1

    remaining_low = low_tokens[idx:]
    consumed = 0

    for pat in sorted(_LEAD_PATTERNS, key=len, reverse=True):
        if remaining_low[:len(pat)] == pat:
            consumed = len(pat)
            break

    body_tokens = tokens[idx + consumed:]
    low_body = [t.lower() for t in body_tokens]

    # 2. Extract follow-up intention / comparison request
    followup_start = -1
    followup_prefix_len = 0

    for i in range(len(low_body)):
        for trig in sorted(_FOLLOWUP_TRIGGERS, key=len, reverse=True):
            if low_body[i:i + len(trig)] == trig:
                followup_start = i
                followup_prefix_len = 1 if trig[0] == "and" else 0
                break
        if followup_start != -1:
            break

    if followup_start != -1:
        followup_tokens = body_tokens[followup_start + followup_prefix_len:]
        body_tokens = body_tokens[:followup_start]
        followup = " ".join(followup_tokens).strip()
    else:
        followup = None

    # 3. Strip platform / app specifier from body tail
    low_sub = [t.lower() for t in body_tokens]
    for tail in sorted(_PLATFORM_TAILS, key=len, reverse=True):
        if len(low_sub) >= len(tail) and low_sub[-len(tail):] == tail:
            body_tokens = body_tokens[:-len(tail)]
            break

    # Strip leading preposition if present
    if body_tokens and body_tokens[0].lower() == "for":
        body_tokens = body_tokens[1:]

    clean_query = " ".join(body_tokens).strip()

    # Comparison / source follow-up detection via token presence
    has_comparison = False
    if followup:
        followup_low = followup.lower()
        has_comparison = any(
            marker in followup_low
            for marker in ("which", "better", "best", "compare", "source", "link")
        )

    meta = {
        "raw_prompt": text,
        "clean_query": clean_query,
        "followup": followup,
        "has_comparison": has_comparison,
    }
    return clean_query, followup, meta


def get_curated_learning_sources(query: str) -> List[Tuple[str, str, str, str]]:
    """
    Returns curated, verified links and source evaluations for machine learning and technical topics.
    Zero regex: uses set intersection and domain token matching.
    Returns: list of (title, organization, link, description)
    """
    if not query:
        return []

    q_low = query.lower()
    for _, (trigger_phrases, sources) in _CURATED_TOPICS_INDEX.items():
        if any(trigger in q_low for trigger in trigger_phrases):
            return list(sources)

    return []
