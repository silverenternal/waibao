"""OpenAI text-embedding-3 真实接入验证 (T1701).

默认 **跳过** — 复用 OPENAI_API_KEY:

    export OPENAI_API_KEY="sk-..."
    pytest -m real_api backend/providers/embedding/tests/test_openai_real.py

凭证申请: docs/REAL_API_SETUP.md (2.1 OpenAI Embedding)
"""
from __future__ import annotations

import os

import pytest

from backend.providers.embedding.openai_embedding import OpenAIEmbeddingProvider


def _is_real_openai_key() -> bool:
    k = os.getenv("OPENAI_API_KEY", "")
    return k.startswith("sk-") and len(k) > 20


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not _is_real_openai_key(),
        reason="OPENAI_API_KEY 缺失或非真实 — 跳过 Embedding 真实 API 测试",
    ),
]


@pytest.fixture
def provider():
    return OpenAIEmbeddingProvider(default_model="text-embedding-3-small")


@pytest.mark.asyncio
async def test_embed_returns_correct_dimensions(provider):
    """text-embedding-3-small 应返回 1536 维向量."""
    result = await provider.embed(["hello world", "你好世界"])
    assert len(result.vectors) == 2
    assert len(result.vectors[0]) == 1536
    assert len(result.vectors[1]) == 1536
    assert result.usage_tokens > 0


@pytest.mark.asyncio
async def test_embed_large_model(provider):
    """text-embedding-3-large 返回 3072 维."""
    p = OpenAIEmbeddingProvider(default_model="text-embedding-3-large")
    result = await p.embed(["test"])
    assert len(result.vectors[0]) == 3072


@pytest.mark.asyncio
async def test_embed_one_returns_vector(provider):
    vec = await provider.embed_one("test text")
    assert isinstance(vec, list)
    assert len(vec) == 1536
    # 向量元素应是 float
    assert all(isinstance(x, float) for x in vec)


def test_dimensions_property():
    p = OpenAIEmbeddingProvider(default_model="text-embedding-3-small")
    assert p.dimensions == 1536
    p2 = OpenAIEmbeddingProvider(default_model="text-embedding-3-large")
    assert p2.dimensions == 3072