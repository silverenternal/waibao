"""Provider 注册中心.

所有 Provider 实例都通过 registry 懒加载 + 单例获取。
切换供应商只需修改环境变量,无需改业务代码。
"""
from __future__ import annotations

import os
from threading import Lock
from typing import Any

from .exceptions import InvalidRequestError

# 单例容器
_llm: Any | None = None
_embedding: Any | None = None
_vision: Any | None = None
_ocr: Any | None = None
_stt: Any | None = None
_notify: dict[str, Any] = {}
_lookup: Any | None = None
_job_market: Any | None = None  # T607 招聘市场供应商

_lock = Lock()


def _mock_provider(contract: str) -> Any:
    """根据 contract 分发到对应的 typed mock provider.

    contract 取值: llm / embedding / vision / ocr / stt / lookup.
    notify 不走这里 (registry 走自己的 5 通道逻辑).
    """
    if contract == "llm":
        from .llm.mock_provider import MockLLMProvider

        return MockLLMProvider()
    if contract == "embedding":
        from .embedding.mock_provider import MockEmbeddingProvider

        return MockEmbeddingProvider()
    if contract == "vision":
        from .vision.mock_provider import MockVisionProvider

        return MockVisionProvider()
    if contract == "ocr":
        from .ocr.mock_provider import MockOCRProvider

        return MockOCRProvider()
    if contract == "stt":
        from .stt.mock_provider import MockSTTProvider

        return MockSTTProvider()
    if contract == "lookup":
        from .lookup.mock_provider import MockLookupProvider

        return MockLookupProvider()
    if contract == "job_market":  # T607
        from .job_market.mock import MockJobMarketProvider

        return MockJobMarketProvider()
    # 兜底:走旧的通用 mock (保底)
    from . import mock as _mock

    if not hasattr(_mock, "MockProvider"):
        raise InvalidRequestError(
            f"providers.mock.MockProvider 不存在,无法 fallback {contract}",
        )
    return _mock.MockProvider(contract=contract)


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
def get_llm_provider() -> Any:
    """根据 LLM_PROVIDER env 返回对应 LLMProvider."""
    global _llm
    if _llm is not None:
        return _llm
    with _lock:
        if _llm is not None:
            return _llm
        name = (os.getenv("LLM_PROVIDER") or "mock").lower()
        if name == "mock":
            _llm = _mock_provider("llm")
            return _llm
        from .llm import (
            AnthropicProvider,
            DeepSeekProvider,
            MoonshotProvider,
            OpenAIProvider,
            TongyiProvider,
            ZhipuProvider,
        )

        mapping = {
            "openai": OpenAIProvider,
            "anthropic": AnthropicProvider,
            "deepseek": DeepSeekProvider,
            "zhipu": ZhipuProvider,
            "tongyi": TongyiProvider,
            "moonshot": MoonshotProvider,
        }
        cls = mapping.get(name)
        if cls is None:
            raise InvalidRequestError(
                f"unknown LLM_PROVIDER={name}", details={"supported": list(mapping)}
            )
        _llm = cls()
    return _llm


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
def get_embedding_provider() -> Any:
    """根据 EMBEDDING_PROVIDER env 返回对应 EmbeddingProvider."""
    global _embedding
    if _embedding is not None:
        return _embedding
    with _lock:
        if _embedding is not None:
            return _embedding
        name = (os.getenv("EMBEDDING_PROVIDER") or "mock").lower()
        if name == "mock":
            _embedding = _mock_provider("embedding")
            return _embedding
        from .embedding import (
            OpenAIEmbeddingProvider,
            TongyiEmbeddingProvider,
            ZhipuEmbeddingProvider,
        )

        mapping = {
            "openai": OpenAIEmbeddingProvider,
            "zhipu": ZhipuEmbeddingProvider,
            "tongyi": TongyiEmbeddingProvider,
        }
        cls = mapping.get(name)
        if cls is None:
            raise InvalidRequestError(
                f"unknown EMBEDDING_PROVIDER={name}",
                details={"supported": list(mapping)},
            )
        _embedding = cls()
    return _embedding


