"""T3001: 训练数据集准备.

从历史业务数据构建 3 类任务的 SFT 训练集 (Alpaca 格式):

    resume_scoring — HR 对候选人的历史评分 + 候选人特征
    bias_review    — 偏见审查历史结果 + 原始文本
    hrbp_summary   — 工单 + 人工撰写的摘要

真实实现应从 Supabase / 数仓拉取; 这里既支持传入 records (dict 列表),
也支持在无数据源时生成结构正确的合成样本, 保证离线可跑。
输出为 LLaMA-Factory 可直接消费的 JSONL / JSON。
"""
from __future__ import annotations

import json
import os
import random
from typing import Any, Iterable

from .types import TaskKind, TrainingExample

# ---------------------------------------------------------------------------
# 每类任务的 instruction 模板 (与线上 prompt 对齐, 便于蒸馏)
# ---------------------------------------------------------------------------
_INSTRUCTIONS: dict[TaskKind, str] = {
    TaskKind.RESUME_SCORING: (
        "你是资深招聘官。根据岗位要求评估候选人简历, 输出 0-100 的匹配分和一句理由。"
    ),
    TaskKind.BIAS_REVIEW: (
        "你是招聘合规审查员。判断以下文本是否含有性别/年龄/地域/院校等歧视性偏见, "
        "输出 biased/clean 及涉及的偏见类别。"
    ),
    TaskKind.HRBP_SUMMARY: (
        "你是 HRBP 助理。将以下工单对话浓缩成一段不超过 60 字的中文摘要, 保留关键诉求与处理结果。"
    ),
}


def instruction_for(task: TaskKind) -> str:
    return _INSTRUCTIONS[task]


# ---------------------------------------------------------------------------
# 从业务记录转训练样本
# ---------------------------------------------------------------------------
def _resume_example(rec: dict[str, Any]) -> TrainingExample:
    feats = rec.get("candidate_features") or rec.get("features") or {}
    job = rec.get("job_requirement") or rec.get("job") or ""
    score = rec.get("hr_score", rec.get("score", 0))
    reason = rec.get("reason") or rec.get("hr_comment") or ""
    input_txt = json.dumps(
        {"job": job, "candidate": feats}, ensure_ascii=False, sort_keys=True
    )
    output = json.dumps({"score": int(score), "reason": reason}, ensure_ascii=False)
    return TrainingExample(instruction=instruction_for(TaskKind.RESUME_SCORING), input=input_txt, output=output)


def _bias_example(rec: dict[str, Any]) -> TrainingExample:
    text = rec.get("text") or rec.get("content") or ""
    label = rec.get("label") or ("biased" if rec.get("categories") else "clean")
    categories = rec.get("categories") or []
    output = json.dumps({"label": label, "categories": categories}, ensure_ascii=False)
    return TrainingExample(instruction=instruction_for(TaskKind.BIAS_REVIEW), input=text, output=output)


def _summary_example(rec: dict[str, Any]) -> TrainingExample:
    ticket = rec.get("ticket_text") or rec.get("ticket") or rec.get("text") or ""
    summary = rec.get("human_summary") or rec.get("summary") or ""
    return TrainingExample(instruction=instruction_for(TaskKind.HRBP_SUMMARY), input=ticket, output=summary)


_BUILDERS = {
    TaskKind.RESUME_SCORING: _resume_example,
    TaskKind.BIAS_REVIEW: _bias_example,
    TaskKind.HRBP_SUMMARY: _summary_example,
}


def build_examples(task: TaskKind, records: Iterable[dict[str, Any]]) -> list[TrainingExample]:
    """把业务记录列表转成训练样本 (跳过空记录)。"""
    builder = _BUILDERS[task]
    out: list[TrainingExample] = []
    for rec in records:
        if not rec:
            continue
        try:
            out.append(builder(rec))
        except Exception:  # noqa: BLE001 - 单条脏数据不应中断整批
            continue
    return out


# ---------------------------------------------------------------------------
# 合成样本 (无真实数据源时的兜底, 保证 pipeline 可端到端跑)
# ---------------------------------------------------------------------------
_SYNTH_SKILLS = ["Python", "Go", "React", "Kubernetes", "PyTorch", "Rust", "Java", "Flink"]
_SYNTH_BIAS = [
    ("我们只招 985/211 应届生", "biased", ["院校"]),
    ("限男性, 女生勿扰", "biased", ["性别"]),
    ("欢迎有 5 年经验的后端工程师投递", "clean", []),
    ("年龄 35 岁以下优先", "biased", ["年龄"]),
    ("需要熟悉分布式系统的候选人", "clean", []),
]


def synth_records(task: TaskKind, n: int, *, seed: int = 42) -> list[dict[str, Any]]:
    """生成 n 条结构正确的合成业务记录。"""
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    for i in range(n):
        if task is TaskKind.RESUME_SCORING:
            skills = rng.sample(_SYNTH_SKILLS, k=rng.randint(2, 4))
            years = rng.randint(1, 12)
            score = min(100, 40 + years * 4 + len(skills) * 3)
            out.append(
                {
                    "job_requirement": f"招聘 {skills[0]} 高级工程师",
                    "candidate_features": {"skills": skills, "years": years},
                    "hr_score": score,
                    "reason": f"具备 {', '.join(skills)}, {years} 年经验",
                }
            )
        elif task is TaskKind.BIAS_REVIEW:
            text, label, cats = _SYNTH_BIAS[i % len(_SYNTH_BIAS)]
            out.append({"text": text, "label": label, "categories": cats})
        else:  # HRBP_SUMMARY
            out.append(
                {
                    "ticket_text": f"候选人 #{i} 询问 offer 薪资构成与入职时间, HR 已回复并确认 {rng.randint(1,4)} 周内入职。",
                    "human_summary": f"候选人询问薪资与入职, 已确认 {rng.randint(1,4)} 周内到岗。",
                }
            )
    return out


# ---------------------------------------------------------------------------
# 落盘 (LLaMA-Factory 数据格式)
# ---------------------------------------------------------------------------
def write_dataset(
    examples: list[TrainingExample],
    out_path: str,
    *,
    fmt: str = "alpaca",
) -> str:
    """写出训练集; 返回文件路径。

    fmt: alpaca (JSON 数组) | sharegpt (JSON 数组) | jsonl (每行一条 alpaca)。
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    if fmt == "jsonl":
        with open(out_path, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex.to_alpaca(), ensure_ascii=False) + "\n")
    else:
        rows = [ex.to_sharegpt() if fmt == "sharegpt" else ex.to_alpaca() for ex in examples]
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    return out_path


def prepare_dataset(
    task: TaskKind,
    *,
    records: Iterable[dict[str, Any]] | None = None,
    out_dir: str = "/tmp/lora_datasets",
    min_samples: int = 32,
    fmt: str = "alpaca",
) -> tuple[str, list[TrainingExample]]:
    """一站式: 业务记录 → 训练样本 → 落盘。

    records 为空或过少时用合成样本补齐到 min_samples, 保证训练可启动。
    返回 (dataset_path, examples)。
    """
    examples = build_examples(task, records or [])
    if len(examples) < min_samples:
        need = min_samples - len(examples)
        examples += build_examples(task, synth_records(task, need))
    out_path = os.path.join(out_dir, f"{task.value}.json" if fmt != "jsonl" else f"{task.value}.jsonl")
    write_dataset(examples, out_path, fmt=fmt)
    return out_path, examples
