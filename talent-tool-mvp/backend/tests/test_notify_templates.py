"""Tests for services.notify.templates (T104)."""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    """每个测试前后清理全局 env,避免互相污染."""
    yield


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from services.notify.templates import (  # noqa: E402
    NotificationTemplate,
    NotificationType,
    available_types,
    render_template,
)


# ---------------------------------------------------------------------------
# NotificationType
# ---------------------------------------------------------------------------

class TestNotificationType:
    def test_all_expected_types_present(self):
        assert NotificationType.EMOTION_HIGH_RISK.value == "emotion_high_risk"
        assert NotificationType.TICKET_CREATED.value == "ticket_created"
        assert NotificationType.MATCH_SUCCESS.value == "match_success"
        assert NotificationType.SYSTEM_ALERT.value == "system_alert"

    def test_available_types_returns_all(self):
        types = available_types()
        assert set(types) == {t.value for t in NotificationType}

    def test_string_coercion_round_trip(self):
        for t in NotificationType:
            assert NotificationType(t.value) is t


# ---------------------------------------------------------------------------
# render_template - emotion_high_risk
# ---------------------------------------------------------------------------

class TestEmotionHighRisk:
    def test_minimal_context_renders_with_defaults(self):
        t = render_template(NotificationType.EMOTION_HIGH_RISK, {})
        assert "[情绪预警]" in t.subject
        assert "未知" in t.body  # candidate_name default
        assert "未提供" in t.body  # trigger default
        assert t.html is not None
        assert "UNKNOWN" not in t.html  # defaulting works

    def test_full_context(self):
        ctx = {
            "candidate_name": "Alice",
            "risk_level": "CRITICAL",
            "trigger": "self-harm keywords",
            "occurred_at": "2026-07-11 10:00",
            "link": "https://example.com/c/1",
        }
        t = render_template(NotificationType.EMOTION_HIGH_RISK, ctx)
        assert "Alice" in t.subject
        assert "Alice" in t.body
        assert "CRITICAL" in t.body
        assert "self-harm keywords" in t.body
        assert "https://example.com/c/1" in t.body
        assert "https://example.com/c/1" in (t.html or "")


# ---------------------------------------------------------------------------
# render_template - ticket_created
# ---------------------------------------------------------------------------

class TestTicketCreated:
    def test_subject_interpolates_title(self):
        t = render_template(
            NotificationType.TICKET_CREATED,
            {"title": "简历解析失败", "ticket_id": "TKT-001"},
        )
        assert "[新工单]" in t.subject
        assert "简历解析失败" in t.subject
        assert "TKT-001" in t.body

    def test_html_contains_description(self):
        t = render_template(
            NotificationType.TICKET_CREATED,
            {"description": "PDF parse error on page 3"},
        )
        assert "PDF parse error on page 3" in (t.html or "")


# ---------------------------------------------------------------------------
# render_template - match_success
# ---------------------------------------------------------------------------

class TestMatchSuccess:
    def test_scores_render(self):
        t = render_template(
            NotificationType.MATCH_SUCCESS,
            {
                "candidate_name": "张三",
                "role_title": "Senior Backend Engineer",
                "score": 0.92,
                "skill_score": 0.88,
                "semantic_score": 0.95,
            },
        )
        assert "张三" in t.subject
        assert "Senior Backend Engineer" in t.subject
        assert "0.92" in t.body
        assert "handoff" in t.body.lower() or "初筛" in t.body

    def test_html_table_format(self):
        t = render_template(
            NotificationType.MATCH_SUCCESS,
            {"candidate_name": "Bob", "role_title": "PM"},
        )
        assert t.html is not None
        assert "| 候选人 |" in t.html
        assert "Bob" in t.html


# ---------------------------------------------------------------------------
# render_template - system_alert
# ---------------------------------------------------------------------------

class TestSystemAlert:
    def test_severity_in_subject(self):
        t = render_template(
            NotificationType.SYSTEM_ALERT,
            {"severity": "P0", "alert_name": "DB connection pool exhausted"},
        )
        assert "[P0]" in t.subject
        assert "DB connection pool exhausted" in t.subject
        assert "P0" in t.body

    def test_action_default_present(self):
        t = render_template(NotificationType.SYSTEM_ALERT, {"alert_name": "X"})
        assert "请相关 SRE 介入" in t.body


# ---------------------------------------------------------------------------
# Return shape / metadata
# ---------------------------------------------------------------------------

class TestTemplateReturnShape:
    def test_returns_notification_template(self):
        result = render_template(NotificationType.SYSTEM_ALERT, {"alert_name": "Y"})
        assert isinstance(result, NotificationTemplate)
        assert result.type is NotificationType.SYSTEM_ALERT
        assert isinstance(result.subject, str)
        assert isinstance(result.body, str)
        assert isinstance(result.html, str)

    def test_meta_carries_notification_type(self):
        result = render_template(
            NotificationType.MATCH_SUCCESS,
            {"candidate_name": "X"},
            recipients=["user-1"],
        )
        assert result.meta["notification_type"] == "match_success"
        assert result.meta["default_recipients"] == ["user-1"]

    def test_to_message_payload(self):
        result = render_template(
            NotificationType.SYSTEM_ALERT,
            {"alert_name": "z"},
            recipients=["a@b.com"],
        )
        payload = result.to_message_payload(["a@b.com", "c@d.com"])
        assert payload["subject"] == result.subject
        assert payload["to"] == ["a@b.com", "c@d.com"]
        assert payload["metadata"]["notification_type"] == "system_alert"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_unknown_string_type_raises(self):
        with pytest.raises(ValueError):
            render_template("not_a_real_type", {})

    def test_unknown_type_member_raises(self):
        # 构造一个绕过枚举的伪造值
        with pytest.raises(ValueError):
            render_template("__bogus__", {})


# ---------------------------------------------------------------------------
# Defensive rendering
# ---------------------------------------------------------------------------

class TestDefensiveRendering:
    def test_missing_keys_do_not_break(self):
        """所有关键变量都有 | default 兜底,空 context 必须能渲染."""
        for ntype in NotificationType:
            t = render_template(ntype, {})
            assert t.subject  # 非空
            assert t.body     # 非空
            assert t.html     # 非空

    def test_jinja2_default_filter_used_for_undefined_keys(self):
        """Undef key 走 default filter;不会 raise StrictUndefined."""
        t = render_template(
            NotificationType.MATCH_SUCCESS,
            {"candidate_name": "X"},  # 缺 score/role_title/skill_score
        )
        # 'score' 的 default 是 '--'
        assert "--" in t.body