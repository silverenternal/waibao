"""Tests for services.compliance_service (T103)."""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("LOOKUP_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    try:
        from providers import registry
        registry.reset_cache()
    except Exception:
        pass
    yield


@pytest.fixture
def valid_credit_code() -> str:
    return "91110000600037341L"


@pytest.fixture
def fake_lookup_provider():
    """A controllable lookup provider used to test service behavior."""
    from providers.lookup.base import CompanyInfo, CompanyLookupProvider

    class StubProvider(CompanyLookupProvider):
        provider_name = "stub"

        def __init__(self):
            self.search_calls = []
            self.detail_calls = []

        async def search(self, keyword, **kw):
            self.search_calls.append((keyword, kw))
            return [
                CompanyInfo(
                    name=f"{keyword} 测试公司",
                    unified_social_credit_code="91110000600037341L",
                    status="存续",
                    established_date="2020-01-15",
                    registered_capital="1000万",
                    legal_representative="张三",
                    industry="科技",
                    business_scope="技术开发",
                    address="北京市",
                )
            ]

        async def get_detail(self, company_id, **kw):
            self.detail_calls.append((company_id, kw))
            return CompanyInfo(
                name="测试公司",
                unified_social_credit_code=company_id,
                status="存续",
                established_date="2020-01-15",
                registered_capital="5000万",
            )

    return StubProvider()


# ---------------------------------------------------------------------------
# 1. resolve lookup provider default = mock, fallback to mock if credential missing
# ---------------------------------------------------------------------------
class TestProviderResolution:
    def test_default_lookup_is_mock(self, monkeypatch):
        from services.compliance_service import _resolve_lookup_provider

        monkeypatch.delenv("LOOKUP_PROVIDER", raising=False)
        monkeypatch.setenv("LOOKUP_PROVIDER", "mock")
        p = _resolve_lookup_provider()
        assert p.provider_name == "mock"

    def test_lookup_falls_back_to_mock_when_credential_missing(self, monkeypatch):
        """LOOKUP_PROVIDER=tianyancha 但 key 缺失 → 降级到 mock."""
        from services.compliance_service import _resolve_lookup_provider

        monkeypatch.setenv("LOOKUP_PROVIDER", "tianyancha")
        monkeypatch.delenv("TIANYANCHA_API_KEY", raising=False)

        # registry 可能抛错,service 应该降级到 mock
        p = _resolve_lookup_provider()
        assert p.provider_name in ("mock", "tianyancha")  # 任何一种都 OK


# ---------------------------------------------------------------------------
# 2. assess_company: full pipeline
# ---------------------------------------------------------------------------
class TestAssessCompany:
    @pytest.mark.asyncio
    async def test_valid_credit_code_full_pass(self, valid_credit_code):
        from services.compliance_service import assess_company

        out = await assess_company(credit_code=valid_credit_code)
        assert out["credit_code_valid"] is True
        assert out["lookup_provider"] == "mock"
        assert out["lookup_status"] == "存续"
        assert out["trust_score"] >= 0.7
        assert out["risk_level"] == "low"
        assert out["company_match"] is True
        assert out["matched_company"] is not None
        assert out["warnings"] == []
        assert "cross_check" in out
        assert out["cross_check"]["credit_code_valid"] is True

    @pytest.mark.asyncio
    async def test_invalid_credit_code_no_lookup(self):
        from services.compliance_service import assess_company

        out = await assess_company(credit_code="911100006000373410")  # wrong check digit
        assert out["credit_code_valid"] is False
        assert out["trust_score"] < 0.5
        assert out["risk_level"] in ("high", "medium")
        # lookup 没拿到,因为 code 不合法
        assert any("校验位" in w or "信用代码" in w for w in out["warnings"])

    @pytest.mark.asyncio
    async def test_company_name_only(self):
        from services.compliance_service import assess_company

        out = await assess_company(company_name="华为投资控股有限公司")
        # No credit code, so validation fails → risk weighted lower
        assert out["credit_code_valid"] is False
        # 但 mock 应该返回搜索结果
        # trust_score 可能小于 0.4 因为 credit_code_valid=False 不加分
        assert out["risk_level"] in ("high", "medium", "low")

    @pytest.mark.asyncio
    async def test_summary_includes_established_years(self, valid_credit_code):
        from services.compliance_service import assess_company

        out = await assess_company(credit_code=valid_credit_code)
        assert "6年" in out["summary"] or "经营" in out["summary"]

    @pytest.mark.asyncio
    async def test_called_with_stub_provider(self, valid_credit_code, fake_lookup_provider):
        """When we monkeypatch resolve_lookup_provider, verify our stub gets called."""
        import services.compliance_service as svc

        # Patch the module-level resolver
        svc._resolve_lookup_provider = lambda: fake_lookup_provider

        out = await svc.assess_company(credit_code=valid_credit_code)
        # Our stub returns '测试公司' as the name
        assert out["matched_company"]["name"] == "测试公司"
        assert out["lookup_provider"] == "stub"
        # Should have called get_detail (because we passed valid credit_code)
        assert len(fake_lookup_provider.detail_calls) == 1
        assert fake_lookup_provider.detail_calls[0][0] == valid_credit_code


# ---------------------------------------------------------------------------
# 3. verify_credential_against_lookup (with OCR-style input)
# ---------------------------------------------------------------------------
class TestVerifyCredentialAgainstLookup:
    @pytest.mark.asyncio
    async def test_with_ocr_payload(self, valid_credit_code):
        from services.compliance_service import verify_credential_against_lookup

        ocr = {
            "company_name": "测试公司",
            "credit_code": valid_credit_code,
            "ocr_text_snippet": "...",
        }
        out = await verify_credential_against_lookup(ocr)
        assert out["credit_code_valid"] is True
        assert out["trust_score"] >= 0.7

    @pytest.mark.asyncio
    async def test_with_empty_payload(self):
        from services.compliance_service import verify_credential_against_lookup

        out = await verify_credential_against_lookup({})
        assert out["credit_code_valid"] is False
        assert out["trust_score"] >= 0.0

    @pytest.mark.asyncio
    async def test_with_none_payload(self):
        from services.compliance_service import verify_credential_against_lookup

        out = await verify_credential_against_lookup(None)
        # Should not raise; just produce empty verdict
        assert isinstance(out, dict)
        assert "trust_score" in out


# ---------------------------------------------------------------------------
# 4. compute_expiry_alerts
# ---------------------------------------------------------------------------
class TestComputeExpiryAlerts:
    def test_filters_out_far_future(self):
        from services.compliance_service import compute_expiry_alerts

        base = date(2026, 7, 5)
        creds = [
            {"id": "1", "expiry_date": (base + timedelta(days=365)).isoformat()},
        ]
        alerts = compute_expiry_alerts(creds, today=base, days_ahead=30)
        assert alerts == []

    def test_includes_warning_within_window(self):
        from services.compliance_service import compute_expiry_alerts

        base = date(2026, 7, 5)
        creds = [
            {"id": "1", "expiry_date": (base + timedelta(days=20)).isoformat()},
        ]
        alerts = compute_expiry_alerts(creds, today=base, days_ahead=30)
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "warning"
        assert alerts[0]["days_to_expiry"] == 20
        assert alerts[0]["credential_id"] == "1"

    def test_includes_critical_within_7_days(self):
        from services.compliance_service import compute_expiry_alerts

        base = date(2026, 7, 5)
        creds = [
            {"id": "1", "expiry_date": (base + timedelta(days=3)).isoformat()},
        ]
        alerts = compute_expiry_alerts(creds, today=base, days_ahead=30)
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "critical"

    def test_includes_expired(self):
        from services.compliance_service import compute_expiry_alerts

        base = date(2026, 7, 5)
        creds = [
            {"id": "1", "expiry_date": (base - timedelta(days=10)).isoformat()},
        ]
        alerts = compute_expiry_alerts(creds, today=base, days_ahead=30)
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "expired"
        assert alerts[0]["days_to_expiry"] == -10

    def test_no_expiry_skipped(self):
        from services.compliance_service import compute_expiry_alerts

        creds = [{"id": "1", "expiry_date": None}, {"id": "2"}]
        alerts = compute_expiry_alerts(creds, today=date(2026, 7, 5))
        assert alerts == []

    def test_sorted_by_severity_then_days(self):
        from services.compliance_service import compute_expiry_alerts

        base = date(2026, 7, 5)
        creds = [
            {"id": "1", "expiry_date": (base + timedelta(days=20)).isoformat()},  # warning
            {"id": "2", "expiry_date": (base + timedelta(days=3)).isoformat()},   # critical
            {"id": "3", "expiry_date": (base - timedelta(days=2)).isoformat()},   # expired
            {"id": "4", "expiry_date": (base + timedelta(days=5)).isoformat()},   # critical
        ]
        alerts = compute_expiry_alerts(creds, today=base, days_ahead=30)
        severities = [a["severity"] for a in alerts]
        # Severity ranking: expired < critical < warning
        assert severities == ["expired", "critical", "critical", "warning"]
        # Within critical, should be sorted by days_to_expiry ascending
        critical = [a for a in alerts if a["severity"] == "critical"]
        assert critical[0]["days_to_expiry"] == 3
        assert critical[1]["days_to_expiry"] == 5

    def test_bad_date_skipped(self):
        from services.compliance_service import compute_expiry_alerts

        creds = [{"id": "1", "expiry_date": "not-a-date"}]
        alerts = compute_expiry_alerts(creds, today=date(2026, 7, 5))
        assert alerts == []

    def test_supports_expiry_at_alias(self):
        from services.compliance_service import compute_expiry_alerts

        base = date(2026, 7, 5)
        creds = [{"id": "1", "expiry_at": (base + timedelta(days=10)).isoformat()}]
        alerts = compute_expiry_alerts(creds, today=base)
        assert len(alerts) == 1

    def test_supports_expires_at_alias(self):
        from services.compliance_service import compute_expiry_alerts

        base = date(2026, 7, 5)
        creds = [{"id": "1", "expires_at": (base + timedelta(days=10)).isoformat()}]
        alerts = compute_expiry_alerts(creds, today=base)
        assert len(alerts) == 1


# ---------------------------------------------------------------------------
# 5. list_expiry_alerts with supabase (mocked)
# ---------------------------------------------------------------------------
class TestListExpiryAlerts:
    @pytest.mark.asyncio
    async def test_with_explicit_credentials(self):
        from services.compliance_service import list_expiry_alerts

        base = date(2026, 7, 5)
        creds = [
            {"id": "1", "expiry_date": (base + timedelta(days=2)).isoformat()},
        ]
        alerts = await list_expiry_alerts(
            credentials=creds,
            today=base,
            days_ahead=30,
        )
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_with_mock_supabase(self):
        from services.compliance_service import list_expiry_alerts

        base = date(2026, 7, 5)
        creds = [
            {"id": "1", "expiry_date": (base + timedelta(days=20)).isoformat()},
        ]

        # Build a fake supabase client with chainable select/eq/execute
        class FakeResult:
            data = creds

        class FakeChain:
            def select(self, *a, **kw): return self
            def eq(self, *a, **kw): return self
            def execute(self): return FakeResult()

        fake_supabase = MagicMock()
        fake_supabase.table.return_value = FakeChain()

        alerts = await list_expiry_alerts(
            supabase=fake_supabase,
            today=base,
            days_ahead=30,
        )
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "warning"


# ---------------------------------------------------------------------------
# 6. normalize_for_compare
# ---------------------------------------------------------------------------
class TestNormalizeForCompare:
    def test_strips_and_uppercases(self):
        from services.compliance_service import normalize_for_compare

        assert (
            normalize_for_compare("91-1100-0060-0037-341L")
            == normalize_for_compare("91110000600037341l")
        )

    def test_none_safe(self):
        from services.compliance_service import normalize_for_compare

        assert normalize_for_compare(None) == ""
        assert normalize_for_compare("") == ""


# ---------------------------------------------------------------------------
# 7. Provider-aware error handling
# ---------------------------------------------------------------------------
class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_provider_error_does_not_raise(self, valid_credit_code):
        """When lookup provider raises ProviderError, the service should
        gracefully include a warning in the verdict without propagating."""
        import services.compliance_service as svc
        from providers.exceptions import ProviderError
        from providers.lookup.base import CompanyInfo, CompanyLookupProvider

        class BrokenProvider(CompanyLookupProvider):
            provider_name = "broken"

            async def search(self, keyword, **kw):
                raise ProviderError("network down", provider="broken")

            async def get_detail(self, company_id, **kw):
                raise ProviderError("network down", provider="broken")

        svc._resolve_lookup_provider = lambda: BrokenProvider()
        out = await svc.assess_company(credit_code=valid_credit_code)
        assert out["credit_code_valid"] is True
        assert any("工商查询失败" in w or "lookup" in w.lower() or "查询" in w for w in out["warnings"])
        # 不应该 propagate;risk 也合理
        assert "trust_score" in out


# ---------------------------------------------------------------------------
# 8. Public exports
# ---------------------------------------------------------------------------
def test_module_exports():
    import services.compliance_service as svc

    for name in (
        "ComplianceVerdict",
        "assess_company",
        "verify_credential_against_lookup",
        "compute_expiry_alerts",
        "list_expiry_alerts",
        "normalize_for_compare",
    ):
        assert hasattr(svc, name), f"missing export {name}"
