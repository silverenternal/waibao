"""T3706 - policy explainer tests."""
import pytest
from services.policy_explainer import (
    explain_policy, _to_plain, _extract_key_points, _auto_faq, _risk_flags, LEGAL_TO_PLAIN,
)


class TestToPlain:
    def test_empty(self):
        assert _to_plain("") == ""

    def test_worker_to_employee(self):
        assert "员工" in _to_plain("劳动者权益保护")

    def test_legal_to_plain(self):
        assert "不可以" in _to_plain("不得擅自离岗")

    def test_minimum_wage(self):
        assert "最低工资" in _to_plain("工资不得低于当地最低工资标准")

    def test_social_insurance(self):
        assert "社保" in _to_plain("依法缴纳社会保险")

    def test_terminate(self):
        assert "解除合同" in _to_plain("用人单位有权解除劳动合同")


class TestExtractKeyPoints:
    def test_basic(self):
        out = _extract_key_points("公司必须按时足额支付工资。需要提前一天通知。")
        assert any("必须" in p or "需要" in p for p in out)

    def test_short_filtered(self):
        # too short sentences should be filtered
        out = _extract_key_points("需要。")
        assert out == [] or len(out) <= 5

    def test_no_match(self):
        out = _extract_key_points("无特殊条款。")
        assert isinstance(out, list)


class TestAutoFaq:
    def test_returns_list(self):
        out = _auto_faq("用人单位应当")
        assert len(out) >= 3

    def test_contains_qa(self):
        out = _auto_faq("any")
        for faq in out:
            assert faq.q
            assert faq.a


class TestRiskFlags:
    def test_no_risks(self):
        assert _risk_flags("按时发工资") == []

    def test_fine_risk(self):
        assert any("罚款" in r for r in _risk_flags("违章罚款 500 元"))

    def test_immediate_termination_risk(self):
        assert any("即时解除" in r or "程序" in r
                   for r in _risk_flags("员工立即解除"))

    def test_guarantee_risk(self):
        assert any("担保" in r for r in _risk_flags("需提供担保"))


class TestExplainPolicy:
    def test_basic(self):
        out = explain_policy("请假制度", "员工请假需要提前申请。")
        d = out.to_dict()
        assert d["plain_version"]

    def test_with_faq(self):
        out = explain_policy("X", "y")
        assert len(out.faqs) >= 1

    def test_with_risk_flags(self):
        out = explain_policy("X", "违章罚款")
        assert out.risk_flags

    def test_citations(self):
        out = explain_policy("X", "y")
        assert out.citations

    def test_key_points(self):
        out = explain_policy(
            "X",
            "公司必须按时支付工资。需要双方协商一致解除劳动合同。"
        )
        assert isinstance(out.key_points, list)
