"""工商查询业务模块 (T103).

职责链路:
    ocr_data + hint_credit_code
        ↓
    credit_code_validator (GB 32100-2015)
        ↓
    providers.lookup (默认 LOOKUP_PROVIDER env,fallback mock)
        ↓
    risk score 0.0-1.0
        ↓
    ComplianceVerdict (dict, 含 trust_score/warnings/expiry_risk/cross_check)

主入口:
    assess_company(credit_code=..., company_name=..., **kwargs) -> dict
    verify_credential_against_lookup(ocr_data) -> dict
    list_expiry_alerts(organisation_id=..., days_ahead=30) -> list[dict]
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from providers.exceptions import ProviderError
from providers.lookup.base import CompanyInfo, CompanyLookupProvider

from services.credit_code_validator import (
    validate as validate_credit_code,
)

logger = logging.getLogger("recruittech.services.compliance")


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------
@dataclass(slots=True)
class ComplianceVerdict:
    """统一审核结果."""

    credit_code: str
    credit_code_valid: bool
    trust_score: float
    risk_level: str                                  # low / medium / high
    company_match: bool
    matched_company: dict | None
    warnings: list[str]
    expiry_alerts: list[dict]
    lookup_provider: str
    lookup_status: str | None
    cross_check: dict = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Provider 选择
# --------------------------------------------------------------------------
def _resolve_lookup_provider() -> CompanyLookupProvider:
    """从 registry 拿 lookup provider. LOOKUP_PROVIDER 未配置时降级到 mock.

    读取 environment var LOOKUP_PROVIDER:
        - 默认 'mock' (不需要任何 credential,适合本地/CI)
        - 'tianyancha': TianyanchaProvider (需要 TIANYANCHA_API_KEY)
        - 'qichacha': QichachaProvider (需要 QICHACHA_APP_KEY/SECRET)

    如果 env 要求 tianyancha 但 TIANYANCHA_API_KEY 缺失,降级到 mock 并 log warning。
    """
    name = (os.getenv("LOOKUP_PROVIDER") or "mock").lower()
    try:
        from providers.registry import get_lookup_provider

        provider = get_lookup_provider()
        # sanity: 强行要求 credential 的 provider,缺 key 时 registry 会抛
        if name != "mock" and getattr(provider, "provider_name", "") == "mock":
            logger.warning(
                f"LOOKUP_PROVIDER={name} requested but provider fell back to mock; "
                "check your credentials"
            )
        return provider
    except ProviderError as exc:
        logger.warning(
            f"LOOKUP_PROVIDER={name} unavailable: {exc}; using mock"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"get_lookup_provider() failed: {exc}; using mock"
        )
    # fallback: 显式 mock provider 实例
    from providers.lookup.mock_provider import MockLookupProvider
    return MockLookupProvider()


# --------------------------------------------------------------------------
# 公司信息归一化
# --------------------------------------------------------------------------
def _company_to_dict(c: CompanyInfo) -> dict:
    return {
        "name": c.name,
        "legal_representative": c.legal_representative,
        "registered_capital": c.registered_capital,
        "established_date": c.established_date,
        "status": c.status,
        "industry": c.industry,
        "business_scope": c.business_scope,
        "address": c.address,
        "unified_social_credit_code": c.unified_social_credit_code,
        "raw": c.raw,
    }


def _company_status_active(status: str | None) -> bool:
    """判断公司是否 '存续' / '正常' 等可用状态."""
    if not status:
        return False
    s = status.strip()
    return s in ("存续", "正常", "在营", "开业", "active", "ACTIVE")


# --------------------------------------------------------------------------
# 风险评分
# --------------------------------------------------------------------------
def _score_from_cross_check(
    *,
    credit_code_valid: bool,
    lookup_hit: bool,
    credit_code_matches_lookup: bool,
    status_active: bool,
    established_years: int | None,
) -> tuple[float, str]:
    """根据多项信号计算 0.0-1.0 trust_score.

    Returns: (trust_score, risk_level)
    """
    score = 0.0

    # 1. 信用代码合法 → 0.30
    if credit_code_valid:
        score += 0.30

    # 2. 工商查询有命中 → 0.20
    if lookup_hit:
        score += 0.20

    # 3. 主体身份匹配 (OCR/code 与供应商返回一致) → 0.20
    if credit_code_matches_lookup:
        score += 0.20

    # 4. 企业状态存续 → 0.15
    if status_active:
        score += 0.15

    # 5. 经营年限 (1-30 年) 适当加分 (最多 0.15)
    if established_years is not None:
        if established_years >= 5:
            score += 0.15
        elif established_years >= 2:
            score += 0.08
        elif established_years >= 1:
            score += 0.03

    # clamp
    score = round(max(0.0, min(1.0, score)), 2)

    if score >= 0.7:
        risk = "low"
    elif score >= 0.4:
        risk = "medium"
    else:
        risk = "high"
    return score, risk


def _calc_established_years(established_date: str | None, *, today: date | None = None) -> int | None:
    if not established_date:
        return None
    try:
        d = datetime.strptime(established_date[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    base = today or date.today()
    years = base.year - d.year - ((base.month, base.day) < (d.month, d.day))
    return max(0, years)


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
async def assess_company(
    *,
    credit_code: str | None = None,
    company_name: str | None = None,
    detail: bool = True,
    today: date | None = None,
) -> dict:
    """评估一家公司的合规可信度.

    链路:
        1) credit_code_validator (GB 32100-2015)
        2) lookup provider 默认 'mock',走 LOOKUP_PROVIDER env
        3) 计算 trust_score + risk_level
        4) 返回 ComplianceVerdict.to_dict()
    """
    # 1. 信用代码
    cc_check = validate_credit_code(credit_code)
    normalized_code = cc_check.normalized

    warnings: list[str] = list(cc_check.errors)

    # 2. Lookup provider
    provider = _resolve_lookup_provider()
    provider_name = getattr(provider, "provider_name", "unknown")

    matched: CompanyInfo | None = None
    if credit_code and normalized_code and cc_check.is_valid:
        try:
            matched = await provider.get_detail(normalized_code)
        except ProviderError as exc:
            logger.warning(f"lookup by credit_code failed: {exc}")
            warnings.append(f"工商查询失败: {exc.message}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"lookup by credit_code exception: {exc}")
            warnings.append(f"工商查询异常: {exc}")
    elif company_name:
        try:
            hits = await provider.search(company_name)
            if hits:
                # 优先匹配名称
                picks = [h for h in hits if company_name and company_name in (h.name or "")]
                matched = picks[0] if picks else hits[0]
        except ProviderError as exc:
            logger.warning(f"lookup by name failed: {exc}")
            warnings.append(f"工商查询失败: {exc.message}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"lookup by name exception: {exc}")
            warnings.append(f"工商查询异常: {exc}")

    lookup_status: str | None = None
    lookup_hit = bool(matched)
    credit_code_matches_lookup = False
    established_years: int | None = None
    matched_dict: dict | None = None

    if matched is not None:
        matched_dict = _company_to_dict(matched)
        lookup_status = matched.status
        # 校验 OCR/code 与查询返回是否一致
        if normalized_code and matched.unified_social_credit_code:
            cc_matches = (
                normalize_for_compare(normalized_code)
                == normalize_for_compare(matched.unified_social_credit_code)
            )
            credit_code_matches_lookup = cc_matches
            if not cc_matches:
                warnings.append("信用代码与工商查询结果不一致")
        established_years = _calc_established_years(matched.established_date, today=today)

    # 3. 评分
    trust_score, risk_level = _score_from_cross_check(
        credit_code_valid=cc_check.is_valid,
        lookup_hit=lookup_hit,
        credit_code_matches_lookup=credit_code_matches_lookup,
        status_active=_company_status_active(lookup_status),
        established_years=established_years,
    )

    company_match = lookup_hit and (
        bool(company_name and matched and company_name in (matched.name or ""))
        or credit_code_matches_lookup
        or (not company_name and not credit_code)
    )

    summary = _summarize(
        cc_check.is_valid, lookup_hit, credit_code_matches_lookup,
        lookup_status, established_years,
    )

    verdict = ComplianceVerdict(
        credit_code=normalized_code,
        credit_code_valid=cc_check.is_valid,
        trust_score=trust_score,
        risk_level=risk_level,
        company_match=company_match,
        matched_company=matched_dict,
        warnings=warnings,
        expiry_alerts=[],
        lookup_provider=provider_name,
        lookup_status=lookup_status,
        cross_check={
            "credit_code_valid": cc_check.is_valid,
            "lookup_hit": lookup_hit,
            "credit_code_matches_lookup": credit_code_matches_lookup,
            "status_active": _company_status_active(lookup_status),
            "established_years": established_years,
        },
        summary=summary,
    )
    return verdict.to_dict()


def _summarize(
    cc_valid: bool,
    lookup_hit: bool,
    cc_match: bool,
    lookup_status: str | None,
    years: int | None,
) -> str:
    if cc_valid and lookup_hit and cc_match and _company_status_active(lookup_status):
        ys = f"{years}年" if years is not None else "未披露"
        return f"基础验证通过:信用代码合法、{ys}经营、状态{lookup_status}。"
    if cc_valid and not lookup_hit:
        return "信用代码合法,工商查询未命中。"
    if not cc_valid:
        return "信用代码不合规,建议人工复核。"
    if lookup_hit and not _company_status_active(lookup_status):
        return f"工商信息命中,但状态为{lookup_status!r},需复核。"
    return "基础核验完成,详见交叉验证结果。"


def normalize_for_compare(code: str | None) -> str:
    """把任意代码归一到可比较的字符串 (upper + 去分隔符)."""
    if not code:
        return ""
    return "".join(c for c in code.upper() if c.isalnum())


# --------------------------------------------------------------------------
# 与 OCR 结果联合校验
# --------------------------------------------------------------------------
async def verify_credential_against_lookup(ocr_data: dict | None) -> dict:
    """从 OCR 抽取的字段推断出信用代码 + 公司名,调用 assess_company.

    Expected ocr_data keys (extractor 抽取):
        - credit_code: 统一社会信用代码
        - company_name / name: 公司名
        - legal_rep: 法人
        - established_date: 注册日期 (ISO)
        - status: 企业状态
    """
    if not isinstance(ocr_data, dict):
        ocr_data = {}

    cc = ocr_data.get("credit_code") or ocr_data.get("hint_credit_code") or ""
    name = ocr_data.get("company_name") or ocr_data.get("name") or ""

    return await assess_company(credit_code=cc, company_name=name)


# --------------------------------------------------------------------------
# 到期提醒 (expiry alerts)
# --------------------------------------------------------------------------
_VALID_STATUSES = ("存续", "正常", "在营", "开业", "active", "ACTIVE")
_SOON_EXPIRY_THRESHOLD = 30  # 默认 30 天内到期


def compute_expiry_alerts(
    credentials: list[dict],
    *,
    today: date | None = None,
    days_ahead: int = _SOON_EXPIRY_THRESHOLD,
) -> list[dict]:
    """根据 credential list 中的 expiry_date 字段返回即将到期 / 已过期的列表.

    Inputs:
        credentials: list of dicts with `expiry_date` / `expiry_at` ISO string,
                     optional `organisation_id`, `id`, `file_url`, `company_name`.
        today: 基准日期 (默认今天)
        days_ahead: 多少天内视为 "即将到期"

    Returns: 排序后的 list of alerts, 每个元素结构:
        {"credential_id": ..., "organisation_id": ..., "company_name": ...,
         "days_to_expiry": int, "severity": "expired" | "critical" | "warning",
         "expires_at": "YYYY-MM-DD"}
    """
    base = today or date.today()
    alerts: list[dict] = []
    for c in credentials or []:
        exp_raw = c.get("expiry_date") or c.get("expiry_at") or c.get("expires_at")
        if not exp_raw:
            continue
        try:
            exp_date = datetime.strptime(str(exp_raw)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        delta = (exp_date - base).days
        severity: str
        if delta < 0:
            severity = "expired"
        elif delta <= 7:
            severity = "critical"
        elif delta <= days_ahead:
            severity = "warning"
        else:
            continue  # 不在警告窗口
        alerts.append(
            {
                "credential_id": c.get("id"),
                "organisation_id": c.get("organisation_id"),
                "company_name": c.get("company_name") or c.get("name"),
                "credential_type": c.get("credential_type"),
                "file_url": c.get("file_url"),
                "expires_at": exp_date.isoformat(),
                "days_to_expiry": delta,
                "severity": severity,
                "trust_score": c.get("trust_score"),
                "verified": c.get("verified"),
            }
        )
    # 优先级排序:expired > critical > warning,其次按剩余天数升序
    severity_rank = {"expired": 0, "critical": 1, "warning": 2}
    alerts.sort(
        key=lambda a: (
            severity_rank.get(a.get("severity"), 9),
            a.get("days_to_expiry", 0),
        )
    )
    return alerts


async def list_expiry_alerts(
    *,
    organisation_id: str | None = None,
    credentials: list[dict] | None = None,
    days_ahead: int = _SOON_EXPIRY_THRESHOLD,
    supabase: Any | None = None,
    today: date | None = None,
) -> list[dict]:
    """提供两种模式:
    1) 直接传 credentials (测试 / 推荐)
    2) 通过 supabase 拉 (生产);若 supabase 不可用 → 返回空数组
    """
    if credentials is not None:
        return compute_expiry_alerts(credentials, today=today, days_ahead=days_ahead)

    if supabase is None:
        try:
            from api.deps import get_supabase_admin
            supabase = get_supabase_admin()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"supabase unavailable for expiry alerts: {exc}")
            return []

    try:
        q = supabase.table("company_credentials").select("*")
        if organisation_id:
            q = q.eq("organisation_id", organisation_id)
        result = q.execute()
        return compute_expiry_alerts(result.data or [], today=today, days_ahead=days_ahead)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"fetch credentials failed: {exc}")
        return []


# Re-export for tests
__all__ = [
    "ComplianceVerdict",
    "assess_company",
    "verify_credential_against_lookup",
    "compute_expiry_alerts",
    "list_expiry_alerts",
    "normalize_for_compare",
]
