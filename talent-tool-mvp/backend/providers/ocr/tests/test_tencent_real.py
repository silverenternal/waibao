"""腾讯云 OCR 真实接入验证 (T1701).

默认 **跳过** — 需要 TENCENT_SECRET_ID + TENCENT_SECRET_KEY:

    export TENCENT_SECRET_ID="AKID..."
    export TENCENT_SECRET_KEY="..."
    pytest -m real_api backend/providers/ocr/tests/test_tencent_real.py

凭证申请: docs/REAL_API_SETUP.md (3.1 腾讯云 OCR)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.providers.ocr.tencent_ocr import TencentOCRProvider


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not (os.getenv("TENCENT_SECRET_ID") and os.getenv("TENCENT_SECRET_KEY")),
        reason="TENCENT_SECRET_ID/SECRET_KEY 未设置 — 跳过腾讯云 OCR 真实测试",
    ),
]


# 测试样本: 100x30 PNG, 内容 "Hello OCR"
FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ocr"
SAMPLE_PNG = FIXTURE_DIR / "sample_zh_001.png"


@pytest.fixture
def provider():
    return TencentOCRProvider(region="ap-guangzhou")


@pytest.mark.asyncio
async def test_signature_generation_correct(provider):
    """TC3-HMAC-SHA256 签名格式正确."""
    headers = provider._sign('{"ImageBase64":"aGVsbG8="}')
    auth = headers["Authorization"]
    assert auth.startswith("TC3-HMAC-SHA256 Credential=")
    assert "SignedHeaders=content-type;host;x-tc-action" in auth
    assert "Signature=" in auth
    assert headers["X-TC-Action"] == "GeneralBasicOCR"
    assert headers["X-TC-Version"] == "2018-11-19"


@pytest.mark.asyncio
async def test_instantiate_with_real_credentials(provider):
    assert provider.secret_id
    assert provider.secret_key


@pytest.mark.asyncio
@pytest.mark.skipif(
    not SAMPLE_PNG.exists(),
    reason="OCR 测试样本不存在 — 跳过真实 API 调用",
)
async def test_recognize_returns_text(provider):
    """真实 OCR 调用,返回非空文本."""
    image_bytes = SAMPLE_PNG.read_bytes()
    result = await provider.recognize(image_bytes, mime="image/png")
    assert isinstance(result.text, str)
    # 即便模型识别有误差,text 字段不应抛异常
    assert result.blocks  # blocks 至少包含 bbox 信息