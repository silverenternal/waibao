"""Mock provider fallback (registry 自动调用).

不实现真实业务,仅保证 provider 协议完整,用于本地无 key 调试。

v10.0 T5004 — MockProvider now declares a :class:`providers.contract.ProviderContract`
with ``mock_enabled=True``. The registry uses the explicit
``WAIBAO_PROVIDER_MOCK`` gate before any real caller receives mock data —
production traffic must never silently degrade.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .contract import ProviderContract
from .exceptions import ProviderError


class MockProvider:
    """通用 mock,所有 ABC 的方法签名都给一个最小占位实现."""

    def __init__(self, contract: str = "llm") -> None:
        self.contract = contract
        self.provider_name = f"mock_{contract}"
        self.channel = f"mock_{contract}"
        # T5004: declare the unified contract. Mock providers are always
        # mock_enabled; the registry enforces the gate before serving them.
        self.provider_contract = ProviderContract(
            name=self.provider_name,
            contract_type=contract,
            mock_enabled=True,
            allow_mock_fallback=False,
            vendor="mock",
        )

    async def chat(self, messages: list[Any], **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
        from .llm.base import LLMResponse, Usage

        return LLMResponse(
            content=f"[mock-{self.contract}] echo: {messages[-1].content if messages else ''}",
            model="mock-model",
            usage=Usage(),
        )

    async def stream_chat(  # type: ignore[no-untyped-def]
        self, messages: list[Any], **kwargs: Any
    ) -> AsyncIterator[str]:
        text = f"[mock-{self.contract}] stream: {messages[-1].content if messages else ''}"
        for ch in text:
            yield ch

    async def tool_call(self, messages: list[Any], tools: list[Any], **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
        from .llm.base import ToolCallResult

        return ToolCallResult(content="[mock] no tool call", tool_calls=[])

    @property
    def supported_models(self) -> list[str]:
        return ["mock-model"]

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return {"mock-model": (0.0, 0.0)}

    async def embed(self, texts: list[str], **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
        from .embedding.base import EmbeddingResult

        return EmbeddingResult(
            vectors=[[0.0] * 8 for _ in texts],
            model="mock-embed",
            dimensions=8,
        )

    async def embed_one(self, text: str, **kwargs: Any) -> list[float]:  # type: ignore[no-untyped-def]
        return [0.0] * 8

    @property
    def dimensions(self) -> int:
        return 8

    async def chat_with_images(self, messages: list[Any], **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
        from .vision.base import VisionResponse

        return VisionResponse(content="[mock-vision]", model="mock-vision")

    async def ocr(self, image: Any, **kwargs: Any) -> str:  # type: ignore[no-untyped-def]
        return "[mock-ocr]"

    async def recognize(self, image: bytes, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
        from .ocr.base import OCRResult

        return OCRResult(text="[mock-ocr]", blocks=[])

    async def recognize_url(self, url: str, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
        from .ocr.base import OCRResult

        return OCRResult(text="[mock-ocr]", blocks=[])

    async def transcribe(self, audio: bytes, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
        from .stt.base import STTResult

        return STTResult(text="[mock-stt]")

    async def transcribe_url(self, url: str, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
        from .stt.base import STTResult

        return STTResult(text="[mock-stt]")

    async def send(self, message: Any) -> Any:  # type: ignore[no-untyped-def]
        from .notify.base import NotifyResult

        return NotifyResult(success=True, channel=f"mock_{self.contract}")

    async def search(self, keyword: str, **kwargs: Any) -> list[Any]:  # type: ignore[no-untyped-def]
        return []

    async def get_detail(self, company_id: str, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
        from .lookup.base import CompanyInfo

        return CompanyInfo(name=f"[mock-lookup] {company_id}")
