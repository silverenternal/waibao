"""T3001: LoRA 模型注册中心.

进程内单例, 记录每个任务已训练的 LoRA adapter, 支持:
    - register: 训练完成后登记 (自增版本号)
    - get / latest: 按 model_id 或 task 取最新
    - list: 全量列出
    - promote: 标记某版本为该 task 的 active (推理默认走它)

生产环境应替换为 Supabase 表 (lora_models), 这里用内存实现让测试无外部依赖。
"""
from __future__ import annotations

import threading
from typing import Optional

from .types import JobStatus, LoRAModel, TaskKind


class ModelRegistry:
    """LoRA adapter 注册表 (线程安全, 内存实现)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._models: dict[str, LoRAModel] = {}
        # task -> 当前 active model_id
        self._active: dict[TaskKind, str] = {}

    # ---- 写 ----
    def register(self, model: LoRAModel, *, activate: bool = True) -> LoRAModel:
        """登记一个新 adapter; 若同 task 已有则自增版本号。"""
        with self._lock:
            existing = [m for m in self._models.values() if m.task == model.task]
            if existing:
                model.version = max(m.version for m in existing) + 1
            # model_id 若冲突, 追加版本后缀保证唯一
            if model.model_id in self._models:
                model.model_id = f"{model.task.value}-v{model.version}"
            self._models[model.model_id] = model
            if activate and model.eval_passed:
                self._active[model.task] = model.model_id
            return model

    def promote(self, model_id: str) -> LoRAModel:
        """把某版本设为该 task 的 active。"""
        with self._lock:
            m = self._models.get(model_id)
            if m is None:
                raise KeyError(f"unknown model_id={model_id}")
            self._active[m.task] = model_id
            return m

    def set_served_url(self, model_id: str, url: str) -> None:
        with self._lock:
            m = self._models.get(model_id)
            if m is not None:
                m.served_url = url
                m.status = JobStatus.COMPLETED

    # ---- 读 ----
    def get(self, model_id: str) -> Optional[LoRAModel]:
        with self._lock:
            return self._models.get(model_id)

    def latest(self, task: TaskKind) -> Optional[LoRAModel]:
        """返回该 task 版本号最大的 adapter。"""
        with self._lock:
            candidates = [m for m in self._models.values() if m.task == task]
            if not candidates:
                return None
            return max(candidates, key=lambda m: m.version)

    def active(self, task: TaskKind) -> Optional[LoRAModel]:
        """返回该 task 当前 active adapter (未指定则回退到 latest passed)。"""
        with self._lock:
            mid = self._active.get(task)
            if mid and mid in self._models:
                return self._models[mid]
            passed = [
                m for m in self._models.values() if m.task == task and m.eval_passed
            ]
            if not passed:
                return None
            return max(passed, key=lambda m: m.version)

    def list(self, *, task: TaskKind | None = None) -> list[LoRAModel]:
        with self._lock:
            out = list(self._models.values())
            if task is not None:
                out = [m for m in out if m.task == task]
            return sorted(out, key=lambda m: (m.task.value, m.version))

    def clear(self) -> None:
        with self._lock:
            self._models.clear()
            self._active.clear()


_registry: ModelRegistry | None = None
_lock = threading.Lock()


def get_registry() -> ModelRegistry:
    """进程内单例。"""
    global _registry
    if _registry is not None:
        return _registry
    with _lock:
        if _registry is None:
            _registry = ModelRegistry()
    return _registry


def reset_registry() -> None:
    """清空单例, 主要用于单元测试。"""
    global _registry
    with _lock:
        _registry = None
