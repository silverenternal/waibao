"""T3001: LoRA adapter 部署到 vLLM.

vLLM 支持在启动时通过 ``--enable-lora --lora-modules <name>=<path>`` 动态挂载
LoRA adapter, 并以 OpenAI 兼容协议 (/v1/chat/completions) 提供服务,
请求时把 adapter name 作为 ``model`` 字段即可命中对应 LoRA。

本模块负责:
    - 生成 vLLM 启动命令 (供 infra/training 或 k8s 使用)
    - 通过 vLLM 的 dynamic LoRA load API 热挂载 adapter (若服务在线)
    - 无 vLLM 时 dry_run: 只返回一个约定的 served_url, 让 registry 可登记

部署完成后把 served_url 回写 registry, custom_lora provider 即可路由。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from .registry import get_registry
from .types import JobStatus, LoRAModel, TaskKind, TrainingJob

logger = logging.getLogger("recruittech.training.deploy")

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://vllm:8000")


@dataclass(slots=True)
class DeploySpec:
    """一次 vLLM 部署的描述。"""

    model_id: str
    adapter_path: str
    base_model: str
    served_url: str


def build_vllm_command(
    base_model: str,
    lora_modules: dict[str, str],
    *,
    port: int = 8000,
    max_loras: int = 8,
    max_lora_rank: int = 16,
) -> list[str]:
    """构造 vLLM OpenAI server 启动命令 (多 LoRA)。

    lora_modules: {adapter_name: adapter_path}。
    """
    cmd = [
        "python",
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        base_model,
        "--enable-lora",
        "--max-loras",
        str(max_loras),
        "--max-lora-rank",
        str(max_lora_rank),
        "--port",
        str(port),
    ]
    for name, path in lora_modules.items():
        cmd += ["--lora-modules", f"{name}={path}"]
    return cmd


async def _load_lora_dynamic(model_id: str, adapter_path: str, *, base_url: str) -> bool:
    """调 vLLM 的 /v1/load_lora_adapter 热挂载 (vLLM >=0.6 支持)。"""
    url = f"{base_url.rstrip('/')}/v1/load_lora_adapter"
    payload = {"lora_name": model_id, "lora_path": adapter_path}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("vllm dynamic load failed (%s): %s", url, exc)
        return False


async def deploy(
    job: TrainingJob,
    *,
    base_url: str | None = None,
    dry_run: bool | None = None,
    register: bool = True,
) -> LoRAModel:
    """把训练产物部署到 vLLM 并注册模型。

    Args:
        job: 已 evaluate 完成的 job (需 output_dir + eval)。
        base_url: vLLM 服务地址; 默认 VLLM_BASE_URL。
        dry_run: None=自动 (无法连上 vLLM 则 dry_run)。
        register: 是否写入 ModelRegistry。
    """
    base_url = base_url or VLLM_BASE_URL
    adapter_path = job.output_dir or ""
    model_id = f"{job.task.value}-v1"
    eval_acc = job.eval.accuracy if job.eval else 0.0
    eval_passed = bool(job.eval and job.eval.passed)

    served_url = f"{base_url.rstrip('/')}/v1"
    loaded = False
    if dry_run is None:
        loaded = await _load_lora_dynamic(model_id, adapter_path, base_url=base_url)
        dry_run = not loaded
    elif not dry_run:
        loaded = await _load_lora_dynamic(model_id, adapter_path, base_url=base_url)

    if dry_run:
        logger.info("deploy dry_run task=%s adapter=%s", job.task.value, adapter_path)

    model = LoRAModel(
        model_id=model_id,
        task=job.task,
        base_model=job.config.base_model,
        adapter_path=adapter_path,
        status=JobStatus.COMPLETED,
        eval_accuracy=eval_acc,
        eval_passed=eval_passed,
        served_url=served_url if (loaded or dry_run) else None,
        config={
            "lora_rank": job.config.lora_rank,
            "lora_alpha": job.config.lora_alpha,
            "dry_run": dry_run,
        },
    )
    job.model = model
    job.touch(JobStatus.COMPLETED)
    if register:
        model = get_registry().register(model, activate=eval_passed)
    return model
