"""Interview Calibration — T1801.

目标:对齐 AI Interviewer 评分与真人 HR 评分。
原理:
    1. 邀请 ≥10 名真实候选人(或内测员工)进行 AI 面试
    2. 同一位候选人由 2 名 HR 独立打分(golden label)
    3. 计算 AI 评分 vs HR 评分的差异(MAE / Pearson / Quadratic Kappa)
    4. 输出 calibration_report.json
    5. 若差异 > 阈值,自动建议 weights 调整

校准指标:
    - MAE (Mean Absolute Error):  |ai - hr|
    - Bias:  mean(ai - hr)  -> 系统性偏差(>0 表示 AI 打分偏高)
    - Pearson r:  整体相关性
    - Quadratic Weighted Kappa: 顺序一致性 (0-1, 越高越好)
    - Per-band accuracy: 在各 band 上的命中率

输出: backend/reports/interview_calibration_YYYY-MM-DD.json
"""
from __future__ import annotations

import json
import logging
import math
import os
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger("recruittech.services.interview_calibration")

REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class InterviewRecord:
    """一条 AI + HR 双盲评分记录."""

    candidate_id: str
    role: str
    ai_overall: float
    hr_overall_a: float
    hr_overall_b: float
    hr_band: str = ""   # 共识 band
    ai_band: str = ""
    notes: str = ""

    @property
    def hr_overall(self) -> float:
        """两 HR 打分平均."""
        return round((self.hr_overall_a + self.hr_overall_b) / 2.0, 1)

    @property
    def hr_disagreement(self) -> float:
        """HR 之间差异 — 越大说明题目越主观."""
        return abs(self.hr_overall_a - self.hr_overall_b)


# ---------------------------------------------------------------------------
# Band 工具函数
# ---------------------------------------------------------------------------
def _band(score: float) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 55:
        return "fair"
    return "weak"


def _band_to_num(b: str) -> int:
    return {"weak": 0, "fair": 1, "good": 2, "excellent": 3}.get(b, 1)


def _num_to_band(n: int) -> str:
    return {0: "weak", 1: "fair", 2: "good", 3: "excellent"}.get(n, "fair")


