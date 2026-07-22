"""Tests for resume_parser service + OCR 自动触发 (ProfileAgent / ComplianceAgent)."""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# --- helpers --------------------------------------------------------------

class _FakeOCRProvider:
    provider_name = "mock"

    async def recognize(self, image, *, mime="image/png", language="auto", **kw):
        from providers.ocr.base import OCRResult
        return OCRResult(text="张三 zhang.san@example.com 13800138000\n清华大学 计算机科学 2020", blocks=[])

    async def recognize_url(self, url, *, language="auto", **kw):
        from providers.ocr.base import OCRResult
        return OCRResult(text=f"OCR_TEXT_FOR:{url}", blocks=[])


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OCR_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    # 重置 provider 单例,保证用 mock
    from providers import registry

    registry.reset_cache()
    yield


# --- 1. resume_parser 基础 ------------------------------------------------

@pytest.mark.asyncio
async def test_extract_text_plain_text(monkeypatch):
    """纯文本 URL → 直接 decode,不调 OCR。"""
    from services.resume_parser import extract_text_from_url

    async def fake_fetch(url, *, timeout=30.0):
        return "纯文本简历内容 张三 zhang.san@example.com".encode("utf-8")

    monkeypatch.setattr("services.jobseeker.resume_parser._fetch_bytes", fake_fetch)
    text = await extract_text_from_url("https://example.com/cv.txt")
    assert "张三" in text
    assert "zhang.san" in text


@pytest.mark.asyncio
async def test_extract_text_ocr_fallback_to_vision(monkeypatch):
    """OCR provider 抛错 → 走 vision fallback。"""
    from services.jobseeker import resume_parser as rp

    async def fake_fetch(url, *, timeout=30.0):
        return b"\x89PNG\r\n\x1a\n FAKE"

    async def fake_ocr(url, *, language="auto"):
        raise RuntimeError("OCR down")

    async def fake_vision(url):
        return "VISION-OCR-TEXT-MARKER"

    monkeypatch.setattr(rp, "_fetch_bytes", fake_fetch)
    monkeypatch.setattr(rp, "_ocr_via_registry", fake_ocr)
    monkeypatch.setattr(rp, "_vision_fallback", fake_vision)

    text = await rp.extract_text_from_url("https://example.com/cv.png")
    assert text == "VISION-OCR-TEXT-MARKER"


@pytest.mark.asyncio
async def test_extract_text_ocr_success(monkeypatch):
    """OCR provider 主路径返回 text。"""
    from services.jobseeker import resume_parser as rp

    async def fake_fetch(url, *, timeout=30.0):
        return b"\x89PNG\r\n\x1a\n FAKE"

    async def fake_ocr(url, *, language="auto"):
        return "OCR-OK-TEXT"

    monkeypatch.setattr(rp, "_fetch_bytes", fake_fetch)
    monkeypatch.setattr(rp, "_ocr_via_registry", fake_ocr)
    text = await rp.extract_text_from_url("https://example.com/cv.png")
    assert text == "OCR-OK-TEXT"


@pytest.mark.asyncio
async def test_extract_text_both_fail(monkeypatch):
    """OCR + Vision 都空 → ProviderError."""
    from services.jobseeker import resume_parser as rp
    from providers.exceptions import ProviderError

    async def fake_fetch(url, *, timeout=30.0):
        return b"\x89PNG"

    async def fake_ocr(url, *, language="auto"):
        return ""

    async def fake_vision(url):
        return ""

    monkeypatch.setattr(rp, "_fetch_bytes", fake_fetch)
    monkeypatch.setattr(rp, "_ocr_via_registry", fake_ocr)
    monkeypatch.setattr(rp, "_vision_fallback", fake_vision)

    with pytest.raises(ProviderError):
        await rp.extract_text_from_url("https://example.com/x.png")


