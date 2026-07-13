"""T3001: LoRA Fine-tuning (LLaMA-Factory) 服务层.

流程: dataset_prep → train (QLoRA) → evaluate (金标准 + Agenta) → deploy (vLLM) → registry。

公共入口:
    prepare_dataset / synth_records          — 数据准备
    train                                    — 调 LLaMA-Factory 训练
    evaluate / evaluate_gold / rouge_l       — 评估
    deploy / build_vllm_command              — vLLM 部署
    get_registry / reset_registry            — 模型注册中心
    run_pipeline / train_all                 — 端到端编排
"""
from __future__ import annotations

from .dataset_prep import (
    build_examples,
    instruction_for,
    prepare_dataset,
    synth_records,
    write_dataset,
)
from .deploy import DeploySpec, build_vllm_command, deploy
from .evaluate import (
    DEFAULT_THRESHOLD,
    evaluate,
    evaluate_gold,
    gold_from_examples,
    rouge_l,
    run_agenta_evaluator,
)
from .pipeline import run_pipeline, train_all
from .registry import ModelRegistry, get_registry, reset_registry
from .train import render_configs, train
from .types import (
    EvalResult,
    JobStatus,
    LoRAConfig,
    LoRAModel,
    TaskKind,
    TrainingExample,
    TrainingJob,
)

__all__ = [
    "DEFAULT_THRESHOLD",
    "DeploySpec",
    "EvalResult",
    "JobStatus",
    "LoRAConfig",
    "LoRAModel",
    "ModelRegistry",
    "TaskKind",
    "TrainingExample",
    "TrainingJob",
    "build_examples",
    "build_vllm_command",
    "deploy",
    "evaluate",
    "evaluate_gold",
    "get_registry",
    "gold_from_examples",
    "instruction_for",
    "prepare_dataset",
    "render_configs",
    "reset_registry",
    "rouge_l",
    "run_agenta_evaluator",
    "run_pipeline",
    "synth_records",
    "train",
    "train_all",
    "write_dataset",
]
