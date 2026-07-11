"""CompanyLookup Mock Provider — 返回可复现的占位工商信息."""
from __future__ import annotations

import hashlib
from typing import Any

from .base import CompanyInfo, CompanyLookupProvider


class MockLookupProvider(CompanyLookupProvider):
    """纯本地 mock,基于 keyword hash 生成稳定结果."""

    provider_name = "mock"

    async def search(self, keyword: str, **kwargs: Any) -> list[CompanyInfo]:
        # 用 keyword 哈希生成 1-3 个固定条目,保证可复现
        n = (int(hashlib.md5(keyword.encode()).hexdigest(), 16) % 3) + 1
        return [
            CompanyInfo(
                name=f"{keyword} 子公司 {i + 1}",
                legal_representative=f"mock-rep-{i}",
                registered_capital="100万",
                established_date="2020-01-01",
                status="存续",
                industry="mock 行业",
                business_scope="mock 经营范围",
                address=f"mock 地址 {i}",
                unified_social_credit_code=f"MOCK{i:04d}",
            )
            for i in range(n)
        ]

    async def get_detail(self, company_id: str, **kwargs: Any) -> CompanyInfo:
        return CompanyInfo(
            name=f"[mock-lookup] {company_id}",
            legal_representative="mock-rep",
            registered_capital="100万",
            established_date="2020-01-01",
            status="存续",
            industry="mock 行业",
            business_scope="mock 经营范围",
            address="mock 地址",
            unified_social_credit_code=company_id,
            raw={"mock": True, "company_id": company_id},
        )