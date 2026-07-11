"""OCR Mock Provider — 返回固定占位文字."""
from __future__ import annotations

from typing import Any

from .base import OCRProvider, OCRResult


class MockOCRProvider(OCRProvider):
    """纯本地 mock,不发起任何网络请求."""

    provider_name = "mock"

    async def recognize(
        self,
        image: bytes,
        *,
        mime: str = "image/png",
        language: str = "auto",
        **kwargs: Any,
    ) -> OCRResult:
        text = f"[mock-ocr] bytes={len(image)} mime={mime} lang={language}"
        return OCRResult(
            text=text,
            blocks=[
                {
                    "text": text,
                    "bbox": [0, 0, 100, 20],
                    "confidence": 0.99,
                }
            ],
            confidence=0.99,
        )

    async def recognize_url(
        self,
        url: str,
        *,
        language: str = "auto",
        **kwargs: Any,
    ) -> OCRResult:
        text = f"[mock-ocr] url={url} lang={language}"
        return OCRResult(
            text=text,
            blocks=[
                {
                    "text": text,
                    "bbox": [0, 0, 100, 20],
                    "confidence": 0.99,
                }
            ],
            confidence=0.99,
        )