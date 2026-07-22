"""T6301 (v11.2) — 匹配阀值门 (visibility gate).

甲方要求: **不淘汰, 只排序**. 但为了"避免无效沟通", 双方只有当任意一次
匹配评分 ≥ MATCH_THRESHOLD (默认 70%) 时才互相可见. 低于阀值 → 双方暂不可见.

本模块负责:
  * 暴露可配置阀值 ``MATCH_THRESHOLD`` (环境变量 ``MATCH_THRESHOLD`` 覆盖).
  * ``is_above_threshold(score)`` —— 简单阈值判定.
  * ``VisibilityGate.decide(score)`` —— 返回 visible / threshold / reason 三件套.
  * ``compute_pair_score(candidate, role)`` —— 包装 :class:`HardConditionFilter`.
  * ``best_score_against_roles(talent, roles)`` —— 取候选人对一组岗位的最佳分
    (任一岗位过线即对雇主可见).
  * ``best_score_against_talents(role, talents)`` —— 对称: 岗位对一组人才的最佳分.

所有函数对空列表健壮 (返回 ``(0, None, None)``).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from matching.hard_filter import HardConditionFilter, MatchResult

logger = logging.getLogger("recruittech.matching.threshold")

# ---------------------------------------------------------------------------
# 阀值常量 (可被环境变量覆盖)
# ---------------------------------------------------------------------------

MATCH_THRESHOLD = int(os.environ.get("MATCH_THRESHOLD", "70"))

# 低于阀值时的固定文案 (甲方口径)
_BELOW_REASON = f"低于匹配阀值({MATCH_THRESHOLD}%)，双方暂不可见，避免无效沟通"


def is_above_threshold(score: int) -> bool:
    """``score`` 是否达到匹配阀值 (含等号: == 阀值即算过线)."""
    try:
        score = int(score)
    except (TypeError, ValueError):
        return False
    return score >= MATCH_THRESHOLD


# ---------------------------------------------------------------------------
# 可见性门
# ---------------------------------------------------------------------------

class VisibilityGate:
    """根据匹配分判定双方是否互相可见.

    Usage::

        gate = VisibilityGate()
        decision = gate.decide(match_result.match_score)
        if decision["visible"]:
            ...  # 双方可见, 允许发起沟通
    """

    def __init__(self, threshold: Optional[int] = None) -> None:
        self.threshold = int(threshold) if threshold is not None else MATCH_THRESHOLD

    def decide(self, score: int) -> dict[str, Any]:
        """返回 ``{'visible': bool, 'threshold': int, 'reason': str}``."""
        try:
            score_int = int(score)
        except (TypeError, ValueError):
            score_int = 0
        visible = score_int >= self.threshold
        if visible:
            reason = f"匹配分 {score_int}% 达到阀值, 双方可见"
        else:
            reason = (
                f"低于匹配阀值({self.threshold}%)，"
                f"双方暂不可见，避免无效沟通"
            )
        return {
            "visible": visible,
            "threshold": self.threshold,
            "reason": reason,
        }


# ---------------------------------------------------------------------------
# 单对 / 多对评分封装
# ---------------------------------------------------------------------------

# 复用同一个 filter 实例 (无状态)
_filter = HardConditionFilter()


def compute_pair_score(candidate: Any, role: Any) -> MatchResult:
    """计算单个 (候选人, 岗位) 对的 :class:`MatchResult`.

    薄封装 :meth:`HardConditionFilter.filter`, 方便上层统一入口.
    """
    return _filter.filter(candidate, role)


def _best(
    candidate: Any,
    candidate_others: list[Any],
    id_getter,
    *,
    early_threshold: Optional[int] = None,
) -> tuple[int, Optional[str], Optional[MatchResult]]:
    """对 ``candidate_others`` (一组岗位) 逐一评分, 取最大分.

    恒以 ``filter(candidate, role)`` 顺序调用 (候选人在前, 岗位在后).
    ``id_getter(role)`` 从岗位对象里取 id. 空列表 → ``(0, None, None)``.

    性能优化 (v11.5 R4): 当调用方只需要 "是否过线" (如 ``initiate_contact`` /
    ``get_talent`` 的阀值门) 时, 可传 ``early_threshold``. 一旦某岗位评分
    ≥ 该阀值即 **提前返回** (语义: 任一过线即足够, 不必继续算更高分). 默认
    ``None`` → 完整取最大分 (雇主列表需要精确排序, 必须用默认值).
    """
    if not candidate_others:
        return 0, None, None

    best_score = -1
    best_id: Optional[str] = None
    best_res: Optional[MatchResult] = None

    for obj in candidate_others:
        try:
            res = _filter.filter(candidate, obj)
        except Exception:  # noqa: BLE001 — 单条脏数据不影响整体
            logger.warning("scoring failed for %r, skipping", obj, exc_info=True)
            continue
        if res.match_score > best_score:
            best_score = res.match_score
            best_id = id_getter(obj)
            best_res = res
            # 早停: 已找到一个过线岗位 → 调用方只要 "是否可见", 无需更高分.
            if (
                early_threshold is not None
                and best_score >= early_threshold
            ):
                return best_score, best_id, best_res

    if best_score < 0:
        # 全部异常 → 安全兜底
        return 0, None, None
    return best_score, best_id, best_res


def best_score_against_roles(
    talent: Any, roles: list[Any], *, early_threshold: Optional[int] = None
) -> tuple[int, Optional[str], Optional[MatchResult]]:
    """候选人对一组岗位的最佳匹配分.

    甲方语义: 候选人只要命中 **任意一个** 岗位过线, 即对雇主可见.
    返回 ``(best_score, best_role_id, MatchResult)``. 空列表 → ``(0, None, None)``.

    ``early_threshold`` (v11.5 R4 性能): 当只需判定 "是否过线" 时传入阀值,
    任一岗位达标即提前返回, 避免对全部 R 个岗位评分. 雇主列表需要精确排序
    (取最大分), **不得** 传该参数.
    """
    return _best(talent, roles, _role_id_getter, early_threshold=early_threshold)


def best_score_against_talents(
    role: Any, talents: list[Any], *, early_threshold: Optional[int] = None
) -> tuple[int, Optional[str], Optional[MatchResult]]:
    """岗位对一组人才的最佳匹配分 (对称).

    ``filter(candidate, role)`` 始终候选人在前 —— 这里把每个 talent 当 candidate,
    固定的 role 当岗位, 取最大分.
    返回 ``(best_score, best_talent_id, MatchResult)``. 空列表 → ``(0, None, None)``.

    ``early_threshold`` (v11.5 R4 性能): 同 :func:`best_score_against_roles`,
    任一人才达标即提前返回. 排序场景 **不得** 传该参数.
    """
    if not talents:
        return 0, None, None

    best_score = -1
    best_id: Optional[str] = None
    best_res: Optional[MatchResult] = None

    for talent in talents:
        try:
            res = _filter.filter(talent, role)
        except Exception:  # noqa: BLE001 — 单条脏数据不影响整体
            logger.warning("scoring failed for %r, skipping", talent, exc_info=True)
            continue
        if res.match_score > best_score:
            best_score = res.match_score
            best_id = _candidate_id_getter(talent)
            best_res = res
            # 早停: 已找到一个过线人才 → 调用方只要 "是否可见", 无需更高分.
            if (
                early_threshold is not None
                and best_score >= early_threshold
            ):
                return best_score, best_id, best_res

    if best_score < 0:
        return 0, None, None
    return best_score, best_id, best_res


# ---------------------------------------------------------------------------
# id 取值辅助 (兼容 dict / 对象 / 常见字段名)
# ---------------------------------------------------------------------------

def _get_first(obj: Any, *keys: str) -> Optional[str]:
    if obj is None:
        return None
    for k in keys:
        if isinstance(obj, dict):
            v = obj.get(k)
        else:
            v = getattr(obj, k, None)
        if v is not None and v != "":
            return str(v)
    return None


def _role_id_getter(role: Any) -> Optional[str]:
    return _get_first(role, "id", "role_id", "uuid")


def _candidate_id_getter(talent: Any) -> Optional[str]:
    return _get_first(talent, "id", "candidate_id", "talent_id", "uuid")
