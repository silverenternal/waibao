"""T6105 — Hard-condition matching engine.

甲方合同匹配因素分级 (v11.0):
  * 技能 + 岗位职责         → 硬条件 (必须满足)
  * 学历 + 证书             → 硬条件 (必须满足)
  * 薪资 + 城市 + 工作时间  → 高优先级 (打分, 不淘汰)
  * 到岗时间 + 求职意愿     → 高优先级 (打分, 不淘汰)
  * 工作 / 行业经历         → 不使用

甲方要求: **不淘汰, 只排序** —— 所有人保留, 按综合匹配度排序输出.
所以这里的 "硬条件" 不是过滤器, 而是 0-1 的达标判定 + 显著的权重影响
(全部达标 → 高分; 有缺口 → 分数降低 + 在 skill_gaps / risks 里明确标出).

输出 :class:`MatchResult` 包含:
  * match_score   0-100
  * match_reasons []string  为什么匹配 (高优先级命中)
  * skill_gaps    []string  技能/学历/证书缺口
  * risks         []string  风险提示 (到岗不确定 / 薪资期望偏高等)
  * hard_conditions  各硬条件达标明细
  * high_priority    各高优先级维度得分明细

设计原则: 纯函数式 + 无外部依赖, 输入是普通的 dict / dataclass,
方便单测; 引擎层 (:mod:`matching.engine`) 负责把它接到 DB.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger("recruittech.matching.hard_filter")

# ---------------------------------------------------------------------------
# 权重: 硬条件占大头 (达标才有高分), 高优先级维度均分剩余权重.
# 总和 = 1.0. 这些是 *贡献系数*, 与达标率相乘.
# ---------------------------------------------------------------------------

# 硬条件 (达标贡献)
W_SKILL = 0.40
W_EDUCATION = 0.15
W_CERTIFICATE = 0.10
HARD_TOTAL = W_SKILL + W_EDUCATION + W_CERTIFICATE  # 0.65

# 高优先级 (软评分)
W_SALARY_CITY = 0.20
W_AVAILABILITY = 0.15
SOFT_TOTAL = W_SALARY_CITY + W_AVAILABILITY  # 0.35

assert abs(HARD_TOTAL + SOFT_TOTAL - 1.0) < 1e-9, "权重必须归一"

# 学历顺序: 越大越高
EDUCATION_ORDER: dict[str, int] = {
    "初中": 1,
    "高中": 2,
    "中专": 2,
    "大专": 3,
    "本科": 4,
    "学士": 4,
    "硕士": 5,
    "研究生": 5,
    "博士": 6,
    "phd": 6,
    "master": 5,
    "bachelor": 4,
    "associate": 3,
}

# 工作时间偏好关键词 → 是否接受
REMOTE_OK_TOKENS = {"remote", "远程", "不限地点", "anywhere"}


# ---------------------------------------------------------------------------
# 数据形状 (纯 dict 友好, 方便从 DB row / Pydantic 直接喂进来)
# ---------------------------------------------------------------------------

@dataclass
class HardConditionResult:
    """单个硬条件的达标判定."""

    name: str  # skill | education | certificate
    satisfied: bool  # 是否完全达标
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchResult:
    """HardConditionFilter 的输出 (不淘汰, 只排序)."""

    match_score: int  # 0-100
    match_reasons: list[str]
    skill_gaps: list[str]
    risks: list[str]
    hard_conditions: dict[str, HardConditionResult]
    high_priority: dict[str, float]
    passed_hard: bool  # 所有硬条件是否达标 (用于排序优先级)
    candidate_id: Optional[str] = None  # 引擎填充, 供上游关联展示
    role_id: Optional[str] = None  # 引擎填充

    def to_dict(self) -> dict[str, Any]:
        """序列化成可 JSON / 可存 DB 的 dict."""
        return {
            "match_score": self.match_score,
            "match_reasons": list(self.match_reasons),
            "skill_gaps": list(self.skill_gaps),
            "risks": list(self.risks),
            "candidate_id": self.candidate_id,
            "role_id": self.role_id,
            "hard_conditions": {
                k: {
                    "name": v.name,
                    "satisfied": v.satisfied,
                    "detail": v.detail,
                }
                for k, v in self.hard_conditions.items()
            },
            "high_priority": dict(self.high_priority),
            "passed_hard": self.passed_hard,
        }


# ---------------------------------------------------------------------------
# 规范化辅助
# ---------------------------------------------------------------------------

def _norm_skill(name: Any) -> str:
    if name is None:
        return ""
    if isinstance(name, dict):
        name = name.get("name") or name.get("skill") or ""
    return str(name).strip().lower()


def _as_skill_list(raw: Any) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    if isinstance(raw, (list, tuple)):
        for s in raw:
            n = _norm_skill(s)
            if n:
                out.append(n)
    elif isinstance(raw, str):
        for part in raw.replace(";", ",").split(","):
            n = _norm_skill(part)
            if n:
                out.append(n)
    return out


def _education_level(val: Any) -> int:
    if val is None:
        return 0
    key = str(val).strip().lower()
    if not key:
        return 0
    # 直接命中
    if key in EDUCATION_ORDER:
        return EDUCATION_ORDER[key]
    # 子串命中 (e.g. "计算机本科" → "本科")
    for token, level in EDUCATION_ORDER.items():
        if token in key:
            return level
    return 0


def _norm_cert(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, dict):
        val = val.get("name") or val.get("certificate") or ""
    return str(val).strip().lower()


def _as_cert_list(raw: Any) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    if isinstance(raw, (list, tuple)):
        for c in raw:
            n = _norm_cert(c)
            if n:
                out.append(n)
    elif isinstance(raw, str):
        for part in raw.replace(";", ",").split(","):
            n = _norm_cert(part)
            if n:
                out.append(n)
    return out


def _coerce_amount(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(Decimal(str(val)))
    except Exception:  # noqa: BLE001 — 输入可能脏
        return None


def _salary_in_k(amount_k: Optional[float]) -> Optional[float]:
    return amount_k


# ---------------------------------------------------------------------------
# 主过滤器
# ---------------------------------------------------------------------------

class HardConditionFilter:
    """硬条件匹配引擎.

    Usage::

        f = HardConditionFilter()
        result = f.filter(candidate, role)
        print(result.match_score, result.skill_gaps)

    ``candidate`` / ``role`` 接受 dict 或有同名属性的对象. 缺失字段按
    "无约束 / 无信息" 处理 (不因此淘汰).
    """

    def filter(self, candidate: Any, role: Any) -> MatchResult:
        c = _DictView(candidate)
        r = _DictView(role)

        reasons: list[str] = []
        gaps: list[str] = []
        risks: list[str] = []

        # --- 硬条件 1: 技能 (必须全满足) -----------------------------------
        skill_res = self._check_skills(c, r, gaps, reasons)
        # --- 硬条件 2: 学历 (必须满足) -------------------------------------
        edu_res = self._check_education(c, r, gaps, reasons)
        # --- 硬条件 3: 证书 (必须满足) -------------------------------------
        cert_res = self._check_certificates(c, r, gaps, reasons)

        hard_conditions = {
            "skill": skill_res,
            "education": edu_res,
            "certificate": cert_res,
        }
        passed_hard = all(
            h.satisfied for h in hard_conditions.values()
        )

        # --- 高优先级: 薪资 + 城市 + 工作时间 ------------------------------
        sc_score, sc_reasons, sc_risks = self._score_salary_city(c, r)
        reasons.extend(sc_reasons)
        risks.extend(sc_risks)

        # --- 高优先级: 到岗时间 + 求职意愿 --------------------------------
        av_score, av_reasons, av_risks = self._score_availability(c, r)
        reasons.extend(av_reasons)
        risks.extend(av_risks)

        high_priority = {
            "salary_city": sc_score,
            "availability": av_score,
        }

        # --- 综合分 (不淘汰: 即便有缺口也给分, 只是更低) -------------------
        # 硬条件贡献 = 达标率 × 硬权重
        hard_contrib = (
            skill_res.detail.get("ratio", 0.0) * W_SKILL
            + (1.0 if edu_res.satisfied else 0.0) * W_EDUCATION
            + (1.0 if cert_res.satisfied else 0.0) * W_CERTIFICATE
        )
        soft_contrib = sc_score * W_SALARY_CITY + av_score * W_AVAILABILITY
        overall_01 = hard_contrib + soft_contrib
        overall_01 = max(0.0, min(1.0, overall_01))
        match_score = round(overall_01 * 100)

        # 去重 (reasons / risks 可能重复生成)
        reasons = list(dict.fromkeys(reasons))
        risks = list(dict.fromkeys(risks))

        return MatchResult(
            match_score=match_score,
            match_reasons=reasons,
            skill_gaps=gaps,
            risks=risks,
            hard_conditions=hard_conditions,
            high_priority=high_priority,
            passed_hard=passed_hard,
        )

    # -- 硬条件检查 --------------------------------------------------------

    def _check_skills(
        self,
        c: "_DictView",
        r: "_DictView",
        gaps: list[str],
        reasons: list[str],
    ) -> HardConditionResult:
        required = _as_skill_list(r.get("required_skills") or r.get("skills_required"))
        candidate_skills = _as_skill_list(
            c.get("skills") or c.get("skill_list")
        )
        cset = set(candidate_skills)

        if not required:
            # 岗位无技能要求 → 视为达标 (空约束)
            return HardConditionResult(
                name="skill",
                satisfied=True,
                detail={
                    "required": [],
                    "matched": list(cset),
                    "missing": [],
                    "ratio": 1.0,
                },
            )

        matched: list[str] = []
        missing: list[str] = []
        for sk in required:
            if _skill_in(sk, cset):
                matched.append(sk)
            else:
                missing.append(sk)

        ratio = len(matched) / len(required) if required else 1.0
        satisfied = len(missing) == 0

        if satisfied:
            reasons.append(f"技能匹配 {len(matched)}/{len(required)} (全部满足)")
        else:
            for m in missing:
                gaps.append(f"缺 {m} 经验/技能")
            reasons.append(
                f"技能匹配 {len(matched)}/{len(required)} (缺 {len(missing)})"
            )

        return HardConditionResult(
            name="skill",
            satisfied=satisfied,
            detail={
                "required": required,
                "matched": matched,
                "missing": missing,
                "ratio": ratio,
            },
        )

    def _check_education(
        self,
        c: "_DictView",
        r: "_DictView",
        gaps: list[str],
        reasons: list[str],
    ) -> HardConditionResult:
        required_edu = r.get("education") or r.get("education_required")
        candidate_edu = c.get("education") or c.get("education_level")

        if required_edu is None:
            return HardConditionResult(
                name="education",
                satisfied=True,
                detail={
                    "required": None,
                    "candidate": candidate_edu,
                    "ratio": 1.0,
                },
            )

        req_level = _education_level(required_edu)
        cand_level = _education_level(candidate_edu)
        satisfied = cand_level >= req_level and cand_level > 0

        if satisfied:
            reasons.append("学历满足要求")
        else:
            gaps.append(
                f"学历要求 {required_edu}, 候选人 {candidate_edu or '未填写'}"
            )

        # 部分达标 (候选人级别未知但岗位有要求 → ratio 0; 否则按比例)
        if req_level > 0 and cand_level > 0:
            ratio = min(1.0, cand_level / req_level)
        else:
            ratio = 0.0

        return HardConditionResult(
            name="education",
            satisfied=satisfied,
            detail={
                "required": required_edu,
                "candidate": candidate_edu,
                "required_level": req_level,
                "candidate_level": cand_level,
                "ratio": ratio,
            },
        )

    def _check_certificates(
        self,
        c: "_DictView",
        r: "_DictView",
        gaps: list[str],
        reasons: list[str],
    ) -> HardConditionResult:
        required = _as_cert_list(
            r.get("certificates_required")
            or r.get("required_certificates")
            or r.get("certificates")
        )
        candidate = _as_cert_list(
            c.get("certificates") or c.get("cert_list")
        )
        cset = set(candidate)

        if not required:
            return HardConditionResult(
                name="certificate",
                satisfied=True,
                detail={
                    "required": [],
                    "matched": [],
                    "missing": [],
                    "ratio": 1.0,
                },
            )

        matched = [x for x in required if x in cset]
        missing = [x for x in required if x not in cset]
        ratio = len(matched) / len(required) if required else 1.0
        satisfied = len(missing) == 0

        if satisfied:
            if matched:
                reasons.append(f"证书齐全 ({', '.join(matched[:3])})")
        else:
            for m in missing:
                gaps.append(f"缺少证书: {m}")

        return HardConditionResult(
            name="certificate",
            satisfied=satisfied,
            detail={
                "required": required,
                "matched": matched,
                "missing": missing,
                "ratio": ratio,
            },
        )

    # -- 高优先级评分 ------------------------------------------------------

    def _score_salary_city(
        self, c: "_DictView", r: "_DictView"
    ) -> tuple[float, list[str], list[str]]:
        reasons: list[str] = []
        risks: list[str] = []

        # 薪资 (K) — 候选人期望 vs 岗位范围
        r_min = _salary_in_k(_coerce_amount(
            r.get("salary_min_k") or _amount_k(r.get("salary_band"), "min")
        ))
        r_max = _salary_in_k(_coerce_amount(
            r.get("salary_max_k") or _amount_k(r.get("salary_band"), "max")
        ))
        c_min = _salary_in_k(_coerce_amount(
            c.get("salary_min_k")
            or _amount_k(c.get("salary_expectation"), "min")
        ))
        c_max = _salary_in_k(_coerce_amount(
            c.get("salary_max_k")
            or _amount_k(c.get("salary_expectation"), "max")
        ))

        salary_score = 1.0  # 默认满 (无约束)
        if r_min is not None and r_max is not None and c_min is not None:
            # 候选人期望下限落在岗位区间内 → 满
            if c_min <= r_max:
                salary_score = 1.0
                reasons.append(f"薪资符合 ({r_min}-{r_max}K)")
            else:
                # 期望偏高: 按超出比例衰减
                over = (c_min - r_max) / max(r_max, 1.0)
                salary_score = max(0.0, 1.0 - over)
                risks.append(
                    f"薪资期望偏高 (期望 {c_min}K, 岗位上限 {r_max}K)"
                )
        elif c_min is not None and r_max is not None and c_min > r_max:
            over = (c_min - r_max) / max(r_max, 1.0)
            salary_score = max(0.0, 1.0 - over)
            risks.append(f"薪资期望偏高 (期望 {c_min}K, 岗位上限 {r_max}K)")

        # 城市
        r_city = (r.get("city") or r.get("location") or "").strip().lower()
        c_city = (c.get("city") or c.get("location") or "").strip().lower()
        city_score = 1.0
        if r_city and c_city:
            if r_city == c_city:
                city_score = 1.0
                reasons.append(f"同城 ({c.get('city')})")
            elif _is_remote(r_city) or _is_remote(c_city):
                city_score = 0.9
                reasons.append("接受远程/异地")
            else:
                city_score = 0.3
                risks.append(f"城市不符 (候选人 {c.get('city')}, 岗位 {r.get('city')})")

        # 工作时间 / 远程政策
        r_remote = (r.get("remote_policy") or r.get("work_time") or "").strip().lower()
        c_remote = (c.get("remote_policy") or c.get("work_time") or "").strip().lower()
        work_score = 1.0
        if r_remote and c_remote and r_remote != c_remote:
            # 简单: 完全一致满, 否则 0.6
            work_score = 0.6

        # 三者平均作为本维度得分
        score = (salary_score + city_score + work_score) / 3.0
        return round(score, 4), reasons, risks

    def _score_availability(
        self, c: "_DictView", r: "_DictView"
    ) -> tuple[float, list[str], list[str]]:
        reasons: list[str] = []
        risks: list[str] = []

        # 到岗时间
        r_avail = (r.get("availability_required") or "").strip().lower()
        c_avail = (
            c.get("availability")
            or c.get("availability_status")
            or ""
        )
        c_avail_s = str(c_avail).strip().lower()

        avail_score = 1.0
        if r_avail:
            # 立即/1月/3月 排序
            order = {"immediate": 1, "立即": 1, "立即上岗": 1,
                     "1_month": 2, "1月": 2, "一个月": 2,
                     "3_months": 3, "3月": 3, "三个月": 3,
                     "not_looking": 9, "在职看机会": 2, "离职可立即上岗": 1}
            r_rank = order.get(r_avail, 0)
            c_rank = order.get(c_avail_s, 0)
            if c_rank == 0:
                avail_score = 0.5
                risks.append("到岗时间不确定")
            elif c_rank <= r_rank or r_rank == 0:
                avail_score = 1.0
                reasons.append("到岗时间满足")
            elif c_rank <= r_rank + 1:
                avail_score = 0.7
                risks.append("到岗时间略晚于预期")
            else:
                avail_score = 0.3
                risks.append("到岗时间不满足岗位要求")
        elif c_avail_s:
            # 岗位无明确到岗要求, 但候选人有状态
            if c_avail_s in {"立即", "立即上岗", "immediate", "离职可立即上岗"}:
                reasons.append("可立即上岗")
            elif c_avail_s in {"not_looking", "在职看机会"}:
                avail_score = 0.8

        # 求职意愿
        intent = (c.get("job_intent") or c.get("intent") or "").strip().lower()
        intent_score = 1.0
        if intent:
            if intent in {"active", "积极", "强烈", "非常想"}:
                intent_score = 1.0
                reasons.append("求职意愿强烈")
            elif intent in {"passive", "观望", "一般"}:
                intent_score = 0.6
                risks.append("求职意愿一般 (被动观望)")
            elif intent in {"none", "无", "不考虑"}:
                intent_score = 0.2
                risks.append("求职意愿低")

        score = (avail_score + intent_score) / 2.0
        return round(score, 4), reasons, risks


# ---------------------------------------------------------------------------
# 工具: dict / 属性统一视图
# ---------------------------------------------------------------------------

class _DictView:
    """把 dict 或有属性的对象统一成 .get() 接口."""

    def __init__(self, obj: Any) -> None:
        self._obj = obj

    def get(self, key: str, default: Any = None) -> Any:
        obj = self._obj
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        # dataclass / pydantic / 普通对象
        return getattr(obj, key, default)


def _skill_in(skill: str, cset: set[str]) -> bool:
    if skill in cset:
        return True
    # 别名 / 子串容错
    aliases = {
        "javascript": {"js", "ecmascript"},
        "typescript": {"ts"},
        "python": {"py"},
        "react": {"reactjs", "react.js"},
        "node": {"nodejs", "node.js"},
        "postgresql": {"postgres", "psql"},
        "kubernetes": {"k8s"},
        "amazon web services": {"aws"},
        "google cloud platform": {"gcp"},
        "machine learning": {"ml"},
        "docker": {"containerization"},
    }
    canon = skill
    for k, al in aliases.items():
        if skill in al or skill == k:
            canon = k
            if cset & ({k} | al):
                return True
    # 子串兜底
    for s in cset:
        if skill and (skill in s or s in skill):
            return True
    return False


def _amount_k(salary_obj: Any, key: str) -> Optional[float]:
    """从 salary_band / salary_expectation dict 里取金额."""
    if not isinstance(salary_obj, dict):
        return None
    val = salary_obj.get(f"{key}_amount")
    if val is None:
        val = salary_obj.get(f"{key}_k")
    return _coerce_amount(val)


def _is_remote(token: str) -> bool:
    return any(t in token for t in REMOTE_OK_TOKENS)