# ---------------------------------------------------------------------------
# Calibration 类
# ---------------------------------------------------------------------------
class InterviewCalibrator:
    """收集 AI + HR 评分,产出校准报告 + 自动建议."""

    def __init__(self, records: list[InterviewRecord] | None = None) -> None:
        self.records = records or []

    # ------------------------------------------------------------------
    # 数据导入
    # ------------------------------------------------------------------
    def add(self, r: InterviewRecord) -> None:
        self.records.append(r)

    def add_batch(self, rs: list[InterviewRecord]) -> None:
        self.records.extend(rs)

    @classmethod
    def from_file(cls, path: str | Path) -> "InterviewCalibrator":
        p = Path(path)
        if not p.exists():
            logger.warning(f"calibration dataset missing: {p}")
            return cls()
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        records = [
            InterviewRecord(
                candidate_id=str(r.get("candidate_id", "")),
                role=str(r.get("role", "")),
                ai_overall=float(r.get("ai_overall", 0)),
                hr_overall_a=float(r.get("hr_overall_a", 0)),
                hr_overall_b=float(r.get("hr_overall_b", 0)),
                hr_band=str(r.get("hr_band", "")) or _band((float(r.get("hr_overall_a", 0)) + float(r.get("hr_overall_b", 0))) / 2),
                ai_band=str(r.get("ai_band", "")) or _band(float(r.get("ai_overall", 0))),
                notes=str(r.get("notes", "")),
            )
            for r in data.get("records", [])
        ]
        return cls(records)

    # ------------------------------------------------------------------
    # 指标计算
    # ------------------------------------------------------------------
    def metrics(self) -> dict:
        rs = self.records
        if not rs:
            return {"error": "no records"}
        ai = [r.ai_overall for r in rs]
        hr = [r.hr_overall for r in rs]
        n = len(rs)

        mae = sum(abs(a - h) for a, h in zip(ai, hr)) / n
        bias = sum(a - h for a, h in zip(ai, hr)) / n
        rmse = math.sqrt(sum((a - h) ** 2 for a, h in zip(ai, hr)) / n)
        # Pearson r
        mean_a, mean_h = statistics.fmean(ai), statistics.fmean(hr)
        num = sum((a - mean_a) * (h - mean_h) for a, h in zip(ai, hr))
        den_a = math.sqrt(sum((a - mean_a) ** 2 for a in ai))
        den_h = math.sqrt(sum((h - mean_h) ** 2 for h in hr))
        pearson = (num / (den_a * den_h)) if (den_a > 0 and den_h > 0) else 0.0

        # Quadratic weighted kappa over band
        qwk = self._quadratic_weighted_kappa(ai, hr)

        # Per-band accuracy
        per_band = {"weak": [0, 0], "fair": [0, 0], "good": [0, 0], "excellent": [0, 0]}
        for r in rs:
            b = r.hr_band or _band(r.hr_overall)
            per_band[b][1] += 1
            ai_b = _band(r.ai_overall)
            if ai_b == b:
                per_band[b][0] += 1
        per_band_acc = {
            b: round(hit / total, 3) if total else None for b, (hit, total) in per_band.items()
        }

        # HR inter-rater agreement
        hr_disagreement = [r.hr_disagreement for r in rs]
        avg_disagree = round(statistics.fmean(hr_disagreement), 2)

        # Role breakdown
        role_breakdown: dict[str, dict] = {}
        for role in sorted({r.role for r in rs}):
            sub = [r for r in rs if r.role == role]
            ai_sub = [r.ai_overall for r in sub]
            hr_sub = [r.hr_overall for r in sub]
            role_breakdown[role] = {
                "n": len(sub),
                "mae": round(sum(abs(a - h) for a, h in zip(ai_sub, hr_sub)) / len(sub), 2),
                "mean_ai": round(statistics.fmean(ai_sub), 1),
                "mean_hr": round(statistics.fmean(hr_sub), 1),
            }

        return {
            "n": n,
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "bias": round(bias, 2),
            "pearson_r": round(pearson, 3),
            "quadratic_weighted_kappa": round(qwk, 3),
            "per_band_accuracy": per_band_acc,
            "hr_avg_disagreement": avg_disagree,
            "role_breakdown": role_breakdown,
            "verdict": self._verdict(mae, pearson, qwk),
            "suggestions": self._suggest(mae, bias, pearson, qwk),
        }

    @staticmethod
    def _verdict(mae: float, pearson: float, qwk: float) -> str:
        if mae <= 8 and pearson >= 0.7 and qwk >= 0.7:
            return "excellent"
        if mae <= 12 and pearson >= 0.55 and qwk >= 0.5:
            return "acceptable"
        if mae <= 18:
            return "needs_improvement"
        return "blocking"

    @staticmethod
    def _suggest(mae: float, bias: float, pearson: float, qwk: float) -> list[str]:
        out: list[str] = []
        if abs(bias) > 3:
            direction = "偏高" if bias > 0 else "偏低"
            out.append(f"AI 整体{direction} HR {abs(bias):.1f} 分;考虑在 _recommendation 中按 bias 调整")
        if qwk < 0.6:
            out.append("band 命中率偏低;在 evaluate_answer 中加强 band 边界的 prompt 锚定(weak/fair/good/excellent 各给 1 个示例)")
        if pearson < 0.6:
            out.append("整体相关性不足;可能 LLM 评分波动较大,可加 self-consistency (5 次打 median)")
        if mae > 12:
            out.append("MAE 偏高;在 mock mode 之外增加 rubric 参考分,让 LLM 评分有 baseline")
        if not out:
            out.append("OK — 校准达标,继续积累数据")
        return out

    @staticmethod
    def _quadratic_weighted_kappa(ai: list[float], hr: list[float]) -> float:
        """QWK over bands."""
        if not ai or not hr:
            return 0.0
        # 转为 band 数值
        a = [_band_to_num(_band(x)) for x in ai]
        h = [_band_to_num(_band(x)) for x in hr]
        n = len(a)
        # 4 个 bands
        K = 4
        # observed matrix
        O = [[0] * K for _ in range(K)]
        for ai_n, hr_n in zip(a, h):
            O[ai_n][hr_n] += 1
        # marginals
        row_marg = [sum(O[i]) for i in range(K)]
        col_marg = [sum(O[i][j] for i in range(K)) for j in range(K)]
        N = sum(row_marg)
        # expected
        E = [[0.0] * K for _ in range(K)]
        for i in range(K):
            for j in range(K):
                E[i][j] = row_marg[i] * col_marg[j] / N if N else 0
        # weights: 1 - (i-j)^2/(K-1)^2
        W = [[1 - ((i - j) ** 2) / ((K - 1) ** 2) for j in range(K)] for i in range(K)]
        num = sum(W[i][j] * O[i][j] for i in range(K) for j in range(K))
        den = sum(W[i][j] * E[i][j] for i in range(K) for j in range(K))
        return (num / den) if den > 0 else 0.0

    # ------------------------------------------------------------------
    # 报告生成
    # ------------------------------------------------------------------
    def report(self) -> dict:
        m = self.metrics()
        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "version": "1.0",
            "task": "T1801",
            "summary": m,
            "records": [asdict(r) for r in self.records],
        }

    def save_report(self, path: str | Path | None = None) -> Path:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = Path(path) if path else (REPORT_DIR / f"interview_calibration_{date.today().isoformat()}.json")
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.report(), f, ensure_ascii=False, indent=2)
        logger.info(f"calibration report saved: {path}")
        return path


