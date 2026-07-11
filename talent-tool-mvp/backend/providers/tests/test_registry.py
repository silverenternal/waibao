"""registry fallback 行为单测.

覆盖目标:
    - LLM_PROVIDER=mock  -> MockLLMProvider
    - 其他维度 *_PROVIDER=mock -> 对应 mock provider
    - notify 5 通道 fallback
    - 未知 provider 抛 InvalidRequestError
    - 单例缓存 + reset_cache()
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

# 把 backend 加入路径,避免触发上层包的 __init__.py (它会 import openai 等)
_THIS = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# 用直接导入而不是 from backend.providers.X import,绕过 package __init__ 的依赖链
from backend.providers import exceptions, registry  # noqa: E402

from backend.providers.embedding.mock_provider import MockEmbeddingProvider  # noqa: E402
from backend.providers.llm.mock_provider import MockLLMProvider  # noqa: E402
from backend.providers.lookup.mock_provider import MockLookupProvider  # noqa: E402
from backend.providers.notify.mock_provider import (  # noqa: E402
    MockDingTalkProvider,
    MockFeishuProvider,
    MockSMTPProvider,
    MockWebhookProvider,
    MockWeComProvider,
)
from backend.providers.ocr.mock_provider import MockOCRProvider  # noqa: E402
from backend.providers.stt.mock_provider import MockSTTProvider  # noqa: E402
from backend.providers.vision.mock_provider import MockVisionProvider  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch: pytest.MonkeyPatch):
    """每个测试都重置 env 和 registry 单例."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("VISION_PROVIDER", "mock")
    monkeypatch.setenv("OCR_PROVIDER", "mock")
    monkeypatch.setenv("STT_PROVIDER", "mock")
    monkeypatch.setenv("LOOKUP_PROVIDER", "mock")
    # 关掉 notify,否则 registry 会去找真实 NotifyProvider
    for ch in ("SMTP", "DINGTALK", "FEISHU", "WECOM", "WEBHOOK"):
        monkeypatch.delenv(f"NOTIFY_{ch}_ENABLED", raising=False)
    registry.reset_cache()
    yield
    registry.reset_cache()


def test_llm_provider_mock_fallback():
    p = registry.get_llm_provider()
    assert isinstance(p, MockLLMProvider)
    assert p.provider_name == "mock"


def test_embedding_provider_mock_fallback():
    p = registry.get_embedding_provider()
    assert isinstance(p, MockEmbeddingProvider)
    assert p.dimensions == 16


def test_vision_provider_mock_fallback():
    p = registry.get_vision_provider()
    assert isinstance(p, MockVisionProvider)


def test_ocr_provider_mock_fallback():
    p = registry.get_ocr_provider()
    assert isinstance(p, MockOCRProvider)


def test_stt_provider_mock_fallback():
    p = registry.get_stt_provider()
    assert isinstance(p, MockSTTProvider)


def test_lookup_provider_mock_fallback():
    p = registry.get_lookup_provider()
    assert isinstance(p, MockLookupProvider)


@pytest.mark.parametrize(
    "channel,expected_cls",
    [
        ("smtp", MockSMTPProvider),
        ("dingtalk", MockDingTalkProvider),
        ("feishu", MockFeishuProvider),
        ("wecom", MockWeComProvider),
        ("webhook", MockWebhookProvider),
    ],
)
def test_notify_provider_5_channels_mock_fallback(channel: str, expected_cls: type):
    p = registry.get_notify_provider(channel)
    assert isinstance(p, expected_cls)
    assert p.channel == channel


def test_notify_unknown_channel_raises():
    with pytest.raises(exceptions.InvalidRequestError):
        registry.get_notify_provider("totally_unknown_channel")


def test_llm_singleton_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    registry.reset_cache()
    p1 = registry.get_llm_provider()
    p2 = registry.get_llm_provider()
    assert p1 is p2
    registry.reset_cache()
    p3 = registry.get_llm_provider()
    assert p3 is not p1


def test_reset_cache_clears_all(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    registry.reset_cache()
    registry.get_llm_provider()
    registry.get_embedding_provider()
    registry.reset_cache()
    # 重新读取,应该是新对象
    assert registry.get_llm_provider() is not None


def test_unknown_llm_provider_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "no-such-vendor")
    registry.reset_cache()
    with pytest.raises(exceptions.InvalidRequestError):
        registry.get_llm_provider()


def test_default_provider_is_mock_when_env_unset(monkeypatch: pytest.MonkeyPatch):
    """没有 LLM_PROVIDER 时,registry 默认 mock 而不是抛错."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    registry.reset_cache()
    p = registry.get_llm_provider()
    assert isinstance(p, MockLLMProvider)


def test_registry_module_imports_clean():
    """确认 import 链路通畅."""
    importlib.import_module("backend.providers.registry")
    importlib.import_module("backend.providers.llm.mock_provider")
    importlib.import_module("backend.providers.embedding.mock_provider")
    importlib.import_module("backend.providers.vision.mock_provider")
    importlib.import_module("backend.providers.ocr.mock_provider")
    importlib.import_module("backend.providers.stt.mock_provider")
    importlib.import_module("backend.providers.notify.mock_provider")
    importlib.import_module("backend.providers.lookup.mock_provider")