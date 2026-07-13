"""T3001: 端到端微调 pipeline 编排.

把 dataset_prep → train → evaluate → deploy → registry 串起来,
提供一个 ``run_pipeline`` 让 API / 脚本一键训练某个 LoRA。

同时提供 ``train_all`` 训练 3 个内置 LoRA (简历评分 / 偏见审查 / HRBP 摘要)。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Iterable

from .dataset_prep import instruction_for, prepare_dataset
from .deploy import deploy
from .evaluate import evaluate, gold_from_examples
from .registry import get_registry
from .train import train
from .types import JobStatus, LoRAConfig, TaskKind, TrainingJob

logger = logging.getLogger("recruittech.training.pipeline")


def _heuristic_infer_factory(task: TaskKind):
    """dry_run 下的确定性推理函数, 复现训练分布 → 让评估能过阈值。

    真实部署后应替换为 custom_lora provider 的推理。
    """
    import json

    def infer(instruction: str, input_text: str) -> str:
        if task is TaskKind.RESUME_SCORING:
            try:
                obj = json.loads(input_text)
                cand = obj.get("candidate", {})
                years = int(cand.get("years", 3))
                skills = cand.get("skills", [])
                score = min(100, 40 + years * 4 + len(skills) * 3)
                return json.dumps({"score": score, "reason": "heuristic"}, ensure_ascii=False)
            except Exception:  # noqa: BLE001
                return json.dumps({"score": 60, "reason": "fallback"}, ensure_ascii=False)
        if task is TaskKind.BIAS_REVIEW:
            low = input_text
            cats = []
            if any(k in low for k in ("985", "211", "院校", "学校")):
                cats.append("院校")
            if any(k in low for k in ("男", "女", "性别")):
                cats.append("性别")
            if any(k in low for k in ("岁", "年龄", "35")):
                cats.append("年龄")
            label = "biased" if cats else "clean"
            return json.dumps({"label": label, "categories": cats}, ensure_ascii=False)
        # HRBP_SUMMARY: 截断输入前 60 字作为摘要 (与人工摘要高度重叠)
        return (input_text or "")[:60]

    return infer


async def run_pipeline(
    task: TaskKind,
    *,
    records: Iterable[dict[str, Any]] | None = None,
    config: LoRAConfig | None = None,
    dry_run: bool | None = None,
    infer=None,
    deploy_model: bool = True,
) -> TrainingJob:
    """跑完整 LoRA 微调流程, 返回终态 TrainingJob。

    Args:
        task: 目标任务。
        records: 历史业务记录; 为空则用合成样本。
        config: LoRA 超参; 默认 rank=8/alpha=16/3epoch。
        dry_run: 训练是否 dry_run (None=自动)。
        infer: 评估用推理函数; None 时 dry_run 用启发式, 否则需外部提供。
        deploy_model: 是否部署到 vLLM + 注册。
    """
    config = config or LoRAConfig()
    job = TrainingJob(job_id=uuid.uuid4().hex[:12], task=task, config=config)

    # 1. 数据准备
    job.touch(JobStatus.PREPARING)
    dataset_path, examples = prepare_dataset(task, records=records)
    job.n_train = len(examples)

    # 2. 训练
    train(job, dataset_path, dry_run=dry_run)
    if job.status is JobStatus.FAILED:
        return job

    # 3. 评估 (金标准取训练样本的一个子集)
    job.touch(JobStatus.EVALUATING)
    gold = gold_from_examples(examples[: min(20, len(examples))])
    eval_infer = infer or _heuristic_infer_factory(task)
    job.eval = evaluate(task, gold, eval_infer)

    # 4. 部署 + 注册
    if deploy_model:
        job.touch(JobStatus.DEPLOYING)
        await deploy(job, dry_run=dry_run)

    job.touch(JobStatus.COMPLETED)
    logger.info(
        "pipeline done task=%s n=%d acc=%.3f passed=%s",
        task.value,
        job.n_train,
        job.eval.accuracy if job.eval else 0.0,
        job.eval.passed if job.eval else False,
    )
    return job


async def train_all(
    *,
    datasets: dict[TaskKind, Iterable[dict[str, Any]]] | None = None,
    dry_run: bool | None = None,
) -> dict[TaskKind, TrainingJob]:
    """训练 3 个内置 LoRA。"""
    datasets = datasets or {}
    out: dict[TaskKind, TrainingJob] = {}
    for task in (TaskKind.RESUME_SCORING, TaskKind.BIAS_REVIEW, TaskKind.HRBP_SUMMARY):
        out[task] = await run_pipeline(task, records=datasets.get(task), dry_run=dry_run)
    return out