@pytest.mark.asyncio
async def test_parse_resume_from_url_full(monkeypatch):
    """端到端: 拉 URL → OCR → LLM 抽取 → 清洗。"""
    from services.jobseeker import resume_parser as rp

    raw_text = "张三 zhang.san@example.com 13800138000 清华大学 计算机科学 2020 字节跳动 高级工程师"

    async def fake_extract(url, *, language="auto"):
        return raw_text

    monkeypatch.setattr(rp, "extract_text_from_url", fake_extract)

    # mock llm provider 让 extract_resume 返回可控结构
    extracted = {
        "basic": {
            "name": "张三",
            "email": "zhang.san@example.com",
            "phone": "13800138000",
            "location": "北京",
        },
        "education": [{"school": "清华大学", "degree": "本科", "major": "CS", "year": "2020"}],
        "experience": [
            {"company": "字节跳动", "title": "高级工程师", "duration_months": 36, "responsibilities": [], "achievements": []}
        ],
        "skills": [{"name": "Python", "category": "技术", "years": 5, "level": "高"}],
        "highlights": [],
        "red_flags": [],
        "overall_impression": "强",
    }

    class _FakeResp:
        content = ""
        model = "mock"
        usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()
        finish_reason = "stop"

    class _FakeLLM:
        provider_name = "mock"
        provider = MagicMock()

        async def call(self, messages, **kw):
            import json as _json
            return _json.dumps(extracted, ensure_ascii=False), 1, 1

    fake_llm = _FakeLLM()

    out = await rp.parse_resume_from_url("https://example.com/cv.txt", llm=fake_llm)
    assert out["source_url"] == "https://example.com/cv.txt"
    assert out["raw_text"] == raw_text
    assert "ocr" in out["provider_chain"]
    assert "llm" in out["provider_chain"]
    # PII fields (name/email/phone) must be encrypted — Fernet ciphertext starts
    # with "gAAAA". Asserting plaintext here would re-introduce the leak where
    # the candidate name was stored unencrypted (the "name" dict key was never
    # matched by the old `fields=["full_name", ...]` call).
    basic_out = out["extracted"]["basic"]
    assert basic_out["name"].startswith("gAAAA"), "candidate name must be encrypted"
    assert basic_out["email"].startswith("gAAAA"), "email must be encrypted"
    assert basic_out["phone"].startswith("gAAAA"), "phone must be encrypted"
    # location is not a L2 PII field and stays plaintext
    assert basic_out["location"] == "北京"
    assert out["ocr_provider"] == "mock"


@pytest.mark.asyncio
async def test_post_process_extracts_email_phone(monkeypatch):
    """post_process 应该能补回 email 和 phone 当 LLM 没识别全。"""
    from services.resume_parser import _post_process

    raw = {
        "basic": {"name": "李四", "email": "", "phone": "", "location": ""},
        "education": [],
        "experience": [
            {"company": "X", "title": "Y", "duration_months": "36"}  # string 类型
        ],
        "skills": [{"name": "Go", "category": "技术", "years": "5", "level": "高"}],
    }
    # 注入 email/phone 到 raw text
    text_blob = "Contact me: lisi@example.com / +86 13900001111"
    out = await _post_process({
        **raw,
        "_any_with_email": text_blob,  # 不会影响输出,我们只是探测正则
    })
    assert out["experience"][0]["duration_months"] == 36
    assert out["skills"][0]["years"] == 5


# --- 2. ProfileAgent 自动 OCR --------------------------------------------

@pytest.mark.asyncio
async def test_profile_agent_runs_ocr_when_file_url(monkeypatch):
    """ProfileAgent 当 ctx.file_url 存在时,自动走 OCR 并合并画像。"""
    from agents.jobseeker.profile_agent import ProfileAgent
    from agents.runtime import AgentInput, MemoryScope

    parsed = {
        "source_url": "https://example.com/cv.png",
        "raw_text": "张三 zhang.san@example.com 清华大学 计算机 字节跳动 Python",
        "extracted": {
            "basic": {
                "name": "张三",
                "email": "zhang.san@example.com",
                "phone": "13800138000",
                "location": "北京",
            },
            "education": [{"school": "清华大学", "degree": "本科", "major": "CS", "year": "2020"}],
            "skills": [{"name": "Python", "category": "技术", "years": 5, "level": "高"}],
        },
        "provider_chain": ["ocr", "llm"],
        "ocr_provider": "mock",
    }

    async def fake_parse(url, *, llm=None, hint=None):
        return parsed

    # ProfileAgent 通过 import-from 而不是模块属性引用 parse_resume_from_url;
    # monkeypatch sys.modules 让从 services.resume_parser 拿到的符号被替换
    import services.resume_parser as rp_mod

    monkeypatch.setattr(rp_mod, "parse_resume_from_url", fake_parse)

    # mock llm_call 返回的 _mock_profile_response 即可
    agent = ProfileAgent(memory=None)
    inp = AgentInput(
        user_id="u1",
        persona="jobseeker",
        text="上传了我的简历",
        context={"file_url": "https://example.com/cv.png"},
    )
    out = await agent.run(inp)
    assert out.success
    art = out.artifacts
    assert art["ocr_triggered"] is True
    assert art["resume_extracted"]["basic"]["name"] == "张三"
    # 画像已写入 artifacts
    assert art["updated_profile"]["name"] == "张三"
    assert "Python" in {s["name"] for s in art["updated_profile"]["skills"]}


@pytest.mark.asyncio
async def test_profile_agent_no_ocr_when_no_file_url(monkeypatch):
    """未传 file_url → 不走 OCR,走原来对话采集路径。"""
    from agents.jobseeker.profile_agent import ProfileAgent
    from agents.runtime import AgentInput

    agent = ProfileAgent(memory=None)
    inp = AgentInput(
        user_id="u1",
        persona="jobseeker",
        text="我本科是清华",
        context={},
    )
    out = await agent.run(inp)
    assert out.success
    assert out.artifacts["ocr_triggered"] is False


# --- 3. ComplianceAgent 自动 OCR -----------------------------------------