# ---------------------------------------------------------------------------
# 合成数据集(无真人时的占位 — 用于 mock 模式演示校准流程)
# ---------------------------------------------------------------------------
def _synth_demo_dataset() -> list[InterviewRecord]:
    """10 条示例数据 — 用 linspace + 噪声模拟真人 vs AI 一致/不一致场景."""
    import random

    random.seed(42)
    base_hr = [62, 71, 78, 84, 55, 68, 81, 73, 88, 60]
    return [
        InterviewRecord(
            candidate_id=f"cand_{i+1:02d}",
            role=role,
            ai_overall=round(hr + random.gauss(0, 4), 1),
            hr_overall_a=round(hr + random.gauss(0, 2), 1),
            hr_overall_b=round(hr + random.gauss(0, 2), 1),
        )
        for i, (hr, role) in enumerate(
            zip(base_hr, ["backend_engineer"] * 3 + ["frontend_engineer"] * 2 + ["data_scientist"] * 2 + ["product_manager"] * 2 + ["designer"])
        )
    ]


# ---------------------------------------------------------------------------
# CLI 入口 — scripts/run_interview_calibration.py 使用
# ---------------------------------------------------------------------------
def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Interview AI-HR calibration report")
    p.add_argument("--input", type=str, default=None, help="JSON 路径,含 {records: [...]}")
    p.add_argument("--output", type=str, default=None, help="报告输出 JSON 路径")
    p.add_argument("--demo", action="store_true", help="无数据时使用 10 条合成数据演示流程")
    args = p.parse_args()

    if args.input:
        cal = InterviewCalibrator.from_file(args.input)
    elif args.demo or not os.environ.get("CALIBRATION_DATA"):
        recs = _synth_demo_dataset()
        cal = InterviewCalibrator(recs)
    else:
        cal = InterviewCalibrator()

    if not cal.records:
        print("No records; pass --input or --demo")
        return 1

    path = cal.save_report(args.output)
    m = cal.metrics()
    print(json.dumps({
        "file": str(path),
        "n": m.get("n"),
        "mae": m.get("mae"),
        "rmse": m.get("rmse"),
        "bias": m.get("bias"),
        "pearson_r": m.get("pearson_r"),
        "qwk": m.get("quadratic_weighted_kappa"),
        "verdict": m.get("verdict"),
        "per_band_accuracy": m.get("per_band_accuracy"),
        "suggestions": m.get("suggestions"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
