"""百度 OCR 真实接入验证 (T1701).

默认 **跳过** — 需要 BAIDU_OCR_API_KEY + BAIDU_OCR_SECRET_KEY:

    export BAIDU_OCR_API_KEY="..."
    export BAIDU_OCR_SECRET_KEY="..."
    pytest -m real_api backend/providers/ocr/tests/test_baidu_real.py

凭证申请: docs/REAL_API_SETUP.md (3.2 百度 OCR)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.providers.ocr.baidu_ocr import BaiduOCRProvider


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not (os.getenv("BAIDU_OCR_API_KEY") and os.getenv("BAIDU_OCR_SECRET_KEY")),
        reason="BAIDU_OCR_API_KEY/SECRET_KEY 未设置 — 跳过百度 OCR 真实测试",
    ),
]


FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ocr"
SAMPLE_PNG = FIXTURE_DIR / "sample_zh_001.png"


@pytest.fixture
def provider():
    return BaiduOCRProvider()


@pytest.mark.asyncio
async def test_instantiate_with_real_credentials(provider):
    assert provider.api_key
    assert provider.secret_key


@pytest.mark.asyncio
async def test_ensure_token_acquires_bearer(provider):
    """client_credentials 应返回有效 access_token."""
    token = await provider._ensure_token()
    assert isinstance(token, str)
    assert len(token) > 20


@pytest.mark.asyncio
@pytest.mark.skipif(
    not SAMPLE_PNG.exists(),
    reason="OCR 测试样本不存在 — 跳过真实 API 调用",
)
async def test_recognize_returns_text(provider):
    image_bytes = SAMPLE_PNG.read_bytes()
    result = await provider.recognize(image_bytes, mime="image/png")
    assert isinstance(result.text, str)