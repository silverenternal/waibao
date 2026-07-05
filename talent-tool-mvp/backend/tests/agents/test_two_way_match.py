"""双向匹配单测 (T301)."""
import pytest

from matching.harmonic_score import harmonic_mean, geometric_mean, arithmetic_mean, weighted_score, confidence_adjusted
from matching.two_way import harmonic, _score_candidate_view, _score_employer_view


def test_harmonic_balanced():
    """调和均值: 双方接近时高分."""
    assert harmonic(0.9, 0.9) > 0.85
    assert harmonic(0.5, 0.5) == pytest.approx(0.5, abs=1e-3)


def test_harmonic_penalizes_weak_side():
    """调和均值惩罚弱侧."""
    assert harmonic(1.0, 0.0) < 0.05
    assert harmonic(0.8, 0.2) < 0.4


def test_geometric_mean():
    assert geometric_mean(0.9, 0.9) == pytest.approx(0.9, abs=1e-3)
    assert geometric_mean(0.0, 1.0) == 0.0


def test_arithmetic_mean():
    assert arithmetic_mean(0.6, 0.8) == 0.7


def test_weighted_score():
    parts = {"skill": 0.9, "experience": 0.5}
    weights = {"skill": 0.7, "experience": 0.3}
    expected = (0.9 * 0.7 + 0.5 * 0.3) / 1.0
    assert weighted_score(parts, weights) == pytest.approx(expected, abs=1e-6)


def test_confidence_adjusted():
    """低置信度应向 0.5 收缩."""
    assert confidence_adjusted(0.9, 1.0) == pytest.approx(0.9, abs=1e-6)
    assert confidence_adjusted(0.9, 0.0) == 0.5


def test_score_candidate_view():
    profile = {"skills": [{"name": "Python"}, {"name": "React"}]}
    role = {"required_skills": [{"name": "Python"}, {"name": "React"}]}
    score = _score_candidate_view(profile, {"must_haves": []}, role)
    assert 0.4 <= score <= 1.0


def test_score_employer_view():
    role = {"required_skills": [{"name": "Python"}, {"name": "React"}], "min_experience_years": 3}
    profile = {"skills": [{"name": "Python"}, {"name": "React"}], "experience_years": 5}
    score = _score_employer_view(role, {}, profile)
    assert score >= 0.7


@pytest.mark.asyncio
async def test_compute_two_way_integration(mock_llm):
    from matching.two_way import compute_two_way
    score = await compute_two_way(
        candidate_profile={"skills": [{"name": "Python"}]},
        role_profile={"required_skills": [{"name": "Python"}], "min_experience_years": 2},
        candidate_needs={"must_haves": []},
        role_needs={"implicit_requirements": []},
        llm=mock_llm,
    )
    assert 0 <= score.candidate_to_role <= 1
    assert 0 <= score.role_to_candidate <= 1
    assert 0 <= score.harmonic_score <= 1
    print(f"✓ two-way score: c2r={score.candidate_to_role:.2f}, r2c={score.role_to_candidate:.2f}, h={score.harmonic_score:.2f}")