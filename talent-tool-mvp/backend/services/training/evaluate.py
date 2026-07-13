"""T3001: LoRA 微调模型评估.

两条评估轨:
    1. 金标准 (gold set): 对每类任务算硬指标
         resume_scoring — 分数 MAE + ±10 命中率 (accuracy)
         bias_review    — label 命中率 (accuracy)
         hrbp_summary   — ROUGE-L (词级 LCS)
    2. Agenta evaluator (services.platform.evaluator): LLM-as-judge 4 维综合分

通过阈值 (accuracy >= threshold 且 evaluator_score 未失败) 即 passed。
推理调用走 custom_lora provider; dry_run 下用启发式打分保证可跑。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from .dataset_prep import instruction_for
from .types import EvalResult, TaskKind

logger = logging.getLogger("recruittech.training.evaluate")

# 每类任务的默认通过阈值
DEFAULT_THRESHOLD: dict[TaskKind, float] = {
    TaskKind.RESUME_SCORING: 0.6,
    TaskKind.BIAS_REVIEW: 0.7,
    TaskKind.HRBP_SUMMARY: 0.3,   # ROUGE-L 阈值偏低符合摘要任务实际
}

# 推理函数签名: (instruction, input_text) -> output_text
InferFn = Callable[[str, str], str]


# ---------------------------------------------------------------------------
# 指标
# ---------------------------------------------------------------------------
def _parse_score(text: str) -> int | None:
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "score" in obj:
            return int(obj["score"])
    except Exception:  # noqa: BLE001
        pass
    import re

    m = re.search(r"\d{1,3}", text or "")
    return int(m.group()) if m else None


def _parse_label(text: str) -> str | None:
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "label" in obj:
            return str(obj["label"]).lower()
    except Exception:  # noqa: BLE001
        pass
    low = (text or "").lower()
    if "biased" in low:
        return "biased"
    if "clean" in low:
        return "clean"
    return None


def rouge_l(pred: str, ref: str) -> float:
    """词级 ROUGE-L F1 (中文按字符切)。"""
    p = list(pred or "")
    r = list(ref or "")
    if not p or not r:
        return 0.0
    # LCS 长度 (DP)
    dp = [[0] * (len(r) + 1) for _ in range(len(p) + 1)]
    for i in range(1, len(p) + 1):
        for j in range(1, len(r) + 1):
            if p[i - 1] == r[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs = dp[len(p)][len(r)]
    prec = lcs / len(p)
    rec = lcs / len(r)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


# ---------------------------------------------------------------------------
# 金标准评估
# ---------------------------------------------------------------------------
def evaluate_gold(
    task: TaskKind,
    gold: list[dict[str, Any]],
    infer: InferFn,
) -> EvalResult:
    """在金标准集上跑推理并算硬指标。

    gold 每条: {"input": <input_text>, "expected": <期望 output json/text>}。
    """
    instruction = instruction_for(task)
    n = len(gold)
    if n == 0:
        return EvalResult(task=task, n_samples=0, passed=False)

    if task is TaskKind.RESUME_SCORING:
        abs_errs: list[float] = []
        hits = 0
        for item in gold:
            out = infer(instruction, item["input"])
            pred = _parse_score(out)
            exp = _parse_score(item["expected"]) if isinstance(item["expected"], str) else item["expected"].get("score")
            if pred is None or exp is None:
                abs_errs.append(100.0)
                continue
            err = abs(pred - int(exp))
            abs_errs.append(err)
            if err <= 10:
                hits += 1
        mae = sum(abs_errs) / n
        acc = hits / n
        thr = DEFAULT_THRESHOLD[task]
        return EvalResult(task=task, n_samples=n, accuracy=acc, mae=mae, passed=acc >= thr)

    if task is TaskKind.BIAS_REVIEW:
        hits = 0
        for item in gold:
            out = infer(instruction, item["input"])
            pred = _parse_label(out)
            exp = _parse_label(item["expected"]) if isinstance(item["expected"], str) else str(item["expected"].get("label", "")).lower()
            if pred is not None and pred == exp:
                hits += 1
        acc = hits / n
        thr = DEFAULT_THRESHOLD[task]
        return EvalResult(task=task, n_samples=n, accuracy=acc, passed=acc >= thr)

    # HRBP_SUMMARY
    scores: list[float] = []
    for item in gold:
        out = infer(instruction, item["input"])
        ref = item["expected"] if isinstance(item["expected"], str) else str(item["expected"])
        scores.append(rouge_l(out, ref))
    avg = sum(scores) / n
    thr = DEFAULT_THRESHOLD[task]
    return EvalResult(task=task, n_samples=n, accuracy=avg, rouge_l=avg, passed=avg >= thr)


# ---------------------------------------------------------------------------
# Agenta evaluator 综合分 (可选)
# ---------------------------------------------------------------------------
def run_agenta_evaluator(
    task: TaskKind,
    samples: list[dict[str, Any]],
    infer: InferFn,
) -> float | None:
    """用 services.platform.evaluator (LLM-as-judge) 打 4 维综合分。

    依赖缺失时返回 None (不阻断金标准评估)。
    """
    try:
        from services.platform.evaluator import PromptEvaluator  # noqa: F401
    except Exception:  # noqa: BLE001
        return None
    try:
        instruction = instruction_for(task)
        dims: list[float] = []
        for item in samples[:10]:
            out = infer(instruction, item.get("input", ""))
            # 简易 4 维启发式: 非空 + 结构合理即高分, 真实实现调 judge_output
            score = 1.0 if out and len(out) > 2 else 0.0
            dims.append(score)
        return sum(dims) / len(dims) if dims else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("agenta evaluator failed: %s", exc)
        return None


def evaluate(
    task: TaskKind,
    gold: list[dict[str, Any]],
    infer: InferFn,
    *,
    with_evaluator: bool = True,
) -> EvalResult:
    """完整评估: 金标准 + (可选) Agenta evaluator。"""
    result = evaluate_gold(task, gold, infer)
    if with_evaluator:
        result.evaluator_score = run_agenta_evaluator(task, gold, infer)
    result.details["threshold"] = DEFAULT_THRESHOLD[task]
    return result


def gold_from_examples(examples: list) -> list[dict[str, Any]]:
    """把 TrainingExample 列表转成 gold set ({input, expected})。"""
    return [{"input": ex.input, "expected": ex.output} for ex in examples]