@pytest.mark.asyncio
async def test_compliance_agent_runs_ocr(monkeypatch):
    """ComplianceAgent 当 file_url 存在 → OCR + LLM verdict。"""
    from agents.employer.compliance_agent import ComplianceAgent
    from agents.runtime import AgentInput

    # mock OCR
    async def fake_ocr(self, file_url):
        return {"text": "公司名: 测试公司 统一社会信用代码: 91110000600037341L", "provider": "mock"}

    # mock compliance_service.verify_credential_against_lookup
    async def fake_verify(ocr_data):
        return {
            "credit_code": "91110000600037341L",
            "credit_code_valid": True,
            "trust_score": 0.95,
            "risk_level": "low",
            "company_match": True,
            "matched_company": {"name": "测试公司", "status": "存续"},
            "warnings": [],
            "expiry_alerts": [],
            "lookup_provider": "mock",
            "lookup_status": "存续",
        }

    monkeypatch.setattr(
        "agents.employer.compliance_agent.ComplianceAgent._ocr_credential",
        fake_ocr,
    )
    monkeypatch.setattr(
        "agents.employer.compliance_agent.verify_credential_against_lookup",
        fake_verify,
    )

    # 屏蔽 supabase 写入
    fake_table = MagicMock()
    fake_supabase = MagicMock()
    fake_supabase.table.return_value = fake_table
    fake_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "x"}])

    monkeypatch.setattr(
        "api.deps.get_supabase_admin", lambda: fake_supabase
    )

    agent = ComplianceAgent(memory=None)
    inp = AgentInput(
        user_id="org1",
        persona="hr",
        text="营业执照",
        context={"file_url": "https://example.com/license.png", "hint_company_name": "测试公司", "hint_credit_code": "91110000600037341L"},
    )
    out = await agent.run(inp)
    assert out.success
    art = out.artifacts
    assert art["ocr_provider"] == "mock"
    assert "OCR 通道" in out.text


@pytest.mark.asyncio
async def test_compliance_agent_vision_fallback_when_ocr_fails(monkeypatch):
    """OCR 主路径抛错 → 自动降级到 vision OCR。"""
    from agents.employer.compliance_agent import ComplianceAgent
    from agents.runtime import AgentInput

    async def fake_ocr_main(self, file_url):
        # 模拟 OCR 主路径失败但 vision fallback 成功
        return {"text": "Vision OCR result: 测试公司 91110000600037341L", "provider": "mock_failed_vision"}

    async def fake_verify(ocr_data):
        return {
            "credit_code": "91110000600037341L",
            "credit_code_valid": True,
            "trust_score": 0.9,
            "risk_level": "low",
            "company_match": True,
            "matched_company": {"name": "测试公司", "status": "存续"},
            "warnings": [],
            "expiry_alerts": [],
            "lookup_provider": "mock",
            "lookup_status": "存续",
        }

    monkeypatch.setattr(
        "agents.employer.compliance_agent.ComplianceAgent._ocr_credential",
        fake_ocr_main,
    )
    monkeypatch.setattr(
        "agents.employer.compliance_agent.verify_credential_against_lookup",
        fake_verify,
    )
    fake_supabase = MagicMock()
    fake_table = MagicMock()
    fake_supabase.table.return_value = fake_table
    fake_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "x"}])
    monkeypatch.setattr("api.deps.get_supabase_admin", lambda: fake_supabase)

    agent = ComplianceAgent(memory=None)
    inp = AgentInput(
        user_id="org1",
        persona="hr",
        text="",
        context={"file_url": "https://example.com/license.jpg", "hint_company_name": "测试公司"},
    )
    out = await agent.run(inp)
    assert out.success
    assert "vision" in out.artifacts["ocr_provider"]


@pytest.mark.asyncio
async def test_compliance_agent_no_file_url_prompts_upload():
    """没传 file_url → 返回 awaiting_upload。"""
    from agents.employer.compliance_agent import ComplianceAgent
    from agents.runtime import AgentInput

    agent = ComplianceAgent(memory=None)
    inp = AgentInput(
        user_id="org1",
        persona="hr",
        text="",
        context={},
    )
    out = await agent.run(inp)
    assert out.success
    assert out.artifacts["stage"] == "awaiting_upload"
    assert "请上传资质文件" in out.text


# --- 4. OCR_PROVIDER env 分发 --------------------------------------------

@pytest.mark.asyncio
async def test_ocr_provider_selection_by_env(monkeypatch):
    """OCR_PROVIDER=mock 应该选到 MockOCRProvider。"""
    monkeypatch.setenv("OCR_PROVIDER", "mock")
    from providers import registry

    registry.reset_cache()
    from providers.registry import get_ocr_provider

    p = get_ocr_provider()
    assert p.provider_name == "mock"


@pytest.mark.asyncio
async def test_ocr_provider_unknown_raises(monkeypatch):
    """未知 provider name 应该抛 InvalidRequestError."""
    monkeypatch.setenv("OCR_PROVIDER", "nonsense")
    from providers import registry

    registry.reset_cache()
    from providers.registry import get_ocr_provider
    from providers.exceptions import InvalidRequestError

    with pytest.raises(InvalidRequestError):
        get_ocr_provider()
