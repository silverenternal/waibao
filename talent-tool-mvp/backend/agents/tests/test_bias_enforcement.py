"""T3704 - bias enforcement tests."""
import pytest
from services.bias_enforcement import (
    scan_bias, substitute, build_impact_report, BIAS_LEXICON,
)


class TestScanBias:
    def test_empty(self):
        rep = scan_bias("")
        assert rep.hits == []

    def test_age(self):
        rep = scan_bias("招聘 35岁以下 前端")
        cats = {h.category for h in rep.hits}
        assert "age" in cats

    def test_gender(self):
        rep = scan_bias("男生优先")
        assert any(h.category == "gender" for h in rep.hits)

    def test_appearance(self):
        rep = scan_bias("形象好")
        assert any(h.category == "appearance" for h in rep.hits)

    def test_region(self):
        rep = scan_bias("仅限本地人")
        assert any(h.category == "region" for h in rep.hits)

    def test_health(self):
        rep = scan_bias("无重大疾病")
        assert any(h.category == "health" for h in rep.hits)

    def test_score_decreases_with_hits(self):
        clean = scan_bias("招聘")
        dirty = scan_bias("招聘 35岁以下 男生")
        assert dirty.score < clean.score

    def test_cannot_submit_when_high_severity(self):
        rep = scan_bias("男生优先 35岁以下")
        assert rep.can_submit is False

    def test_can_submit_when_clean(self):
        rep = scan_bias("招聘前端工程师")
        assert rep.can_submit is True

    def test_recommendations_present(self):
        rep = scan_bias("形象好 35岁以下")
        assert rep.recommendations


class TestSubstitute:
    def test_empty(self):
        assert substitute("") == ""

    def test_basic(self):
        out = substitute("招聘 35岁以下")
        assert "35岁以下" not in out

    def test_replacement_dict(self):
        out = substitute("35岁以下", replacements={"age": "[改写]"})
        assert "[改写]" in out

    def test_keeps_clean_text(self):
        text = "前端工程师"
        assert substitute(text) == text


class TestBuildImpactReport:
    def test_empty(self):
        rep = build_impact_report([])
        # Empty list → 0 total
        assert rep["total_jds"] == 0
        assert rep["affected_jds"] == 0

    def test_count_affected(self):
        historic = [
            {"department": "A", "quarter": "Q1",
             "bias_report": {"hits": [{"category": "age"}]}},
            {"department": "B", "quarter": "Q1",
             "bias_report": {"hits": []}},
        ]
        rep = build_impact_report(historic)
        assert rep["affected_jds"] == 1

    def test_dept_breakdown(self):
        historic = [
            {"department": "A", "quarter": "Q1",
             "bias_report": {"hits": [{"category": "age"}]}},
            {"department": "A", "quarter": "Q2",
             "bias_report": {"hits": [{"category": "gender"}]}},
        ]
        rep = build_impact_report(historic)
        assert rep["department_breakdown"]["A"] == 2

    def test_quarter_breakdown(self):
        historic = [
            {"department": "A", "quarter": "Q1",
             "bias_report": {"hits": [{"category": "age"}]}},
        ]
        rep = build_impact_report(historic)
        assert rep["quarter_breakdown"]["Q1"] == 1

    def test_narrative_contains_keywords(self):
        historic = [{"department": "A", "quarter": "Q1",
                     "bias_report": {"hits": [{"category": "age"}]}}]
        rep = build_impact_report(historic)
        assert "偏见" in rep["narrative"]

    def test_recommendations(self):
        rep = build_impact_report([])
        assert "recommendations" in rep

    def test_default_months(self):
        rep = build_impact_report([], months=6)
        assert rep["affected_rate_pct"] == 0


class TestLexicon:
    def test_has_categories(self):
        assert "age" in BIAS_LEXICON
        assert "gender" in BIAS_LEXICON
        assert "appearance" in BIAS_LEXICON

    def test_each_has_label(self):
        for cat, info in BIAS_LEXICON.items():
            assert "label" in info
            assert "words" in info
            assert "replacement" in info

    def test_words_is_list(self):
        for info in BIAS_LEXICON.values():
            assert isinstance(info["words"], list)
            assert len(info["words"]) > 0
