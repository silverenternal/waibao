"""三区域配置 — T1202 数据驻留.

CN (中国大陆)  / SG (新加坡) / US (美国)
- 每个区域有独立的 Supabase URL + service key
- region_router 根据用户所在区域路由到对应实例
- 默认 CN(中国境内用户强制本地化)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from compliance.data_residency import Region


@dataclass(slots=True)
class RegionConfig:
    """单个区域的连接配置."""

    region: Region
    supabase_url: str
    supabase_service_key: str
    storage_bucket: str
    allowed_pii_categories: tuple[str, ...]
    require_explicit_consent_for_cross_border: bool = True
    description: str = ""


# 三个区域默认配置(可由环境变量覆盖)
REGIONS: dict[Region, RegionConfig] = {
    Region.CN: RegionConfig(
        region=Region.CN,
        supabase_url="https://supabase-cn.waibao.example",
        supabase_service_key="",  # 由 SUPABASE_CN_SERVICE_KEY 环境变量注入
        storage_bucket="waibao-cn-storage",
        allowed_pii_categories=("id_card_no", "phone", "email", "resume_text"),
        require_explicit_consent_for_cross_border=True,
        description="中国大陆(默认)— 阿里云 / 腾讯云,通过等保 2.0 三级测评",
    ),
    Region.SG: RegionConfig(
        region=Region.SG,
        supabase_url="https://supabase-sg.waibao.example",
        supabase_service_key="",  # 由 SUPABASE_SG_SERVICE_KEY 环境变量注入
        storage_bucket="waibao-sg-storage",
        allowed_pii_categories=("phone", "email", "resume_text"),
        require_explicit_consent_for_cross_border=True,
        description="新加坡(亚太)— AWS Singapore,GDPR-friendly",
    ),
    Region.US: RegionConfig(
        region=Region.US,
        supabase_url="https://supabase-us.waibao.example",
        supabase_service_key="",  # 由 SUPABASE_US_SERVICE_KEY 环境变量注入
        storage_bucket="waibao-us-storage",
        allowed_pii_categories=("phone", "email", "resume_text"),
        require_explicit_consent_for_cross_border=True,
        description="美国 — AWS us-east-1,GDPR / CCPA friendly",
    ),
}


def get_region_config(region: Region) -> RegionConfig:
    """获取区域配置;未知 region → 返回 CN."""
    return REGIONS.get(region, REGIONS[Region.CN])


def region_for_phone(phone: str | None) -> Region:
    """粗略从手机号判断区域."""
    if not phone:
        return Region.CN
    phone = phone.strip().replace(" ", "")
    if phone.startswith("+86") or phone.startswith("86"):
        return Region.CN
    if phone.startswith("+65") or phone.startswith("65"):
        return Region.SG
    if phone.startswith("+1"):
        return Region.US
    return Region.CN  # 默认


def list_regions() -> list[dict[str, Any]]:
    """列出所有区域(供前端展示)."""
    return [
        {
            "code": cfg.region.value,
            "name": _display_name(cfg.region),
            "description": cfg.description,
            "require_explicit_consent_for_cross_border": cfg.require_explicit_consent_for_cross_border,
        }
        for cfg in REGIONS.values()
    ]


def _display_name(region: Region) -> str:
    return {
        Region.CN: "中国大陆",
        Region.SG: "新加坡",
        Region.US: "美国",
        Region.EU: "欧盟",
        Region.UK: "英国",
        Region.APAC: "亚太(非中国大陆)",
        Region.GLOBAL: "全球",
    }.get(region, region.value)