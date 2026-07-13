"""T3001: Training / Fine-tuning 领域类型.

所有 LoRA 微调流程 (数据准备 → 训练 → 评估 → 部署 → 注册) 的统一数据结构。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskKind(str, Enum):
    """支持微调的 3 类任务 (对应 3 个 LoRA adapter)."""

    RESUME_SCORING = "resume_scoring"      # 简历评分 (HR 评分 + 候选人特征)
    BIAS_REVIEW = "bias_review"            # 偏见审查 (审查结果 + 文本)
    HRBP_SUMMARY = "hrbp_summary"          # HRBP 摘要 (工单摘要 + 人工摘要)


class JobStatus(str, Enum):
    """训练任务生命周期."""

    PENDING = "pending"
    PREPARING = "preparing"
    TRAINING = "training"
    EVALUATING = "evaluating"
    DEPLOYING = "deploying"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class TrainingExample:
    """单条 SFT 训练样本 (Alpaca 风格).

    LLaMA-Factory 的 alpaca 格式: {instruction, input, output}。
    """

    instruction: str
    input: str
    output: str

    def to_alpaca(self) -> dict[str, str]:
        return {"instruction": self.instruction, "input": self.input, "output": self.output}

    def to_sharegpt(self) -> dict[str, Any]:
        """ShareGPT 多轮对话格式 (LLaMA-Factory 也支持)."""
        user = self.instruction + (f"\n\n{self.input}" if self.input else "")
        return {
            "conversations": [
                {"from": "human", "value": user},
                {"from": "gpt", "value": self.output},
            ]
        }


@dataclass(slots=True)
class LoRAConfig:
    """QLoRA 超参 (对齐 LLaMA-Factory train 参数)."""

    base_model: str = "Qwen/Qwen2.5-7B-Instruct"
    lora_rank: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    lora_target: str = "all"           # LLaMA-Factory: all / q_proj,v_proj ...
    quantization_bit: int = 4          # QLoRA = 4bit
    epochs: float = 3.0
    batch_size: int = 4
    grad_accum: int = 4
    learning_rate: float = 2e-4
    cutoff_len: int = 2048
    template: str = "qwen"             # LLaMA-Factory chat template

    def to_llamafactory_args(self, *, dataset: str, output_dir: str) -> dict[str, Any]:
        """转成 LLaMA-Factory ``llamafactory-cli train`` 的 YAML/CLI 参数字典."""
        return {
            "stage": "sft",
            "do_train": True,
            "model_name_or_path": self.base_model,
            "dataset": dataset,
            "template": self.template,
            "finetuning_type": "lora",
            "lora_rank": self.lora_rank,
            "lora_alpha": self.lora_alpha,
            "lora_dropout": self.lora_dropout,
            "lora_target": self.lora_target,
            "quantization_bit": self.quantization_bit,
            "output_dir": output_dir,
            "cutoff_len": self.cutoff_len,
            "per_device_train_batch_size": self.batch_size,
            "gradient_accumulation_steps": self.grad_accum,
            "learning_rate": self.learning_rate,
            "num_train_epochs": self.epochs,
            "lr_scheduler_type": "cosine",
            "warmup_ratio": 0.1,
            "bf16": True,
            "logging_steps": 10,
            "save_steps": 100,
            "plot_loss": True,
        }


@dataclass(slots=True)
class EvalResult:
    """评估结果 (金标准 + evaluator)."""

    task: TaskKind
    n_samples: int
    accuracy: float = 0.0              # 分类/评分命中率
    mae: float | None = None          # 评分回归 MAE (resume_scoring)
    rouge_l: float | None = None      # 摘要 ROUGE-L (hrbp_summary)
    evaluator_score: float | None = None  # Agenta evaluator 综合分 0-1
    passed: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LoRAModel:
    """已训练并注册的 LoRA adapter 元数据."""

    model_id: str                     # e.g. "resume_scoring-v1"
    task: TaskKind
    base_model: str
    adapter_path: str
    version: int = 1
    status: JobStatus = JobStatus.COMPLETED
    eval_accuracy: float = 0.0
    eval_passed: bool = False
    served_url: str | None = None     # vLLM OpenAI 兼容 endpoint
    created_at: float = field(default_factory=time.time)
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task": self.task.value,
            "base_model": self.base_model,
            "adapter_path": self.adapter_path,
            "version": self.version,
            "status": self.status.value,
            "eval_accuracy": round(self.eval_accuracy, 4),
            "eval_passed": self.eval_passed,
            "served_url": self.served_url,
            "created_at": self.created_at,
            "config": self.config,
        }


@dataclass(slots=True)
class TrainingJob:
    """一次完整的微调任务 (贯穿 dataset_prep → train → evaluate → deploy)."""

    job_id: str
    task: TaskKind
    config: LoRAConfig
    status: JobStatus = JobStatus.PENDING
    dataset_path: str | None = None
    n_train: int = 0
    output_dir: str | None = None
    eval: EvalResult | None = None
    model: LoRAModel | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self, status: JobStatus | None = None) -> None:
        if status is not None:
            self.status = status
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "task": self.task.value,
            "status": self.status.value,
            "dataset_path": self.dataset_path,
            "n_train": self.n_train,
            "output_dir": self.output_dir,
            "eval": (
                {
                    "accuracy": self.eval.accuracy,
                    "mae": self.eval.mae,
                    "rouge_l": self.eval.rouge_l,
                    "evaluator_score": self.eval.evaluator_score,
                    "passed": self.eval.passed,
                }
                if self.eval
                else None
            ),
            "model": self.model.to_dict() if self.model else None,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
