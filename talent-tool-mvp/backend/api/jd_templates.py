"""JD templates API (T604).

Returns a curated library of industry-specific JD starter templates.
Each template provides:
  - structural skeleton (responsibilities / hard requirements / nice-to-haves)
  - recommended salary band range (rough, market-anchored)
  - over-spec heuristic warnings — i.e. fields that tend to be over-specified
    for this role family and that the dept head should reconsider.

The templates are static (not LLM-generated) so the picker UI stays
deterministic and offline-friendly. The 'apply' route just hands the
template back — actual JD generation still flows through job_spec_agent.

Design principles:
  - Templates are industry-agnostic in tone but industry-specific in
    structure (e.g. sales adds quota/CRM; design adds portfolio link).
  - `over_spec_warnings` are short, actionable guardrails, not lectures.
  - Stored as a constant dict — no DB rows so we never serve stale or
    low-quality templates.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger("recruittech.api.jd_templates")
router = APIRouter()


# ---------------------------------------------------------------------------
# Static template library
# ---------------------------------------------------------------------------

_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "backend_engineer",
        "industry": "互联网 / 软件",
        "title": "后端工程师",
        "description": "负责后端服务的设计、开发与维护,擅长高并发、分布式系统。",
        "responsibilities": [
            "负责核心后端服务的功能开发、性能优化、稳定性保障",
            "参与系统架构设计、code review、技术方案评审",
            "与产品、前端、测试紧密协作,按时按质交付需求",
            "撰写技术文档,沉淀团队知识",
        ],
        "hard_requirements": [
            {"category": "技能", "value": "Python / Go / Java 至少一门主力语言", "min_years": 3},
            {"category": "技能", "value": "MySQL / PostgreSQL + Redis 实战经验"},
            {"category": "技能", "value": "RESTful API、微服务框架使用经验"},
            {"category": "经验", "value": "完整的后端项目交付经验", "min_years": 3},
        ],
        "nice_to_haves": [
            "熟悉 Kubernetes / Docker 容器化与编排",
            "开源项目贡献经验",
            "具备性能调优、链路追踪、监控告警体系建设经验",
        ],
        "team_culture": {
            "work_style": "小步快跑 · 跨职能协作",
            "pace": "敏捷双周迭代",
            "autonomy": "高 — 自驱选择实现路径",
        },
        "salary_band": {"currency": "CNY", "min_k": 25, "max_k": 55, "period": "month"},
        "over_spec_warnings": [
            "要求 5+ 年分布式经验但职级 P5 — 薪资带宽可能过低",
            "同一份 JD 同时要求算法、数据、业务 — 建议拆分岗位",
        ],
    },
    {
        "id": "frontend_engineer",
        "industry": "互联网 / 软件",
        "title": "前端工程师",
        "description": "负责 Web / 移动端 H5 前端开发,与设计、后端协作还原产品体验。",
        "responsibilities": [
            "负责 Web 应用 / 管理后台 / 移动 H5 的页面与组件开发",
            "与设计师共建组件库,推动 UI 工程化",
            "性能优化、首屏体验、可访问性",
            "梳理前端规范、文档化最佳实践",
        ],
        "hard_requirements": [
            {"category": "技能", "value": "React / Vue 至少一门主力框架", "min_years": 2},
            {"category": "技能", "value": "TypeScript、ES6+ 扎实掌握"},
            {"category": "技能", "value": "Webpack / Vite 等构建工具使用经验"},
            {"category": "经验", "value": "中大型前端项目实战", "min_years": 2},
        ],
        "nice_to_haves": [
            "有开源组件库 / 设计系统贡献",
            "熟悉移动端混合开发 (RN / Weex / 小程序)",
            "具备 Node BFF 或 SSR 经验",
        ],
        "team_culture": {
            "work_style": "设计驱动 · 像素精准",
            "pace": "双周迭代 + 长尾打磨",
            "autonomy": "中高",
        },
        "salary_band": {"currency": "CNY", "min_k": 18, "max_k": 45, "period": "month"},
        "over_spec_warnings": [
            "要求 5 年经验却只是中级岗位 — 容易招不到或留不住",
        ],
    },
    {
        "id": "product_manager",
        "industry": "互联网 / 软件",
        "title": "产品经理",
        "description": "负责产品全生命周期管理,从需求洞察到上线迭代。",
        "responsibilities": [
            "负责产品规划、PRD 撰写、需求优先级排序",
            "深入用户场景,挖掘未被满足的需求",
            "协同设计、研发、测试推动产品上线",
            "基于数据持续迭代,达成业务指标",
        ],
        "hard_requirements": [
            {"category": "经验", "value": "互联网产品经验", "min_years": 3},
            {"category": "技能", "value": "Axure / Figma / 流程图工具"},
            {"category": "技能", "value": "SQL / Excel 数据分析能力"},
        ],
        "nice_to_haves": [
            "0→1 产品孵化经验",
            "B 端 / SaaS 行业背景",
            "工程或设计跨界背景",
        ],
        "team_culture": {
            "work_style": "用户驱动",
            "pace": "周节奏快速迭代",
            "autonomy": "高",
        },
        "salary_band": {"currency": "CNY", "min_k": 20, "max_k": 60, "period": "month"},
        "over_spec_warnings": [
            "既要求 0→1 经验又要求 100 人规模管理经验 — 难兼得,建议分级",
        ],
    },
    {
        "id": "operations",
        "industry": "互联网 / 零售 / 服务",
        "title": "运营专员 / 主管",
        "description": "负责用户、内容或商品运营,围绕指标设计并推动增长策略。",
        "responsibilities": [
            "制定运营策略,落地活动方案",
            "用户分层运营,提升留存与转化",
            "基于数据复盘活动,沉淀方法论",
            "协同产品、客服、市场共同达成目标",
        ],
        "hard_requirements": [
            {"category": "经验", "value": "运营相关经验", "min_years": 2},
            {"category": "技能", "value": "活动策划、文案撰写"},
            {"category": "技能", "value": "基础数据分析"},
        ],
        "nice_to_haves": [
            "有过 0→1 社群 / 用户增长案例",
            "熟悉私域 / 短视频运营",
        ],
        "team_culture": {
            "work_style": "目标导向",
            "pace": "高强度 996 / 弹性",
            "autonomy": "中",
        },
        "salary_band": {"currency": "CNY", "min_k": 12, "max_k": 35, "period": "month"},
        "over_spec_warnings": [
            "要求英语六级 + 海归背景 + 多平台资源 — 与薪资带宽不匹配",
        ],
    },
    {
        "id": "designer",
        "industry": "互联网 / 软件 / 文化",
        "title": "UI / UX 设计师",
        "description": "负责产品的视觉与体验设计,与产品、研发紧密合作。",
        "responsibilities": [
            "负责 Web / 移动端 UI / 交互设计",
            "沉淀设计规范,推动设计系统建设",
            "参与用户研究、用研洞察转设计",
        ],
        "hard_requirements": [
            {"category": "技能", "value": "Figma / Sketch / XD 精通"},
            {"category": "技能", "value": "组件化、视觉规范文档能力"},
            {"category": "经验", "value": "完整上线项目", "min_years": 2},
        ],
        "nice_to_haves": [
            "动效设计 (Principle / Lottie)",
            "B 端复杂表单 / 数据可视化经验",
        ],
        "team_culture": {
            "work_style": "设计驱动",
            "pace": "中等节奏",
            "autonomy": "中高",
        },
        "salary_band": {"currency": "CNY", "min_k": 15, "max_k": 40, "period": "month"},
        "over_spec_warnings": [
            "要求 985/211 院校会触碰公平招聘红线,建议改为作品集评估",
        ],
    },
    {
        "id": "sales",
        "industry": "B2B / SaaS / 零售",
        "title": "销售经理",
        "description": "负责客户开发、商务谈判、回款及客户关系维护。",
        "responsibilities": [
            "完成公司下达的销售指标",
            "新客户开发,老客户深耕",
            "商务谈判、合同签订、回款跟进",
            "市场情报收集,反馈产品建议",
        ],
        "hard_requirements": [
            {"category": "经验", "value": "To B / SaaS 销售经验", "min_years": 2},
            {"category": "技能", "value": "客户拜访、商务谈判"},
            {"category": "特质", "value": "抗压能力与结果导向"},
        ],
        "nice_to_haves": [
            "有行业大客户资源",
            "具备英语商务沟通能力",
        ],
        "team_culture": {
            "work_style": "结果导向",
            "pace": "高强度",
            "autonomy": "高",
        },
        "salary_band": {"currency": "CNY", "min_k": 10, "max_k": 40, "period": "month", "note": "底薪 + 提成"},
        "over_spec_warnings": [
            "硬性要求男性 / 形象气质佳 — 涉嫌性别 / 容貌歧视,会过不了合规审查",
        ],
    },
    {
        "id": "hr_specialist",
        "industry": "全行业",
        "title": "HRBP / 招聘专员",
        "description": "负责人力资源模块,常见招聘、员工关系、绩效方向。",
        "responsibilities": [
            "负责招聘全流程 (需求 → 面试 → Offer → 入职)",
            "员工关系、绩效辅导、组织氛围建设",
            "与业务负责人紧密对齐人才需求",
        ],
        "hard_requirements": [
            {"category": "经验", "value": "人力资源相关经验", "min_years": 2},
            {"category": "技能", "value": "招聘渠道运营、人才评估"},
        ],
        "nice_to_haves": [
            "有人力资源管理师 / 心理咨询师证书",
            "互联网行业 HRBP 经验",
        ],
        "team_culture": {
            "work_style": "服务型业务伙伴",
            "pace": "中等",
            "autonomy": "中高",
        },
        "salary_band": {"currency": "CNY", "min_k": 10, "max_k": 30, "period": "month"},
        "over_spec_warnings": [
            "要求未婚未育 / 限女性 — 涉嫌婚育歧视,务必删除",
        ],
    },
    {
        "id": "finance",
        "industry": "金融 / 全行业",
        "title": "财务专员 / 主管",
        "description": "负责公司财务核算、税务、预算等常规财务工作。",
        "responsibilities": [
            "日常账务处理、月结、年结",
            "税务申报、发票管理",
            "预算编制、成本分析",
        ],
        "hard_requirements": [
            {"category": "证书", "value": "初级 / 中级会计职称"},
            {"category": "技能", "value": "金蝶 / 用友 / SAP 至少其一"},
            {"category": "经验", "value": "财务相关经验", "min_years": 2},
        ],
        "nice_to_haves": [
            "CPA / ACCA 在考 / 已持证",
            "制造业或互联网行业经验",
        ],
        "team_culture": {
            "work_style": "严谨细致",
            "pace": "月末季度峰值",
            "autonomy": "中",
        },
        "salary_band": {"currency": "CNY", "min_k": 10, "max_k": 35, "period": "month"},
        "over_spec_warnings": [
            "要求 985 财务专业 + CPA 全科通过 — 与薪资带宽不符",
        ],
    },
    {
        "id": "legal",
        "industry": "全行业",
        "title": "法务专员 / 法务主管",
        "description": "负责合同、合规、纠纷处理等法务工作。",
        "responsibilities": [
            "合同起草、审核、修订",
            "法律合规支持、风险评估",
            "诉讼 / 仲裁案件跟踪处理",
        ],
        "hard_requirements": [
            {"category": "证书", "value": "法律职业资格证书"},
            {"category": "学历", "value": "法学本科及以上"},
            {"category": "经验", "value": "企业 / 律所法务经验", "min_years": 2},
        ],
        "nice_to_haves": [
            "有境外律师资格 / LLB / LLM",
            "上市公司合规经验",
        ],
        "team_culture": {
            "work_style": "严谨稳健",
            "pace": "项目驱动",
            "autonomy": "高",
        },
        "salary_band": {"currency": "CNY", "min_k": 12, "max_k": 45, "period": "month"},
        "over_spec_warnings": [
            "要求司法考试 A 证 + 英文法律文书能力 — 人才稀缺,薪资带宽需上调",
        ],
    },
    {
        "id": "executive",
        "industry": "全行业",
        "title": "高管 / VP / CXO",
        "description": "负责条线 / 子公司整体经营,对业务结果负责。",
        "responsibilities": [
            "制定条线战略、年度 OKR",
            "搭建组织、培养梯队",
            "直接对业务结果 / 经营指标负责",
        ],
        "hard_requirements": [
            {"category": "经验", "value": "行业头部企业同岗经验", "min_years": 10},
            {"category": "经验", "value": "百人团队管理经验", "min_years": 5},
            {"category": "经验", "value": "从 0 到 1 / 10 到 100 操盘案例"},
        ],
        "nice_to_haves": [
            "MBA / 海外名校",
            "行业人脉广泛",
        ],
        "team_culture": {
            "work_style": "战略驱动",
            "pace": "高强度",
            "autonomy": "极高",
        },
        "salary_band": {"currency": "CNY", "min_k": 50, "max_k": 200, "period": "month", "note": "含股权 / 期权"},
        "over_spec_warnings": [
            "年轻化要求 (35 岁以下) + 10 年以上经验 — 自相矛盾,务必修改",
            "硬性限男性 — 涉嫌性别歧视,务必删除",
        ],
    },
]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/list")
async def list_jd_templates(
    industry: str = Query(default=None, description="按行业过滤"),
    search: str = Query(default=None, description="按标题 / 行业 / 描述关键字过滤"),
) -> Dict[str, Any]:
    """返回全部 JD 模板(或过滤后)。"""
    items: List[Dict[str, Any]] = []
    for tpl in _TEMPLATES:
        if industry and tpl["industry"] != industry:
            continue
        if search:
            needle = search.lower()
            if (
                needle not in tpl["title"].lower()
                and needle not in tpl["industry"].lower()
                and needle not in tpl["description"].lower()
            ):
                continue
        # 摘要化:返回时不展开 draft_jd 字段(模板不直接生成 JD)。
        items.append(
            {
                "id": tpl["id"],
                "industry": tpl["industry"],
                "title": tpl["title"],
                "description": tpl["description"],
                "salary_band": tpl.get("salary_band"),
                "responsibility_count": len(tpl["responsibilities"]),
                "hard_requirement_count": len(tpl["hard_requirements"]),
                "nice_to_have_count": len(tpl["nice_to_haves"]),
                "over_spec_warnings": tpl.get("over_spec_warnings", []),
            }
        )
    industries = sorted({t["industry"] for t in _TEMPLATES})
    return {"templates": items, "total": len(items), "industries": industries}


@router.get("/{template_id}")
async def get_jd_template(template_id: str) -> Dict[str, Any]:
    """返回单个模板的全部字段(用于在编辑器里展开)."""
    for tpl in _TEMPLATES:
        if tpl["id"] == template_id:
            return {"template": tpl}
    raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")


@router.get("/industries/all")
async def list_industries() -> Dict[str, Any]:
    """单独的 helper — 返回模板涵盖的行业列表."""
    return {
        "industries": sorted({t["industry"] for t in _TEMPLATES}),
    }