# ---------------------------------------------------------------------------
# Vision
# ---------------------------------------------------------------------------
def get_vision_provider() -> Any:
    """根据 VISION_PROVIDER env 返回对应 VisionProvider."""
    global _vision
    if _vision is not None:
        return _vision
    with _lock:
        if _vision is not None:
            return _vision
        name = (os.getenv("VISION_PROVIDER") or "mock").lower()
        if name == "mock":
            _vision = _mock_provider("vision")
            return _vision
        from .vision import GPT4VProvider, QwenVLProvider

        mapping = {
            "gpt4v": GPT4VProvider,
            "qwen_vl": QwenVLProvider,
        }
        cls = mapping.get(name)
        if cls is None:
            raise InvalidRequestError(
                f"unknown VISION_PROVIDER={name}",
                details={"supported": list(mapping)},
            )
        _vision = cls()
    return _vision


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
def get_ocr_provider() -> Any:
    """根据 OCR_PROVIDER env 返回对应 OCRProvider."""
    global _ocr
    if _ocr is not None:
        return _ocr
    with _lock:
        if _ocr is not None:
            return _ocr
        name = (os.getenv("OCR_PROVIDER") or "mock").lower()
        if name == "mock":
            _ocr = _mock_provider("ocr")
            return _ocr
        # OCR_PROVIDER=gpt4v 表示复用 VisionProvider 的 OCR 能力
        if name == "gpt4v":
            _ocr = get_vision_provider()
            return _ocr
        from .ocr import AliyunOCRProvider, BaiduOCRProvider, TencentOCRProvider

        mapping = {
            "tencent": TencentOCRProvider,
            "baidu": BaiduOCRProvider,
            "aliyun": AliyunOCRProvider,
        }
        cls = mapping.get(name)
        if cls is None:
            raise InvalidRequestError(
                f"unknown OCR_PROVIDER={name}", details={"supported": list(mapping)}
            )
        _ocr = cls()
    return _ocr


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------
def get_stt_provider() -> Any:
    """根据 STT_PROVIDER env 返回对应 STTProvider."""
    global _stt
    if _stt is not None:
        return _stt
    with _lock:
        if _stt is not None:
            return _stt
        name = (os.getenv("STT_PROVIDER") or "mock").lower()
        if name == "mock":
            _stt = _mock_provider("stt")
            return _stt
        from .stt import AliyunSTTProvider, WhisperProvider

        mapping = {
            "whisper": WhisperProvider,
            "aliyun": AliyunSTTProvider,
        }
        cls = mapping.get(name)
        if cls is None:
            raise InvalidRequestError(
                f"unknown STT_PROVIDER={name}", details={"supported": list(mapping)}
            )
        _stt = cls()
    return _stt


# ---------------------------------------------------------------------------
# Notify
# ---------------------------------------------------------------------------
def get_notify_provider(channel: str) -> Any:
    """按 channel (smtp/dingtalk/feishu/wecom/webhook) 返回 NotifyProvider.

    通过 env 决定是否启用:NOTIFY_<CHANNEL>_ENABLED=true.
    未启用 / 未知 channel 时,fallback 到对应 mock channel provider.
    """
    if channel in _notify:
        return _notify[channel]
    with _lock:
        if channel in _notify:
            return _notify[channel]
        from .notify import (
            DingTalkProvider,
            FeishuProvider,
            SMTPProvider,
            WeComProvider,
            WebhookProvider,
        )

        mapping = {
            "smtp": SMTPProvider,
            "dingtalk": DingTalkProvider,
            "feishu": FeishuProvider,
            "wecom": WeComProvider,
            "webhook": WebhookProvider,
        }
        cls = mapping.get(channel)
        if cls is None:
            raise InvalidRequestError(
                f"unknown notify channel={channel}",
                details={"supported": list(mapping)},
            )
        env_key = f"NOTIFY_{channel.upper()}_ENABLED"
        if os.getenv(env_key, "").lower() not in ("1", "true", "yes"):
            from .notify.mock_provider import get_mock_notify_provider

            _notify[channel] = get_mock_notify_provider(channel)
            return _notify[channel]
        _notify[channel] = cls()
    return _notify[channel]


# ---------------------------------------------------------------------------
# CompanyLookup
# ---------------------------------------------------------------------------
def get_lookup_provider() -> Any:
    """根据 LOOKUP_PROVIDER env 返回对应 CompanyLookupProvider."""
    global _lookup
    if _lookup is not None:
        return _lookup
    with _lock:
        if _lookup is not None:
            return _lookup
        name = (os.getenv("LOOKUP_PROVIDER") or "mock").lower()
        if name == "mock":
            _lookup = _mock_provider("lookup")
            return _lookup
        from .lookup import QichachaProvider, TianyanchaProvider

        mapping = {
            "tianyancha": TianyanchaProvider,
            "qichacha": QichachaProvider,
        }
        cls = mapping.get(name)
        if cls is None:
            raise InvalidRequestError(
                f"unknown LOOKUP_PROVIDER={name}",
                details={"supported": list(mapping)},
            )
        _lookup = cls()
    return _lookup


# ---------------------------------------------------------------------------
# JobMarket (T607)
# ---------------------------------------------------------------------------
def get_job_market_provider() -> Any:
    """根据 JOB_MARKET_PROVIDER env 返回对应 JobMarketProvider.

    默认 mock. 真实供应商 (boss / lagou / linkedin / adzuna) 由后续任务实现.
    """
    global _job_market
    if _job_market is not None:
        return _job_market
    with _lock:
        if _job_market is not None:
            return _job_market
        name = (os.getenv("JOB_MARKET_PROVIDER") or "mock").lower()
        if name == "mock":
            _job_market = _mock_provider("job_market")
            return _job_market
        from .job_market.registry import get_job_market_provider as _real_router

        # 真实供应商的注册在 job_market 子包内 (避免循环导入)
        _job_market = _real_router()
    return _job_market


# ---------------------------------------------------------------------------
# 重置 (测试用)
# ---------------------------------------------------------------------------
def reset_cache() -> None:
    """清空所有 provider 单例,主要用于单元测试."""
    global _llm, _embedding, _vision, _ocr, _stt, _lookup, _job_market
    with _lock:
        _llm = _embedding = _vision = _ocr = _stt = _lookup = _job_market = None
        _notify.clear()
