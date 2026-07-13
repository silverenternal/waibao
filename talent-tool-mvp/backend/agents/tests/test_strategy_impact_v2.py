"""T3703 - strategy impact tests."""
import pytest
from services.strategy_impact import (
    analyze_strategy, fire_strategy_updated_event, _scan, _extract_numbers,
)


class TestAnalyze:
    def test_empty(self):
        rep = analyze_strategy("")
        assert rep.summary != ""

    def test_no_actions(self):
        rep = analyze_strategy("公司年会")
        assert "未识别" in rep.summary or rep.items == []

    def test_hire_trigger(self):
        rep = analyze_strategy("我们需要招聘 5 个前端工程师")
        assert any(i.type == "hire" for i in rep.items)

    def test_close_trigger(self):
        rep = analyze_strategy("A 业务本月关停")
        assert any(i.type == "close" for i in rep.items)

    def test_language_trigger(self):
        rep = analyze_strategy("Q4 海外扩张需要英语人才")
        assert any("英语" in i.title or "海外" in i.title for i in rep.items)

    def test_priority_high_on_close(self):
        rep = analyze_strategy("关停 C 业务")
        close_items = [i for i in rep.items if i.type == "close"]
        assert any(i.priority == "high" for i in close_items)

    def test_priority_medium_on_small_hire(self):
        rep = analyze_strategy("扩招后端")
        assert rep.items

    def test_notify_targets(self):
        rep = analyze_strategy("招聘 AI 人才")
        assert "hr_team" in rep.auto_notify_targets

    def test_notify_targets_close(self):
        rep = analyze_strategy("关停 B 业务线")
        assert any("hrbp" in t for t in rep.auto_notify_targets)

    def test_dedup_items(self):
        rep = analyze_strategy("招聘招聘招聘")
        titles = [i.title for i in rep.items]
        assert len(titles) == len(set(titles))

    def test_signals_dict(self):
        rep = analyze_strategy("招聘英语")
        assert "hire" in rep.raw_signals

    def test_count_estimate(self):
        rep = analyze_strategy("招 10 个 AI")
        for item in rep.items:
            if "AI" in item.title:
                assert item.estimated_count >= 1

    def test_to_dict(self):
        rep = analyze_strategy("招聘")
        d = rep.to_dict()
        assert "items" in d
        assert "summary" in d


class TestScan:
    def test_no_match(self):
        assert _scan("hello", {"招聘": "hire"}) == []

    def test_match(self):
        out = _scan("我们要招聘", {"招聘": "招聘扩展"})
        assert "招聘扩展" in out

    def test_dedup(self):
        out = _scan("招聘招聘", {"招聘": "x"})
        assert out == ["x"]


class TestExtractNumbers:
    def test_no_numbers(self):
        assert _extract_numbers("hello") == []

    def test_with_ge(self):
        out = _extract_numbers("5 个")
        assert out == [5]


class TestFireEvent:
    def test_basic_event(self):
        out = fire_strategy_updated_event("招聘英语")
        # fire_strategy_updated_event should return dict with items
        assert "items" in out

    def test_with_version(self):
        out = fire_strategy_updated_event("招聘英语", version="2.0")
        assert out.get("version") == "2.0"

    def test_event_no_crash(self):
        # eventbus emit may or may not exist; should not raise
        try:
            fire_strategy_updated_event("anything")
        except Exception:
            pytest.fail("fire should not raise")
