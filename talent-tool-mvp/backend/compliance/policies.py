"""法律文档模板生成器 — ToS / Privacy / DPA.

T1201/T1202 — 不同地区 + 不同租户类型可生成不同策略 bundle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class PolicyBundle:
    """一组策略文档."""

    tenant_id: str | None
    locale: str
    tos_version: str
    privacy_version: str
    dpa_version: str | None
    generated_at: datetime
    sections: dict[str, str] = field(default_factory=dict)


class PolicyGenerator:
    """根据 tenant_id + locale 生成 ToS / Privacy / DPA 文本."""

    DEFAULT_TOS = {
        "en": "Terms of Service (v{version})\n\n1. Service usage ...\n2. Restrictions ...\n3. Liability ...",
        "zh": "服务条款 (v{version})\n\n一、服务使用范围...\n二、用户行为规范...\n三、责任限制...",
    }

    DEFAULT_PRIVACY = {
        "en": (
            "Privacy Policy (v{version})\n\n"
            "1. Data we collect: name, email, resume, IP, ...\n"
            "2. How we use it: matching, communication, billing.\n"
            "3. Cross-border transfer: only with consent.\n"
            "4. Retention: {retention_days} days.\n"
            "5. Your rights: access, rectification, deletion, portability."
        ),
        "zh": (
            "隐私政策 (v{version})\n\n"
            "一、收集信息:姓名、邮箱、简历、IP 等。\n"
            "二、使用目的:候选人匹配、沟通、计费。\n"
            "三、跨境传输:仅在获得用户同意后进行。\n"
            "四、保留期限:{retention_days} 天。\n"
            "五、用户权利:查询、更正、删除、可携。"
        ),
    }

    DEFAULT_DPA = {
        "en": (
            "Data Processing Agreement (v{version})\n\n"
            "Roles: Controller = Customer, Processor = waibao.\n"
            "Sub-processors: {sub_processors}.\n"
            "Cross-border: {cross_border}."
        ),
        "zh": (
            "数据处理协议 (v{version})\n\n"
            "角色:控制者 = 客户,处理者 = waibao。\n"
            "分处理者:{sub_processors}。\n"
            "跨境传输:{cross_border}。"
        ),
    }

    def __init__(self) -> None:
        self._templates: dict[str, dict[str, str]] = {
            "tos": dict(self.DEFAULT_TOS),
            "privacy": dict(self.DEFAULT_PRIVACY),
            "dpa": dict(self.DEFAULT_DPA),
        }

    def override(self, doc: str, locale: str, body: str) -> None:
        """覆盖某个 doc + locale 的模板."""
        self._templates.setdefault(doc, {})[locale] = body

    def generate(
        self,
        *,
        tenant_id: str | None = None,
        locale: str = "en",
        tos_version: str = "1.0",
        privacy_version: str = "1.0",
        dpa_version: str | None = "1.0",
        retention_days: int = 365,
        sub_processors: list[str] | None = None,
        cross_border: bool = False,
    ) -> PolicyBundle:
        locale = locale if locale in self._templates["tos"] else "en"
        tos_tmpl = self._templates["tos"][locale]
        privacy_tmpl = self._templates["privacy"][locale]
        dpa_tmpl = self._templates["dpa"][locale] if dpa_version else None

        sections: dict[str, str] = {
            "tos": tos_tmpl.format(version=tos_version),
            "privacy": privacy_tmpl.format(
                version=privacy_version,
                retention_days=retention_days,
            ),
        }
        if dpa_tmpl is not None:
            sections["dpa"] = dpa_tmpl.format(
                version=dpa_version,
                sub_processors=", ".join(sub_processors or []) or "n/a",
                cross_border="yes (with explicit consent)" if cross_border else "no",
            )
        return PolicyBundle(
            tenant_id=tenant_id,
            locale=locale,
            tos_version=tos_version,
            privacy_version=privacy_version,
            dpa_version=dpa_version,
            generated_at=datetime.now(timezone.utc),
            sections=sections,
        )


_singleton: PolicyGenerator | None = None


def get_policy_generator() -> PolicyGenerator:
    global _singleton
    if _singleton is None:
        _singleton = PolicyGenerator()
    return _singleton