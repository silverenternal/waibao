"""T3705 - JD marketing tests."""
import pytest
from services.jd_marketing import (
    generate_seo, story_mode, culture_blurb, team_vibe, score_jd,
    ab_variant_title, marketing_package,
)


class TestSeo:
    def test_basic(self):
        s = generate_seo("前端", "前端工程师, React/TypeScript", "北京")
        assert s.title
        assert s.description
        assert isinstance(s.keywords, list)

    def test_keywords_unique(self):
        s = generate_seo("前端 前端 前端", "前端工程师 React")
        assert len(s.keywords) == len(set(s.keywords))

    def test_description_truncated(self):
        s = generate_seo("前端", "x" * 200)
        assert len(s.description) <= 200


class TestStoryMode:
    def test_basic(self):
        out = story_mode("前端", "下一代产品", "真正的改变")
        assert "前端" in out

    def test_includes_vision(self):
        out = story_mode("X", "AI", "Y")
        assert "AI" in out

    def test_includes_impact(self):
        out = story_mode("X", "Y", "智能助手")
        assert "智能助手" in out


class TestCultureBlurb:
    def test_empty(self):
        out = culture_blurb([])
        assert "开放" in out or "透明" in out

    def test_with_keywords(self):
        out = culture_blurb(["开放", "协作"])
        assert "开放" in out
        assert "协作" in out


class TestTeamVibe:
    def test_size(self):
        out = team_vibe(10, ["脑暴"])
        assert "10" in out

    def test_keywords(self):
        out = team_vibe(5, ["脑暴", "午餐"])
        assert "脑暴" in out


class TestScoreJD:
    def test_minimum_payload(self):
        s = score_jd({"title": "前端"})
        assert s.completeness < 50

    def test_full_payload(self):
        s = score_jd({
            "title": "前端",
            "description": "我们正在改变行业,加入我们一起成长",
            "responsibilities": "...",
            "requirements": "...",
            "salary_range": "20-40k",
            "location": "B",
            "team_size": "10",
            "culture_keywords": ["开放"],
        })
        assert s.completeness >= 80
        assert s.attractiveness >= 50

    def test_fairness_penalty(self):
        s = score_jd({"description": "招聘 35岁以下男生"})
        assert s.fairness < 100

    def test_marketing_boost(self):
        clean = score_jd({"description": "looking for engineer"})
        story = score_jd({"description": "我们正在构建改变行业的产品"})
        assert story.marketing > clean.marketing

    def test_total_in_range(self):
        s = score_jd({"title": "X"})
        assert 0 <= s.total <= 100


class TestABVariants:
    def test_count(self):
        out = ab_variant_title("前端")
        assert len(out) == 2
        assert {v["variant"] for v in out} == {"A", "B"}

    def test_includes_role(self):
        out = ab_variant_title("数据科学家")
        for v in out:
            assert "数据科学家" in v["title"]


class TestMarketingPackage:
    def test_basic(self):
        meta = marketing_package({"title": "前端"})
        d = meta.to_dict()
        assert d["seo"]["title"]
        assert d["scores"]["total"] >= 0
        assert isinstance(d["ab_variants"], list)

    def test_full_payload(self):
        meta = marketing_package({
            "title": "前端",
            "description": "我们正在构建改变行业的产品",
            "vision": "AI",
            "candidate_impact": "真正的改变",
            "culture_keywords": ["开放", "协作"],
            "team_size": 10,
        })
        d = meta.to_dict()
        assert "story_mode" in d
        assert "team_vibe" in d
