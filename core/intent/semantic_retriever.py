"""
Hybrid Semantic & Lexical Capability Retriever for SpaceV.
Maps natural language user intents to registered capabilities using cached
subword hypersphere vector projections and lexical token overlap without cloud API latency.
"""

from __future__ import annotations

import math
import re
import time
from typing import Any

from core.intent.capability_registry import Capability, capability_registry


def _fnv1a(s: str) -> int:
    h = 2166136261
    for b in s.encode("utf-8"):
        h = (h ^ b) * 16777619
        h &= 0xFFFFFFFF
    return h


# Domain salience weights for high-signal technical and system terms
DOMAIN_SALIENT_WEIGHTS: dict[str, float] = {
    # System & Hardware
    "ram": 5.0, "cpu": 5.0, "memory": 4.5, "hardware": 4.0, "diagnostics": 4.0,
    "battery": 4.5, "stats": 3.5, "performance": 3.5, "network": 4.5, "wifi": 5.0,
    "ip": 4.5, "internet": 4.0, "lock": 5.0, "recycle": 5.0, "trash": 5.0, "purge": 4.5,
    "brightness": 5.0, "dim": 4.5, "screen": 3.0, "display": 3.0, "monitor": 3.0,
    # Media & Audio
    "mute": 5.5, "unmute": 5.5, "silence": 5.0, "quiet": 4.5, "quieter": 4.5, "hush": 5.0,
    "volume": 4.5, "louder": 4.5, "crank": 4.5, "audio": 4.0, "sound": 3.5,
    "music": 4.0, "song": 4.0, "track": 4.0, "skip": 4.5, "next": 3.5, "previous": 4.0,
    "pause": 4.5, "resume": 4.0,
    # Apps & Windows
    "screenshot": 5.0, "snapshot": 4.5, "capture": 4.0, "clipboard": 5.0,
    "window": 4.0, "focused": 4.0, "active": 3.0, "processes": 4.5, "running": 3.5,
    "kill": 5.0, "terminate": 5.0, "timer": 5.0, "countdown": 4.5,
    # Conversational & Presence
    "awake": 4.5, "alive": 4.5, "ping": 4.5, "introduce": 4.5, "capabilities": 4.5,
    # Files & Dev
    "file": 3.0, "folder": 3.5, "directory": 3.5, "editor": 4.5, "vscode": 4.5,
    "notepad": 4.5, "code": 3.5, "desktop": 3.5, "workspace": 3.5,
    # Web & Career
    "search": 3.5, "google": 4.5, "youtube": 5.0, "video": 3.5, "jobs": 5.0,
    "internship": 5.0, "hiring": 4.5, "career": 4.5,
}


# Stop words that dilute vector similarity
STOP_WORDS: set[str] = {
    "a", "about", "after", "all", "also", "an", "and", "any", "are", "as", "at", "be",
    "because", "been", "before", "being", "between", "both", "but", "by", "can", "could",
    "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from", "further",
    "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him", "himself",
    "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more",
    "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once", "only",
    "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which",
    "while", "who", "whom", "why", "with", "would", "you", "your", "yours", "yourself",
    "yourselves", "bit", "little", "please", "sir", "buddy", "bro", "hey", "hello"
}


def encode_intent_vector(text: str, dim: int = 4096) -> dict[int, float]:
    """
    Encodes text into a normalized sparse semantic feature vector using
    salience weighting, stop-word attenuation, word hashing, and character n-grams.
    """
    clean = text.lower().strip()
    if not clean:
        return {}

    vec: dict[int, float] = {}
    words = re.findall(r"\b[a-z0-9_+#'-]+\b", clean)

    # 1. Whole word tokens with salience weighting and stop-word attenuation
    for w in words:
        if w in STOP_WORDS:
            weight = 0.15
        else:
            weight = DOMAIN_SALIENT_WEIGHTS.get(w, 1.5 + min(len(w) * 0.2, 2.0))
        h = _fnv1a(w) % dim
        vec[h] = vec.get(h, 0.0) + weight

    # 2. Subword 3-grams and 4-grams for morphology and typo resilience
    # Strip stop words from n-gram calculation to keep subword features discriminative
    content_words = [w for w in words if w not in STOP_WORDS]
    content_str = "".join(content_words) if content_words else clean.replace(" ", "")

    for i in range(max(0, len(content_str) - 2)):
        h3 = _fnv1a(content_str[i:i+3]) % dim
        vec[h3] = vec.get(h3, 0.0) + 0.35

    for i in range(max(0, len(content_str) - 3)):
        h4 = _fnv1a(content_str[i:i+4]) % dim
        vec[h4] = vec.get(h4, 0.0) + 0.25

    # 3. L2 unit normalization
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm > 0:
        for k in vec:
            vec[k] /= norm

    return vec


