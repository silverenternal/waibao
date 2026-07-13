"""v8.1 T3602 — 行业垂直的日报评价服务.

需求 1.2: 行业垂直评价 + 行动项追踪

按 10 种主流职业角色分别定制评价维度 (后端 / AI产品 / 运营 / 设计 /
销售 / HR / 财务 / 法务 / 管理 / 教师),每种角色:

    * 评分维度 (0-10)
    * 优势 / 改进 / 风险
    * 可执行性 1-5

暴露两个对外 API:
    - evaluate(text, role, context) -> Evaluation
    - extract_action_items(evaluation, role) -> list[ActionItem]
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("recruittech.services.jobseeker.journal_evaluator")


# ---------------------------------------------------------------------------
# 角色定义
# ---------------------------------------------------------------------------
class IndustryRole(str, Enum):
    BACKEND = "backend"
    AI_PRODUCT = "ai_product"
    OPERATIONS = "operations"
    DESIGN = "design"
    SALES = "sales"
    HR = "hr"
    FINANCE = "finance"
    LEGAL = "legal"
    MANAGEMENT = "management"
    TEACHER = "teacher"


ROLE_DISPLAY = {
    IndustryRole.BACKEND.value: "后端工程师",
    IndustryRole.AI_PRODUCT.value: "AI 产品经理",
    IndustryRole.OPERATIONS.value: "运营",
    IndustryRole.DESIGN.value: "设计师",
    IndustryRole.SALES.value: "销售",
    IndustryRole.HR.value: "HR",
    IndustryRole.FINANCE.value: "财务",
    IndustryRole.LEGAL.value: "法务",
    IndustryRole.MANAGEMENT.value: "管理者",
    IndustryRole.TEACHER.value: "教师",
}


# 每个角色: 评价维度 + 评价 prompt 注入
ROLE_DIMENSIONS: Dict[str, Dict[str, Any]] = {
    IndustryRole.BACKEND.value: {
        "dimensions": [
            "code_quality",
            "system_design",
            "performance",
            "reliability",
            "tech_debt",
        ],
        "weight": {
            "code_quality": 0.25,
            "system_design": 0.25,
            "performance": 0.20,
            "reliability": 0.20,
            "tech_debt": 0.10,
        },
        "look_for": [
            "单元测试覆盖率",
            "接口设计",
            "性能瓶颈",
            "监控告警",
            "技术债",
        ],
    },
    IndustryRole.AI_PRODUCT.value: {
        "dimensions": [
            "user_research",
            "prd_quality",
            "experiment_design",
            "data_driven",
            "cross_team",
        ],
        "weight": {
            "user_research": 0.30,
            "prd_quality": 0.25,
            "experiment_design": 0.20,
            "data_driven": 0.15,
            "cross_team": 0.10,
        },
        "look_for": [
            "用户访谈",
            "PRD 结构",
            "A/B 实验",
            "北极星指标",
            "跨团队协作",
        ],
    },
    IndustryRole.OPERATIONS.value: {
        "dimensions": [
            "growth",
            "retention",
            "funnel",
            "content",
            "experiments",
        ],
        "weight": {
            "growth": 0.30,
            "retention": 0.25,
            "funnel": 0.20,
            "content": 0.15,
            "experiments": 0.10,
        },
        "look_for": [
            "拉新",
            "留存",
            "转化漏斗",
            "内容质量",
            "活动复盘",
        ],
    },
    IndustryRole.DESIGN.value: {
        "dimensions": [
            "visual",
            "interaction",
            "consistency",
            "accessibility",
            "business_value",
        ],
        "weight": {
            "visual": 0.20,
            "interaction": 0.25,
            "consistency": 0.20,
            "accessibility": 0.15,
            "business_value": 0.20,
        },
        "look_for": [
            "视觉层级",
            "交互流畅度",
            "设计系统",
            "无障碍",
            "业务指标",
        ],
    },
    IndustryRole.SALES.value: {
        "dimensions": [
            "pipeline",
            "win_rate",
            "relationship",
            "negotiation",
            "forecast",
        ],
        "weight": {
            "pipeline": 0.25,
            "win_rate": 0.25,
            "relationship": 0.20,
            "negotiation": 0.20,
            "forecast": 0.10,
        },
        "look_for": [
            "商机",
            "成交率",
            "客户关系",
            "议价",
            "预测准确度",
        ],
    },
    IndustryRole.HR.value: {
        "dimensions": [
            "recruiting",
            "employee_care",
            "policy",
            "compliance",
            "data_driven",
        ],
        "weight": {
            "recruiting": 0.30,
            "employee_care": 0.20,
            "policy": 0.15,
            "compliance": 0.20,
            "data_driven": 0.15,
        },
        "look_for": [
            "招聘漏斗",
            "员工体验",
            "制度",
            "合规",
            "人效",
        ],
    },
    IndustryRole.FINANCE.value: {
        "dimensions": [
            "accuracy",
            "compliance",
            "analysis",
            "forecasting",
            "controls",
        ],
        "weight": {
            "accuracy": 0.30,
            "compliance": 0.20,
            "analysis": 0.20,
            "forecasting": 0.20,
            "controls": 0.10,
        },
        "look_for": [
            "账实相符",
            "税务合规",
            "财务分析",
            "预算",
            "内控",
        ],
    },
    IndustryRole.LEGAL.value: {
        "dimensions": [
            "risk_assessment",
            "compliance",
            "drafting",
            "negotiation",
            "case_handling",
        ],
        "weight": {
            "risk_assessment": 0.25,
            "compliance": 0.25,
            "drafting": 0.20,
            "negotiation": 0.15,
            "case_handling": 0.15,
        },
        "look_for": [
            "法律风险",
            "合规",
            "合同审阅",
            "商务谈判",
            "诉讼",
        ],
    },
    IndustryRole.MANAGEMENT.value: {
        "dimensions": [
            "strategy",
            "execution",
            "people",
            "communication",
            "decision_making",
        ],
        "weight": {
            "strategy": 0.25,
            "execution": 0.25,
            "people": 0.20,
            "communication": 0.15,
            "decision_making": 0.15,
        },
        "look_for": [
            "战略清晰度",
            "OKR 进度",
            "团队培养",
            "跨部门沟通",
            "决策质量",
        ],
    },
    IndustryRole.TEACHER.value: {
        "dimensions": [
            "lesson_design",
            "engagement",
            "feedback",
            "assessment",
            "growth",
        ],
        "weight": {
            "lesson_design": 0.25,
            "engagement": 0.25,
            "feedback": 0.20,
            "assessment": 0.15,
            "growth": 0.15,
        },
        "look_for": [
            "教学设计",
            "课堂互动",
            "作业反馈",
            "学习评估",
            "教师成长",
        ],
    },
}


# ---------------------------------------------------------------------------
# 评价 prompt (按角色拼装)
# ---------------------------------------------------------------------------
def build_prompt(role: str, text: str) -> str:
    cfg = ROLE_DIMENSIONS.get(role)
    if not cfg:
        return _generic_prompt(text)
    dims = ", ".join(cfg["dimensions"])
    look_for = "、".join(cfg["look_for"])
    return f"""你是 {ROLE_DISPLAY.get(role, role)} 行业的资深教练。

