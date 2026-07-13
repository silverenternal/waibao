"""T3001: Custom LoRA Provider — 加载 LoRA adapter + OpenAI 兼容推理.

微调产出的 LoRA adapter 由 vLLM 以 OpenAI 兼容协议提供服务
(vLLM ``--enable-lora``, 请求时把 adapter name 作为 ``model``)。

本 provider:
    - 从 ModelRegistry 解析 task → active adapter (model_id + served_url)
    - 走 OpenAI SDK (base_url 指向 vLLM) 发 chat/completions
    - 无 vLLM / adapter 未部署时进入本地 heuristic fallback, 保证离线可用
    - 额外提供 score_resume / review_bias / summarize_ticket 三个任务快捷方法

与其他 LLMProvider 一致继承 base.LLMProvider, 可被 registry.get_llm_provider 复用。
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import (
    LLMProvider,
    LLMResponse,
    Message,
    ToolCall,
    ToolCallResult,
    ToolDefinition,
    Usage,
)

logger = logging.getLogger("recruittech.providers.custom_lora")

# 任务名 → registry TaskKind (延迟导入避免 services 依赖)
_TASK_ALIASES = {
    "resume_scoring": "resume_scoring",
    "resume": "resume_scoring",
    "bias_review": "bias_review",
    "bias": "bias_review",
    "hrbp_summary": "hrbp_summary",
    "summary": "hrbp_summary",
}


def _resolve_task(name: str):
    from services.training.types import TaskKind

    key = _TASK_ALIASES.get(name.lower(), name.lower())
    return TaskKind(key)


class CustomLoRAProvider(LLMProvider):
    """加载微调 LoRA adapter 并以 OpenAI 兼容协议推理。"""

    provider_name = "custom_lora"

    DEFAULT_BASE_URL: ClassVar[str] = os.getenv("VLLM_BASE_URL", "http://vllm:8000") + "/v1"
    DEFAULT_MODEL: ClassVar[str] = "resume_scoring-v1"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        default_model: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        # vLLM 不校验 key, 但 OpenAI SDK 需要非空值
        self.api_key = api_key or os.getenv("VLLM_API_KEY") or "EMPTY"
        self.base_url = base_url or os.getenv("VLLM_BASE_URL_FULL") or self.DEFAULT_BASE_URL
        self.default_model = default_model or self.DEFAULT_MODEL
        self._client = None  # 延迟构造

    # ---- OpenAI client (延迟) ----
    @property
    def client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    # ---- protocol ----
    @property
    def supported_models(self) -> list[str]:
        """已注册的 adapter model_id 列表 (registry)。"""
        try:
            from services.training.registry import get_registry

            return [m.model_id for m in get_registry().list()] or [self.default_model]
        except Exception:  # noqa: BLE001
            return [self.default_model]

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        # 自托管 LoRA: 无 API 费用 (只有算力成本, 不在此计价)
        return {m: (0.0, 0.0) for m in self.supported_models}

    # ---- adapter 解析 ----
    def resolve_adapter(self, task: str) -> tuple[str, str | None]:
        """task → (model_id, served_url); 未部署时 model_id 回退默认。"""
        try:
            from services.training.registry import get_registry

            kind = _resolve_task(task)
            model = get_registry().active(kind) or get_registry().latest(kind)
            if model is not None:
                return model.model_id, model.served_url
        except Exception as exc:  # noqa: BLE001
            logger.debug("resolve_adapter fallback: %s", exc)
        return f"{task}-v1", None

    # ---- serialize ----
    @staticmethod
    def _serialize_messages(messages: list[Message]) -> list[dict[str, Any]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    # ---- chat ----
    @with_resilience(provider="custom_lora", method="chat", rate_per_sec=20.0, burst=40)
    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[ToolDefinition] | None = None,
        response_format: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        model = model or self.default_model
        # model 可能是任务名或 model_id; 若是任务别名, 解析出 served adapter
        served_url = None
        if "-v" not in model:
            model, served_url = self.resolve_adapter(model)

        params: dict[str, Any] = {
            "model": model,
            "messages": self._serialize_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            params["response_format"] = response_format
        params.update(kwargs)
        try:
            resp = await self.client.chat.completions.create(**params)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - vLLM 未就绪 → 本地 fallback
            logger.warning("custom_lora chat fallback (vllm unavailable): %s", exc)
            return self._local_fallback(model, messages)
        return self._parse(resp, model)

    def _parse(self, resp: Any, model: str) -> LLMResponse:
        choice = resp.choices[0]
        usage = Usage(
            prompt_tokens=getattr(resp.usage, "prompt_tokens", 0) if resp.usage else 0,
            completion_tokens=getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0,
            total_tokens=getattr(resp.usage, "total_tokens", 0) if resp.usage else 0,
        )
        return LLMResponse(
            content=choice.message.content or "",
            model=getattr(resp, "model", model),
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            raw=resp,
        )

    def _local_fallback(self, model: str, messages: list[Message]) -> LLMResponse:
        """vLLM 不可用时的确定性本地推理 (启发式), 保证服务不中断。"""
        task = model.split("-v")[0]
        user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        try:
            content = _heuristic(task, user)
        except Exception:  # noqa: BLE001
            content = ""
        return LLMResponse(
            content=content,
            model=model,
            finish_reason="stop",
            usage=Usage(prompt_tokens=len(user) // 2, completion_tokens=len(content) // 2),
        )

    # ---- stream ----
    async def stream_chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        resp = await self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs)
        for ch in resp.content:
            yield ch

    # ---- tool_call (LoRA adapter 通常不做工具调用) ----
    async def tool_call(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> ToolCallResult:
        resp = await self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)
        return ToolCallResult(content=resp.content, tool_calls=[], finish_reason=resp.finish_reason)

    # ---- 任务快捷方法 ----
    async def score_resume(self, job: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        """简历评分 LoRA。返回 {score, reason}。"""
        from services.training.dataset_prep import instruction_for
        from services.training.types import TaskKind

        payload = json.dumps({"job": job, "candidate": candidate}, ensure_ascii=False, sort_keys=True)
        resp = await self.chat(
            [
                Message(role="system", content=instruction_for(TaskKind.RESUME_SCORING)),
                Message(role="user", content=payload),
            ],
            model="resume_scoring",
            temperature=0.0,
        )
        return _safe_json(resp.content)

    async def review_bias(self, text: str) -> dict[str, Any]:
        """偏见审查 LoRA。返回 {label, categories}。"""
        from services.training.dataset_prep import instruction_for
        from services.training.types import TaskKind

        resp = await self.chat(
            [
                Message(role="system", content=instruction_for(TaskKind.BIAS_REVIEW)),
                Message(role="user", content=text),
            ],
            model="bias_review",
            temperature=0.0,
        )
        return _safe_json(resp.content)

    async def summarize_ticket(self, ticket_text: str) -> str:
        """HRBP 摘要 LoRA。返回摘要文本。"""
        from services.training.dataset_prep import instruction_for
        from services.training.types import TaskKind

        resp = await self.chat(
            [
                Message(role="system", content=instruction_for(TaskKind.HRBP_SUMMARY)),
                Message(role="user", content=ticket_text),
            ],
            model="hrbp_summary",
            temperature=0.3,
        )
        return resp.content


# ---------------------------------------------------------------------------
# 本地 fallback 启发式 (vLLM 不可用时)
# ---------------------------------------------------------------------------
def _safe_json(s: str) -> dict[str, Any]:
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {"value": obj}
    except Exception:  # noqa: BLE001
        return {"_raw": s}


def _heuristic(task: str, user: str) -> str:
    if task == "resume_scoring":
        try:
            obj = json.loads(user)
            cand = obj.get("candidate", {})
            years = int(cand.get("years", 3))
            skills = cand.get("skills", [])
            score = min(100, 40 + years * 4 + len(skills) * 3)
            return json.dumps({"score": score, "reason": "local heuristic"}, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            return json.dumps({"score": 60, "reason": "fallback"}, ensure_ascii=False)
    if task == "bias_review":
        cats = []
        if any(k in user for k in ("985", "211", "院校", "学校")):
            cats.append("院校")
        if any(k in user for k in ("男", "女", "性别")):
            cats.append("性别")
        if any(k in user for k in ("岁", "年龄")):
            cats.append("年龄")
        label = "biased" if cats else "clean"
        return json.dumps({"label": label, "categories": cats}, ensure_ascii=False)
    # hrbp_summary
    return (user or "")[:60]


def get_custom_lora_provider() -> CustomLoRAProvider:
    """便捷构造 (无副作用单例交给上层 registry 处理)。"""
    return CustomLoRAProvider()
