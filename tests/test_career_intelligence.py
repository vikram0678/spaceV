"""
Unit tests for core/career_intelligence.py: Career Intelligence & Gap Analysis.
"""

from __future__ import annotations

from core.career_intelligence import (
    CareerIntelligenceEngine,
    CompetencyProfile,
    ReadinessTier,
)


def test_tokenize_clean_preserves_special_technical_symbols():
    text = "Building distributed microservices in C++ and C# with Docker & Kubernetes!"
    tokens = CareerIntelligenceEngine.tokenize_clean(text)

    assert "c++" in tokens
    assert "c#" in tokens
    assert "docker" in tokens
    assert "kubernetes" in tokens
    assert "microservices" in tokens


def test_career_fit_immediate_match():
    cv_text = (
        "Senior Distributed Systems Engineer with expertise in Python, Rust, "
        "PostgreSQL, Redis, Kafka, and Linux kernel microVM architectures."
    )
    jd_text = (
        "Looking for a Senior Engineer with Python, Rust, PostgreSQL, and Linux experience."
    )

    profile = CareerIntelligenceEngine.build_profile(cv_text, title="Senior Profile")
    analysis = CareerIntelligenceEngine.evaluate_fit(profile, jd_text)

    # All JD core requirements are covered in the CV
    assert analysis.match_score >= 0.70
    assert analysis.readiness_tier in (ReadinessTier.IMMEDIATE_FIT, ReadinessTier.HIGH_POTENTIAL)
    assert "python" in analysis.matched_competencies
    assert "rust" in analysis.matched_competencies


def test_career_fit_skill_gap_derivation():
    cv_text = "Frontend Developer skilled in JavaScript, React, CSS, and HTML."
    jd_text = "Backend Go Engineer requiring Go, Kubernetes, gRPC, and Docker."

    profile = CareerIntelligenceEngine.build_profile(cv_text, title="Frontend Dev")
    analysis = CareerIntelligenceEngine.evaluate_fit(profile, jd_text)

    assert analysis.match_score < 0.50
    assert analysis.readiness_tier in (ReadinessTier.SKILL_BRIDGING_REQUIRED, ReadinessTier.STRATEGIC_PIVOT)
    # Missing competencies should be identified cleanly
    assert "go" in analysis.missing_competencies
    assert "kubernetes" in analysis.missing_competencies
    assert len(analysis.growth_recommendations) > 0


def test_cosine_similarity_calculation():
    prof_a = CompetencyProfile(
        source_title="Profile A",
        term_frequencies={"python": 5, "docker": 3, "fastapi": 2},
    )
    prof_b = CompetencyProfile(
        source_title="Profile B",
        term_frequencies={"python": 4, "docker": 3, "fastapi": 1},
    )
    prof_c = CompetencyProfile(
        source_title="Profile C",
        term_frequencies={"java": 5, "spring": 3},
    )

    sim_ab = CareerIntelligenceEngine.calculate_cosine_similarity(prof_a, prof_b)
    sim_ac = CareerIntelligenceEngine.calculate_cosine_similarity(prof_a, prof_c)

    # Identical domain profiles should have very high similarity
    assert sim_ab > 0.90
    # Disjoint profiles should have 0.0 similarity
    assert sim_ac == 0.0
