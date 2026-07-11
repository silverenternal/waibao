"""CompanyLookup Provider 抽象基类 (企业工商信息查询)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CompanyInfo:
    """统一的企业信息."""

    name: str
    legal_representative: str | None = None
    registered_capital: str | None = None
    established_date: str | None = None
    status: str | None = None
    industry: str | None = None
    business_scope: str | None = None
    address: str | None = None
    unified_social_credit_code: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class CompanyLookupProvider(ABC):
    """企业工商信息查询 provider."""

    provider_name: str = "abstract"

    @abstractmethod
    async def search(self, keyword: str, **kwargs: Any) -> list[CompanyInfo]: ...

    @abstractmethod
    async def get_detail(
        self, company_id: str, **kwargs: Any
    ) -> CompanyInfo: ...
