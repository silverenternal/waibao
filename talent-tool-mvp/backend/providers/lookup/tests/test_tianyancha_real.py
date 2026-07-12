"""天眼查 OpenAPI 真实企业信息查询验证 (T1701).

默认 **跳过** — 需要 TIANYANCHA_API_KEY:

    export TIANYANCHA_API_KEY="..."
    pytest -m real_api backend/providers/lookup/tests/test_tianyancha_real.py

凭证申请: docs/REAL_API_SETUP.md (6 天眼查)
"""
from __future__ import annotations

import os

import pytest

from backend.providers.lookup.base import CompanyInfo
from backend.providers.lookup.tianyancha_provider import TianyanchaProvider


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not os.getenv("TIANYANCHA_API_KEY"),
        reason="TIANYANCHA_API_KEY 未设置 — 跳过天眼查真实 API 测试",
    ),
]


# 测试用公司: 腾讯计算机系统有限公司
TEST_COMPANY = "深圳市腾讯计算机系统有限公司"


@pytest.fixture
def provider():
    return TianyanchaProvider()


@pytest.mark.asyncio
async def test_instantiate_with_real_key(provider):
    assert provider.api_key
    assert provider.base_url.startswith("https://")


@pytest.mark.asyncio
async def test_search_real_company_returns_info(provider):
    """真实查询腾讯公司,应返回 CompanyInfo 列表."""
    rows = await provider.search(TEST_COMPANY)
    assert isinstance(rows, list)
    if rows:
        assert all(isinstance(r, CompanyInfo) for r in rows)
        # 第一条应包含关键字
        assert TEST_COMPANY[:4] in rows[0].name or "腾讯" in rows[0].name


@pytest.mark.asyncio
async def test_search_nonexistent_returns_empty(provider):
    """不存在的公司应返回空列表或单条空结果 (不抛异常)."""
    rows = await provider.search("不存在的虚构公司XYZ9999abc")
    assert isinstance(rows, list)