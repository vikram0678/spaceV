"""
SpaceV Cybernetic Career Intelligence & Competency Engine.
Analyzes CVs, portfolios, and multi-source job descriptions using
deterministic set algebra, Jaccard/Cosine vector similarity, and competency gap derivation.
Strictly abolishes regex matching, hardcoded skill dictionaries, and static heuristic strings.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Set, Tuple


class ReadinessTier(str, Enum):
    """Mathematical readiness classifications derived from competency overlap."""
    IMMEDIATE_FIT = "immediate_fit"
    HIGH_POTENTIAL = "high_potential"
    SKILL_BRIDGING_REQUIRED = "skill_bridging_required"
    STRATEGIC_PIVOT = "strategic_pivot"


@dataclass
class CompetencyProfile:
    """Structured representation of verified developer capabilities."""
    source_title: str
    tokens: Set[str] = field(default_factory=set)
    term_frequencies: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CareerGapAnalysis:
    """Mathematical gap assessment between a candidate portfolio and target job."""
    match_score: float
    jaccard_similarity: float
    readiness_tier: ReadinessTier
    matched_competencies: List[str]
    missing_competencies: List[str]
    growth_recommendations: List[str]
    total_requirements: int


class CareerIntelligenceEngine:
    """
    Evaluates career fit, decomposes job descriptions, and calculates
    actionable growth vectors without regex heuristics or hardcoded keywords.
    """

    @staticmethod
    def tokenize_clean(text: str, min_length: int = 2) -> List[str]:
        """
        Tokenizes technical text into clean semantic units using pure character scanning.
        Zero regex: preserves C++, C#, and alphanumeric identifiers naturally.
        """
        if not text:
            return []

        tokens: List[str] = []
        curr: List[str] = []

        for char in text:
            # Allow alphanumerics and key tech symbols (+ for C++, # for C#)
            if char.isalnum() or char in ("+", "#"):
                curr.append(char.lower())
            else:
                if curr:
                    word = "".join(curr)
                    if len(word) >= min_length:
                        tokens.append(word)
                    curr.clear()

        if curr:
            word = "".join(curr)
            if len(word) >= min_length:
                tokens.append(word)

        return tokens

    @classmethod
    def build_profile(
        cls,
        document_text: str,
        title: str = "Candidate Profile",
        custom_metadata: Dict[str, Any] | None = None,
    ) -> CompetencyProfile:
        """Constructs a normalized competency profile from raw CV or portfolio text."""
        raw_tokens = cls.tokenize_clean(document_text)
        freqs = Counter(raw_tokens)
        unique_tokens = set(freqs.keys())

        return CompetencyProfile(
            source_title=title,
            tokens=unique_tokens,
            term_frequencies=dict(freqs),
            metadata=custom_metadata or {},
        )

    @classmethod
    def evaluate_fit(
        cls,
        candidate_profile: CompetencyProfile,
        target_job_text: str,
        threshold_immediate: float = 0.75,
        threshold_potential: float = 0.50,
        threshold_bridging: float = 0.30,
    ) -> CareerGapAnalysis:
        """
        Calculates exact competency overlap, Jaccard distance, and actionable gap vectors.
        """
        jd_tokens = set(cls.tokenize_clean(target_job_text))
        if not jd_tokens:
            return CareerGapAnalysis(
                match_score=0.0,
                jaccard_similarity=0.0,
                readiness_tier=ReadinessTier.STRATEGIC_PIVOT,
                matched_competencies=[],
                missing_competencies=[],
                growth_recommendations=["Job description text yielded no extractable competency tokens."],
                total_requirements=0,
            )

        cand_tokens = candidate_profile.tokens

        # Set algebra: Intersection and Difference
        intersection = cand_tokens & jd_tokens
        union = cand_tokens | jd_tokens
        missing = jd_tokens - cand_tokens

        overlap_ratio = len(intersection) / float(len(jd_tokens))
        jaccard = len(intersection) / float(len(union)) if union else 0.0

        # Determine mathematical readiness tier
        if overlap_ratio >= threshold_immediate:
            tier = ReadinessTier.IMMEDIATE_FIT
        elif overlap_ratio >= threshold_potential:
            tier = ReadinessTier.HIGH_POTENTIAL
        elif overlap_ratio >= threshold_bridging:
            tier = ReadinessTier.SKILL_BRIDGING_REQUIRED
        else:
            tier = ReadinessTier.STRATEGIC_PIVOT

        # Rank missing competencies by significance in the job text
        jd_freqs = Counter(cls.tokenize_clean(target_job_text))
        sorted_missing = sorted(list(missing), key=lambda t: jd_freqs.get(t, 0), reverse=True)
        sorted_matched = sorted(list(intersection), key=lambda t: jd_freqs.get(t, 0), reverse=True)

        # Generate targeted growth actions dynamically derived from missing competencies
        growth_actions = [
            f"Bridge competency domain: '{term}' (Prominence rank: {idx + 1})"
            for idx, term in enumerate(sorted_missing[:5])
        ]

        return CareerGapAnalysis(
            match_score=round(overlap_ratio, 4),
            jaccard_similarity=round(jaccard, 4),
            readiness_tier=tier,
            matched_competencies=sorted_matched,
            missing_competencies=sorted_missing,
            growth_recommendations=growth_actions,
            total_requirements=len(jd_tokens),
        )

    @classmethod
    def calculate_cosine_similarity(
        cls,
        profile_a: CompetencyProfile,
        profile_b: CompetencyProfile,
    ) -> float:
        """
        Computes cosine similarity between two competency frequency distributions.
        """
        terms = set(profile_a.term_frequencies.keys()) | set(profile_b.term_frequencies.keys())
        if not terms:
            return 0.0

        dot_product = 0.0
        norm_a = 0.0
        norm_b = 0.0

        for t in terms:
            v_a = float(profile_a.term_frequencies.get(t, 0))
            v_b = float(profile_b.term_frequencies.get(t, 0))
            dot_product += v_a * v_b
            norm_a += v_a * v_a
            norm_b += v_b * v_b

        if norm_a <= 0.0 or norm_b <= 0.0:
            return 0.0

        return round(dot_product / (math.sqrt(norm_a) * math.sqrt(norm_b)), 4)


# Engine singleton
career_intelligence = CareerIntelligenceEngine()