今天的日报:
\"\"\"{text}\"\"\"

请按角色维度评分 ({dims}),重点关注: {look_for}

输出 JSON:
{{
  "score": 0-10,
  "dimension_scores": {{ "维度1": 0-10, ... }},
  "strengths": ["..."],
  "improvements": ["..."],
  "risks": ["..."],
  "action_items": [{{
    "title": "明天可做的事",
    "detail": "具体步骤",
    "feasibility": 1-5
  }}]
}}
"""


def _generic_prompt(text: str) -> str:
    return f"""你是求职者的工作教练。

今天的日报:
\"\"\"{text}\"\"\"

输出 JSON:
{{
  "score": 0-10,
  "dimension_scores": {{}},
  "strengths": ["..."],
  "improvements": ["..."],
  "risks": ["..."],
  "action_items": [{{
    "title": "...",
    "detail": "...",
    "feasibility": 1-5
  }}]
}}
"""


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ActionItem:
    """行动项 (v2 状态机)."""

    id: str
    user_id: str
    title: str
    detail: str = ""
    role: str = ""
    status: str = "pending"  # pending / in_progress / done / abandoned
    feasibility: int = 3  # 1-5
    quality_score: Optional[float] = None  # 完成质量
    created_at: str = ""
    due_date: Optional[str] = None
    completed_at: Optional[str] = None
    reminder_sent: bool = False
    plan_item_title: Optional[str] = None  # T3606 关联

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Evaluation:
    """一次评价的产出."""

    role: str
    score: float
    dimension_scores: Dict[str, float]
    strengths: List[str]
    improvements: List[str]
    risks: List[str]
    action_items: List[ActionItem]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["action_items"] = [a.to_dict() for a in self.action_items]
        return d


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------
class JournalEvaluatorService:
    """行业垂直的日报评价器 (无 LLM 依赖,纯启发式,deterministic).

    真正的 LLM 调用留给 daily_journal_agent;这个服务是"前置规范化 + 评分
    + 行动项 状态机"层。任何能产生 {score, dimension_scores, ...} 字典
    的上游都可以喂进来。
    """

    def __init__(self) -> None:
        self._items: Dict[str, ActionItem] = {}
        self._user_items: Dict[str, List[str]] = {}
        self._evaluations: List[Evaluation] = []

    # ----------------- 评价 -----------------
    def evaluate(
        self,
        text: str,
        role: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        parsed: Optional[Dict[str, Any]] = None,
    ) -> Evaluation:
        """根据上游 LLM 输出 (parsed) 或文本启发式,生成 Evaluation."""
        if parsed and isinstance(parsed, dict):
            score = float(parsed.get("score", 6.0))
            dim_scores = {
                k: float(v) for k, v in (parsed.get("dimension_scores") or {}).items()
            }
            strengths = list(parsed.get("strengths") or [])
            improvements = list(parsed.get("improvements") or [])
            risks = list(parsed.get("risks") or [])
            raw_items = parsed.get("action_items") or []
        else:
            score, dim_scores, strengths, improvements, risks, raw_items = (
                self._heuristic(text, role)
            )

        # 构造 ActionItem
        action_items = self._persist_action_items(
            user_id=(context or {}).get("user_id", ""),
            role=role,
            raw_items=raw_items,
        )

        ev = Evaluation(
            role=role,
            score=score,
            dimension_scores=dim_scores,
            strengths=strengths,
            improvements=improvements,
            risks=risks,
            action_items=action_items,
        )
        self._evaluations.append(ev)
        return ev

    def list_evaluations(self, role: Optional[str] = None) -> List[Evaluation]:
        return [e for e in self._evaluations if not role or e.role == role]

    # ----------------- Action Items -----------------
    def list_action_items(
        self,
        user_id: str,
        *,
        status: Optional[str] = None,
        role: Optional[str] = None,
    ) -> List[ActionItem]:
        ids = self._user_items.get(user_id, [])
        items = [self._items[i] for i in ids if i in self._items]
        if status:
            items = [i for i in items if i.status == status]
        if role:
            items = [i for i in items if i.role == role]
        return items

    def update_action_item(
        self,
        item_id: str,
        *,
        status: Optional[str] = None,
        quality_score: Optional[float] = None,
        due_date: Optional[str] = None,
    ) -> ActionItem:
        item = self._items.get(item_id)
        if not item:
            raise KeyError(item_id)
        if status:
            valid = {"pending", "in_progress", "done", "abandoned"}
            if status not in valid:
                raise ValueError(f"invalid status: {status}")
            item.status = status
            if status == "done":
                item.completed_at = datetime.now(timezone.utc).isoformat()
        if quality_score is not None:
            try:
                item.quality_score = float(quality_score)
            except (TypeError, ValueError):
                pass
        if due_date is not None:
            item.due_date = due_date
        return item

    def rating_trend(self, user_id: str, *, days: int = 30) -> List[Dict[str, Any]]:
        """返回用户最近 days 天的评分趋势 (按 evaluation 时间倒序)."""
        out: List[Dict[str, Any]] = []
        for ev in reversed(self._evaluations):
            out.append({
                "created_at": ev.created_at,
                "role": ev.role,
                "score": ev.score,
            })
        return out[:days]

    def mark_reminder_sent(self, item_id: str) -> None:
        item = self._items.get(item_id)
        if item:
            item.reminder_sent = True

    def due_items(self, *, hours: int = 24) -> List[ActionItem]:
        """即将到期 (未来 hours 小时内) 且 未完成 的 action items."""
        from datetime import datetime

        now = datetime.now(timezone.utc)
        horizon = now + timedelta(hours=hours)
        out: List[ActionItem] = []
        for it in self._items.values():
            if it.status in ("done", "abandoned"):
                continue
            if not it.due_date:
                continue
            try:
                due = datetime.fromisoformat(it.due_date.replace("Z", "+00:00"))
            except ValueError:
                continue
            if due <= horizon and not it.reminder_sent:
                out.append(it)
        return out

    # ----------------- 关联 (T3606) -----------------
    def link_to_plan(self, item_id: str, plan_item_title: str) -> ActionItem:
        item = self._items.get(item_id)
        if not item:
            raise KeyError(item_id)
        item.plan_item_title = plan_item_title
        return item

    # ----------------- 内部 -----------------
    def _persist_action_items(
        self,
        *,
        user_id: str,
        role: str,
        raw_items: List[Any],
    ) -> List[ActionItem]:
        out: List[ActionItem] = []
        for raw in raw_items or []:
            if isinstance(raw, str):
                title, detail, feas = raw, "", 3
            elif isinstance(raw, dict):
                title = raw.get("title") or raw.get("text") or "(无标题)"
                detail = raw.get("detail", "")
                try:
                    feas = int(raw.get("feasibility", 3))
                except (TypeError, ValueError):
                    feas = 3
                feas = max(1, min(5, feas))
            else:
                continue
            from uuid import uuid4

            item = ActionItem(
                id=str(uuid4()),
                user_id=user_id,
                title=str(title)[:200],
                detail=str(detail)[:1000],
                role=role,
                feasibility=feas,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._items[item.id] = item
            self._user_items.setdefault(user_id, []).append(item.id)
            out.append(item)
        return out

    def _heuristic(self, text: str, role: str) -> tuple:
        """极简启发式 — 给个保底评分,主要用于单测."""
        n = max(1, len(text))
        # 文本越长越倾向"good"
        if n > 200:
            score = 7.5
            strengths = ["内容详尽"]
            improvements = ["下一步:拆解到具体可执行项"]
            risks = []
        elif n > 50:
            score = 6.0
            strengths = ["按时提交"]
            improvements = ["补充数据 / 量化结果"]
            risks = []
        else:
            score = 4.5
            strengths = []
            improvements = ["建议更详细描述当天工作"]
            risks = ["内容过少可能错过关键信号"]
        cfg = ROLE_DIMENSIONS.get(role, {})
        dim_scores = {d: score for d in cfg.get("dimensions", [])}
        raw_items = [{"title": "继续推进今天的核心任务", "feasibility": 4}]
        return score, dim_scores, strengths, improvements, risks, raw_items


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_singleton: Optional[JournalEvaluatorService] = None


def get_journal_evaluator() -> JournalEvaluatorService:
    global _singleton
    if _singleton is None:
        _singleton = JournalEvaluatorService()
    return _singleton


def reset_journal_evaluator() -> None:
    global _singleton
    _singleton = None