def cosine_similarity(v1: dict[int, float], v2: dict[int, float]) -> float:
    """Computes cosine similarity between two normalized sparse vectors."""
    if not v1 or not v2:
        return 0.0
    # Dot product of normalized vectors equals cosine similarity
    if len(v1) > len(v2):
        v1, v2 = v2, v1
    return sum(v1[k] * v2[k] for k in v1 if k in v2)


class SemanticCapabilityRetriever:
    """
    Indexes all registered capabilities into a cached vector space
    using multi-centroid outcome representations and performs sub-millisecond
    similarity search against incoming user goals.
    """

    def __init__(self, registry=None):
        self.registry = registry or capability_registry
        # List of (Capability, list of (vector, lexical_tokens))
        self._index: list[tuple[Capability, list[tuple[dict[int, float], set[str]]]]] = []
        self._build_index()

    def _build_index(self) -> None:
        """Constructs multi-centroid outcome index from capability descriptions and individual outcomes."""
        self._index.clear()
        for cap in self.registry.list_all():
            centroids: list[tuple[dict[int, float], set[str]]] = []

            # 1. Main capability description centroid
            desc_text = f"{cap.name.replace('.', ' ')} {cap.description}"
            d_vec = encode_intent_vector(desc_text)
            d_toks = set(re.findall(r"\b[a-z0-9_+#]+\b", desc_text.lower())) - STOP_WORDS
            centroids.append((d_vec, d_toks))

            # 2. Individual supported outcome centroids (length-invariant focused targets)
            for outcome in cap.supported_outcomes:
                o_vec = encode_intent_vector(outcome)
                o_toks = set(re.findall(r"\b[a-z0-9_+#]+\b", outcome.lower())) - STOP_WORDS
                centroids.append((o_vec, o_toks))

            self._index.append((cap, centroids))

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.15,
    ) -> list[tuple[Capability, float]]:
        """
        Retrieves top-k capabilities matching the user query with calibrated confidence scores.
        Returns a sorted list of (Capability, score) tuples.
        """
        if not query or not query.strip():
            return []

        q_vec = encode_intent_vector(query)
        q_words = set(re.findall(r"\b[a-z0-9_+#]+\b", query.lower()))
        q_tokens = q_words - STOP_WORDS
        if not q_tokens:
            q_tokens = q_words  # fallback if all stop words

        scored_candidates: list[tuple[Capability, float]] = []

        for cap, centroids in self._index:
            best_cap_score = 0.0

            for c_vec, c_tokens in centroids:
                # 1. Dense/Sparse Vector Semantic Similarity (0.0 to 1.0)
                sem_score = cosine_similarity(q_vec, c_vec)

                # 2. Lexical Token Overlap Bonus (Jaccard-like intersection of content words)
                overlap = q_tokens & c_tokens
                lex_score = len(overlap) / max(1, len(q_tokens)) if q_tokens else 0.0

                # 3. Hybrid Blended Score (65% semantic embedding + 35% lexical overlap)
                blended = (0.65 * sem_score) + (0.35 * lex_score)
                if blended > best_cap_score:
                    best_cap_score = blended

            if best_cap_score >= min_score:
                scored_candidates.append((cap, round(best_cap_score, 4)))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        return scored_candidates[:top_k]

    def evaluate_separation(
        self,
        candidates: list[tuple[Capability, float]]
    ) -> tuple[float, bool]:
        """
        Evaluates the score margin between the top-1 and top-2 candidates.
        Returns (margin, is_ambiguous).
        """
        if not candidates:
            return 0.0, True
        if len(candidates) == 1:
            return 1.0, False

        top1_score = candidates[0][1]
        top2_score = candidates[1][1]
        margin = top1_score - top2_score

        # If top score is below reliable recognition threshold (<0.22)
        # or margin between top-1 and top-2 is narrow (< 0.05) without strong dominance (<0.60):
        is_ambiguous = (top1_score < 0.22) or (margin < 0.05 and top1_score < 0.60)
        return round(margin, 4), is_ambiguous


semantic_retriever = SemanticCapabilityRetriever()
