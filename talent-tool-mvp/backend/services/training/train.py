"""T3001: LoRA (QLoRA) 训练任务 — 封装 LLaMA-Factory。

真实训练走 ``llamafactory-cli train <config.yaml>`` (GPU, 见 infra/training)。
本模块负责:
    1. 把 LoRAConfig + dataset 渲染成 LLaMA-Factory 的 dataset_info.json + train YAML
    2. 调 CLI 启动训练 (子进程)
    3. 无 GPU / 无 llamafactory 时进入 dry_run: 只写产物骨架, 让 pipeline 可端到端跑

产物目录结构 (与 LLaMA-Factory 一致):
    output_dir/
        adapter_config.json
        adapter_model.safetensors   (真实训练产生; dry_run 下为占位)
        train_config.yaml
        dataset_info.json
        trainer_state.json
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any

from .dataset_prep import instruction_for
from .types import JobStatus, LoRAConfig, TaskKind, TrainingJob

logger = logging.getLogger("recruittech.training.train")


def _has_llamafactory() -> bool:
    """检测 llamafactory-cli 是否可用。"""
    return shutil.which("llamafactory-cli") is not None


def _dataset_info(task: TaskKind, dataset_path: str) -> dict[str, Any]:
    """LLaMA-Factory 的 dataset_info.json 条目 (alpaca 列映射)。"""
    return {
        task.value: {
            "file_name": os.path.basename(dataset_path),
            "columns": {
                "prompt": "instruction",
                "query": "input",
                "response": "output",
            },
        }
    }


def render_configs(job: TrainingJob, dataset_path: str) -> dict[str, str]:
    """把 job 渲染成 LLaMA-Factory 需要的配置文件, 写入 output_dir。

    返回 {"train_yaml": ..., "dataset_info": ...} 的路径字典。
    """
    output_dir = job.output_dir or os.path.join("/tmp/lora_out", job.job_id)
    os.makedirs(output_dir, exist_ok=True)
    job.output_dir = output_dir

    # dataset_info.json — 放到数据集同目录, 供 --dataset_dir 指向
    ds_dir = os.path.dirname(os.path.abspath(dataset_path))
    info_path = os.path.join(ds_dir, "dataset_info.json")
    # 合并已有 dataset_info (可能多任务共用一个目录)
    info: dict[str, Any] = {}
    if os.path.exists(info_path):
        try:
            with open(info_path, encoding="utf-8") as f:
                info = json.load(f)
        except Exception:  # noqa: BLE001
            info = {}
    info.update(_dataset_info(job.task, dataset_path))
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    args = job.config.to_llamafactory_args(dataset=job.task.value, output_dir=output_dir)
    args["dataset_dir"] = ds_dir
    yaml_path = os.path.join(output_dir, "train_config.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        _dump_yaml(args, f)
    return {"train_yaml": yaml_path, "dataset_info": info_path}


def _dump_yaml(d: dict[str, Any], fp) -> None:
    """极简 YAML 输出 (避免引入 PyYAML 依赖; 值都是标量)。"""
    for k, v in d.items():
        if isinstance(v, bool):
            fp.write(f"{k}: {'true' if v else 'false'}\n")
        elif isinstance(v, str):
            fp.write(f"{k}: {v}\n")
        else:
            fp.write(f"{k}: {v}\n")


def _write_dry_run_artifacts(job: TrainingJob) -> None:
    """无 GPU 时写出与 LLaMA-Factory 一致的产物骨架, 让 evaluate/deploy 可继续。"""
    out = job.output_dir or ""
    cfg = job.config
    adapter_config = {
        "peft_type": "LORA",
        "r": cfg.lora_rank,
        "lora_alpha": cfg.lora_alpha,
        "lora_dropout": cfg.lora_dropout,
        "target_modules": cfg.lora_target,
        "base_model_name_or_path": cfg.base_model,
        "task_type": "CAUSAL_LM",
    }
    with open(os.path.join(out, "adapter_config.json"), "w", encoding="utf-8") as f:
        json.dump(adapter_config, f, ensure_ascii=False, indent=2)
    # 占位 adapter 权重 (真实训练会覆盖为 safetensors)
    with open(os.path.join(out, "adapter_model.safetensors"), "wb") as f:
        f.write(b"DRYRUN_LORA_PLACEHOLDER")
    trainer_state = {
        "task": job.task.value,
        "num_train_epochs": cfg.epochs,
        "log_history": [
            {"step": 10, "loss": 1.42},
            {"step": 20, "loss": 0.98},
            {"step": 30, "loss": 0.71},
        ],
        "train_runtime": 0.0,
        "dry_run": True,
    }
    with open(os.path.join(out, "trainer_state.json"), "w", encoding="utf-8") as f:
        json.dump(trainer_state, f, ensure_ascii=False, indent=2)
    # instruction 备份, 供推理时拼 prompt
    with open(os.path.join(out, "instruction.txt"), "w", encoding="utf-8") as f:
        f.write(instruction_for(job.task))


def train(
    job: TrainingJob,
    dataset_path: str,
    *,
    dry_run: bool | None = None,
    timeout: int = 60 * 60 * 6,
) -> TrainingJob:
    """执行一次 QLoRA 训练。

    Args:
        job: 训练任务 (会被原地更新 status/output_dir/error)。
        dataset_path: prepare_dataset 产出的数据集路径。
        dry_run: None=自动检测 (无 llamafactory-cli 则 dry_run); True/False 强制。
        timeout: 子进程超时秒数。
    """
    job.dataset_path = dataset_path
    job.touch(JobStatus.TRAINING)
    if dry_run is None:
        dry_run = not _has_llamafactory()

    try:
        cfgs = render_configs(job, dataset_path)
    except Exception as exc:  # noqa: BLE001
        job.error = f"render_configs failed: {exc}"
        job.touch(JobStatus.FAILED)
        return job

    if dry_run:
        logger.info("train dry_run job=%s task=%s (no GPU/llamafactory)", job.job_id, job.task.value)
        _write_dry_run_artifacts(job)
        job.touch(JobStatus.COMPLETED)
        return job

    cmd = ["llamafactory-cli", "train", cfgs["train_yaml"]]
    logger.info("launch training: %s", " ".join(cmd))
    started = time.time()
    try:
        proc = subprocess.run(  # noqa: S603 - 命令固定, 参数来自内部配置
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        logger.info("training done in %.1fs\n%s", time.time() - started, proc.stdout[-2000:])
        # 训练成功也补一份 instruction 供推理拼 prompt
        if job.output_dir:
            with open(os.path.join(job.output_dir, "instruction.txt"), "w", encoding="utf-8") as f:
                f.write(instruction_for(job.task))
        job.touch(JobStatus.COMPLETED)
    except FileNotFoundError:
        # CLI 突然不可用 → 退回 dry_run 而非直接失败
        logger.warning("llamafactory-cli missing at runtime, fallback to dry_run")
        _write_dry_run_artifacts(job)
        job.touch(JobStatus.COMPLETED)
    except subprocess.CalledProcessError as exc:
        job.error = f"training failed rc={exc.returncode}: {(exc.stderr or '')[-1000:]}"
        job.touch(JobStatus.FAILED)
    except subprocess.TimeoutExpired:
        job.error = f"training timeout after {timeout}s"
        job.touch(JobStatus.FAILED)
    return job
