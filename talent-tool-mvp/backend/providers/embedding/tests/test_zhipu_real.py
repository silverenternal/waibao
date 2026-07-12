"""智谱 Embedding-2 真实接入验证 (T1701).

默认 **跳过** — 复用 ZHIPU_API_KEY:

    export ZHIPU_API_KEY="..."
    pytest -m real_api backend/providers/embedding/tests/test_zhipu_real.py

凭证申请: docs/REAL_API_SETUP.md (2.2 智谱 Embedding)
"""
from __future__ import annotations

import os

import pytest

from backend.providers.embedding.zhipu_embedding import ZhipuEmbeddingProvider


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not os.getenv("ZHIPU_API_KEY"),
        reason="ZHIPU_API_KEY 未设置 — 跳过智谱 Embedding 真实 API 测试",
    ),
]


@pytest.fixture
def provider():
    return ZhipuEmbeddingProvider(default_model="embedding-2")


@pytest.mark.asyncio
async def test_embed_returns_1024_dim(provider):
    """embedding-2 应返回 1024 维."""
    result = await provider.embed(["hello", "你好"])
    assert len(result.vectors) == 2
    assert all(len(v) == 1024 for v in result.vectors)


@pytest.mark.asyncio
async def test_embed_chinese_text(provider):
    """中文文本应正常编码."""
    result = await provider.embed(["机器学习", "深度学习"])
    assert len(result.vectors) == 2


def test_supported_models_contains_default():
    p = ZhipuEmbeddingProvider()
    assert "embedding-2" in p.supported_models