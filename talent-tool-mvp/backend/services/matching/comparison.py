"""T2301 — 候选人/岗位对比服务.

提供多维度对齐的对比能力:
- 5 个评分维度对齐 (skill/experience/education/culture/potential)
- 自动计算差异最大的 top-3 维度 (highlight)
- 支持候选人 vs 候选人、岗位 vs 岗位 两种模式
- 可序列化为 saved_comparisons 快照
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Iterable, Optional
from uuid import UUID, uuid4

logger = logging.getLogger("recruittech.services.comparison")


# ---------------------------------------------------------------------------
# 5 维度定义
# ---------------------------------------------------------------------------

COMPARISON_DIMENSIONS: tuple[str, ...] = (
    "skill",
    "experience",
    "education",
    "culture",
    "potential",
)

DIMENSION_LABELS: dict[str, str] = {
    "skill": "技能匹配",
    "experience": "经验匹配",
    "education": "教育背景",
    "culture": "文化契合",
    "potential": "发展潜力",
}


@dataclass
class DimensionScore:
    dimension: str
    score: float  # 0..100
    label: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.label:
            self.label = DIMENSION_LABELS.get(self.dimension, self.dimension)


@dataclass
class CompareItem:
    id: str
    name: str
    type: str  # 'candidate' | 'role'
    dimensions: dict[str, DimensionScore] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)
    overall_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "dimensions": {k: asdict(v) for k, v in self.dimensions.items()},
            "attributes": self.attributes,
            "overall_score": self.overall_score,
        }


@dataclass
class DiffDimension:
    dimension: str
    label: str
    spread: float  # max - min
    stddev: float
    values: list[float]
    items: list[str]  # ids
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "label": self.label,
            "spread": round(self.spread, 2),
            "stddev": round(self.stddev, 2),
            "values": [round(v, 2) for v in self.values],
            "items": self.items,
            "rank": self.rank,
        }


@dataclass
class DiffResult:
    items: list[CompareItem]
    diff_dimensions: list[DiffDimension]
    highlights: list[DiffDimension]  # top-3 spread
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "diff_dimensions": [d.to_dict() for d in self.diff_dimensions],
            "highlights": [h.to_dict() for h in self.highlights],
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# 差异计算
# ---------------------------------------------------------------------------


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return var ** 0.5


def compute_diff(
    items: list[CompareItem],
    top_n: int = 3,
) -> DiffResult:
    """计算 5 维度对齐的差异结果.

    Args:
        items: 至少 2 个,最多 5 个 CompareItem
        top_n: 高亮 top-N (默认 3)

    Returns:
        DiffResult: 包含完整对齐结果 + 高亮维度
    """
    if len(items) < 2:
        raise ValueError("需要至少 2 个对比项")
    if len(items) > 5:
        raise ValueError("最多支持 5 个对比项")

    diffs: list[DiffDimension] = []
    for dim in COMPARISON_DIMENSIONS:
        values: list[float] = []
        ids: list[str] = []
        for item in items:
            score = item.dimensions.get(dim)
            if score is None:
                # 缺失维度填 0,保持对齐
                values.append(0.0)
            else:
                values.append(float(score.score))
            ids.append(item.id)

        spread = max(values) - min(values)
        stddev = _stdev(values)
        diffs.append(
            DiffDimension(
                dimension=dim,
                label=DIMENSION_LABELS[dim],
                spread=spread,
                stddev=stddev,
                values=values,
                items=ids,
            )
        )

    # 按 spread 降序
    diffs.sort(key=lambda d: (-d.spread, -d.stddev))
    for rank, d in enumerate(diffs, start=1):
        d.rank = rank

    highlights = diffs[:top_n]

    return DiffResult(
        items=list(items),
        diff_dimensions=diffs,
        highlights=highlights,
    )


# ---------------------------------------------------------------------------
# 从 supabase 行构造 CompareItem
# ---------------------------------------------------------------------------


def _candidate_dimensions_from_match(
    candidate: dict[str, Any],
    role: dict[str, Any] | None,
    match_row: dict[str, Any] | None,
) -> dict[str, DimensionScore]:
    """从候选人 + role + match 派生 5 维度.

    若 match_row 存在,使用其 scoring_breakdown;否则从候选人自身估算.
    """
    breakdown = (match_row or {}).get("scoring_breakdown") or {}

    # Skill: 优先取 skill_overlap 比例
    skill_overlap = (match_row or {}).get("skill_overlap") or []
    if isinstance(skill_overlap, list) and skill_overlap:
        matched = sum(1 for s in skill_overlap if isinstance(s, dict) and s.get("matched"))
        skill_score = round(matched / len(skill_overlap) * 100, 1)
    else:
        skill_score = float(breakdown.get("skill", 0)) * 100

    # Experience
    exp_score = float(breakdown.get("experience", 0)) * 100
    if not exp_score and role:
        # 估算:候选人经验年限 vs 岗位要求
        candidate_years = candidate.get("experience_years") or 0
        required_years = role.get("min_experience_years") or 0
        if required_years <= 0:
            exp_score = 70.0
        else:
            ratio = min(candidate_years / max(required_years, 1), 1.0)
            exp_score = round(ratio * 100, 1)
    if not exp_score:
        # 完全没有信息 → 默认中性 70
        exp_score = 70.0

    # Education: 简化 — 有教育背景视为 80,否则 50
    education = candidate.get("education") or []
    edu_score = 80.0 if education else 50.0

    # Culture: 从 assessment 取
    culture = float(breakdown.get("culture", 0)) * 100
    if not culture:
        culture = 65.0  # 默认中性

    # Potential: 从候选人潜力信号 (tags 中 potential_high 等)
    tags = candidate.get("tags") or []
    potential = 70.0
    if any(t in {"potential_high", "high_potential", "fast_grower"} for t in tags):
        potential = 90.0
    elif any(t in {"potential_low", "lateral"} for t in tags):
        potential = 45.0

    return {
        "skill": DimensionScore("skill", skill_score),
        "experience": DimensionScore("experience", exp_score),
        "education": DimensionScore("education", edu_score),
        "culture": DimensionScore("culture", culture),
        "potential": DimensionScore("potential", potential),
    }


def _role_dimensions(
    role: dict[str, Any],
    candidates: list[dict[str, Any]] | None = None,
    matches: list[dict[str, Any]] | None = None,
) -> dict[str, DimensionScore]:
    """岗位的 5 维度:
    - skill: 技能要求广度 / 必备技能数量
    - experience: 经验要求
    - education: 学历要求
    - culture: 团队文化指标 (从 role metadata)
    - potential: 岗位发展潜力
    """
    required = role.get("required_skills") or []
    nice = role.get("nice_to_have_skills") or []
    skill_score = min(100.0, (len(required) + len(nice) * 0.5) * 8 + 20)

    min_years = role.get("min_experience_years") or 0
    exp_score = min(100.0, min_years * 8 + 20)

    seniority = (role.get("seniority") or "").lower()
    edu_map = {"junior": 50, "mid": 70, "senior": 80, "lead": 85, "principal": 90, "staff": 90}
    edu_score = float(edu_map.get(seniority, 60))

    culture_meta = role.get("culture") or {}
    if isinstance(culture_meta, dict):
        culture_score = float(culture_meta.get("score", 65))
    else:
        culture_score = 65.0

    # Potential: 高级别岗位 + 高匹配候选人 → 高潜力
    potential = 70.0
    if seniority in {"senior", "lead", "principal", "staff"}:
        potential += 15
    if matches:
        avg = sum(float(m.get("overall_score", 0)) for m in matches) / max(len(matches), 1)
        if avg > 0.7:
            potential += 10

    return {
        "skill": DimensionScore("skill", skill_score),
        "experience": DimensionScore("experience", exp_score),
        "education": DimensionScore("education", edu_score),
        "culture": DimensionScore("culture", culture_score),
        "potential": DimensionScore("potential", min(100.0, potential)),
    }


def build_candidate_items(
    candidates: list[dict[str, Any]],
    roles: dict[str, dict[str, Any]] | None = None,
    matches_by_candidate: dict[str, dict[str, Any]] | None = None,
) -> list[CompareItem]:
    """构造候选人 CompareItem 列表.

    Args:
        candidates: candidate 行列表
        roles: role_id -> role 行 (用于经验匹配)
        matches_by_candidate: candidate_id -> match 行
    """
    items: list[CompareItem] = []
    for c in candidates:
        cid = str(c.get("id"))
        match = (matches_by_candidate or {}).get(cid)
        role = None
        if match and roles:
            role = roles.get(str(match.get("role_id")))
        elif roles and len(roles) == 1:
            role = next(iter(roles.values()))

        dims = _candidate_dimensions_from_match(c, role, match)
        overall = float(match.get("overall_score", 0)) * 100 if match else 0.0

        items.append(
            CompareItem(
                id=cid,
                name=c.get("name") or c.get("full_name") or "未知",
                type="candidate",
                dimensions=dims,
                attributes={
                    "headline": c.get("headline") or "",
                    "location": c.get("location") or "",
                    "experience_years": c.get("experience_years"),
                    "tags": c.get("tags") or [],
                },
                overall_score=round(overall, 1),
            )
        )
    return items


def build_role_items(
    roles: list[dict[str, Any]],
    candidates_by_role: dict[str, list[dict[str, Any]]] | None = None,
    matches_by_role: dict[str, list[dict[str, Any]]] | None = None,
) -> list[CompareItem]:
    """构造岗位 CompareItem 列表."""
    items: list[CompareItem] = []
    for r in roles:
        rid = str(r.get("id"))
        cands = (candidates_by_role or {}).get(rid)
        matches = (matches_by_role or {}).get(rid)
        dims = _role_dimensions(r, cands, matches)
        overall = 0.0
        if matches:
            overall = sum(float(m.get("overall_score", 0)) for m in matches) / len(matches) * 100

        items.append(
            CompareItem(
                id=rid,
                name=r.get("title") or "未命名岗位",
                type="role",
                dimensions=dims,
                attributes={
                    "seniority": r.get("seniority"),
                    "location": r.get("location"),
                    "remote_policy": r.get("remote_policy"),
                    "salary_range": r.get("salary_range"),
                },
                overall_score=round(overall, 1),
            )
        )
    return items


# ---------------------------------------------------------------------------
# 服务类 (高层封装)
# ---------------------------------------------------------------------------


class ComparisonService:
    """对比服务 - 包装 supabase 数据访问."""

    def __init__(self, supabase):
        self.supabase = supabase

    async def compare_candidates(
        self,
        candidate_ids: list[UUID],
        role_id: UUID | None = None,
    ) -> DiffResult:
        """对比候选人."""
        if len(candidate_ids) < 2:
            raise ValueError("至少需要 2 个候选人")
        if len(candidate_ids) > 5:
            raise ValueError("最多 5 个候选人")

        str_ids = [str(c) for c in candidate_ids]
        result = (
            self.supabase.table("candidates")
            .select("*")
            .in_("id", str_ids)
            .execute()
        )
        candidates = result.data or []
        if len(candidates) != len(candidate_ids):
            found = {c["id"] for c in candidates}
            missing = [i for i in str_ids if i not in found]
            raise ValueError(f"候选人未找到: {missing}")

        roles: dict[str, dict[str, Any]] = {}
        matches_by_cand: dict[str, dict[str, Any]] = {}
        if role_id:
            r = (
                self.supabase.table("roles")
                .select("*")
                .eq("id", str(role_id))
                .single()
                .execute()
            )
            if r.data:
                roles[str(role_id)] = r.data
            m = (
                self.supabase.table("matches")
                .select("*")
                .eq("role_id", str(role_id))
                .in_("candidate_id", str_ids)
                .execute()
            )
            for row in m.data or []:
                matches_by_cand[str(row["candidate_id"])] = row
        else:
            # 取每个候选人最近一次 match
            m = (
                self.supabase.table("matches")
                .select("*")
                .in_("candidate_id", str_ids)
                .order("created_at", desc=True)
                .execute()
            )
            for row in m.data or []:
                cid = str(row["candidate_id"])
                if cid not in matches_by_cand:
                    matches_by_cand[cid] = row
            # 加载对应的 roles
            role_ids = {str(row["role_id"]) for row in m.data or []}
            if role_ids:
                rs = (
                    self.supabase.table("roles")
                    .select("*")
                    .in_("id", list(role_ids))
                    .execute()
                )
                for r in rs.data or []:
                    roles[str(r["id"])] = r

        items = build_candidate_items(candidates, roles, matches_by_cand)
        return compute_diff(items)

    async def compare_roles(
        self,
        role_ids: list[UUID],
    ) -> DiffResult:
        """对比岗位."""
        if len(role_ids) < 2:
            raise ValueError("至少需要 2 个岗位")
        if len(role_ids) > 5:
            raise ValueError("最多 5 个岗位")

        str_ids = [str(r) for r in role_ids]
        r = (
            self.supabase.table("roles")
            .select("*")
            .in_("id", str_ids)
            .execute()
        )
        roles_data = r.data or []
        if len(roles_data) != len(role_ids):
            found = {x["id"] for x in roles_data}
            missing = [i for i in str_ids if i not in found]
            raise ValueError(f"岗位未找到: {missing}")

        # 加载每个岗位的 matches
        m = (
            self.supabase.table("matches")
            .select("*")
            .in_("role_id", str_ids)
            .order("overall_score", desc=True)
            .execute()
        )
        matches_by_role: dict[str, list[dict[str, Any]]] = {rid: [] for rid in str_ids}
        for row in m.data or []:
            rid = str(row["role_id"])
            matches_by_role.setdefault(rid, []).append(row)

        items = build_role_items(roles_data, matches_by_role=matches_by_role)
        return compute_diff(items)

    async def save_comparison(
        self,
        user_id: UUID,
        item_type: str,  # 'candidate' | 'role'
        item_ids: list[str],
        payload: dict[str, Any],
        title: str | None = None,
    ) -> dict[str, Any]:
        """保存对比快照."""
        record = {
            "id": str(uuid4()),
            "user_id": str(user_id),
            "item_type": item_type,
            "item_ids": item_ids,
            "title": title or f"{item_type} 对比 ({len(item_ids)} 项)",
            "payload": payload,
        }
        result = (
            self.supabase.table("saved_comparisons").insert(record).execute()
        )
        return result.data[0] if result.data else record

    async def list_saved(self, user_id: UUID) -> list[dict[str, Any]]:
        result = (
            self.supabase.table("saved_comparisons")
            .select("*")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    async def get_saved(self, saved_id: UUID, user_id: UUID) -> dict[str, Any] | None:
        result = (
            self.supabase.table("saved_comparisons")
            .select("*")
            .eq("id", str(saved_id))
            .eq("user_id", str(user_id))
            .single()
            .execute()
        )
        return result.data or None