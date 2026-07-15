"""OCR providers."""
from __future__ import annotations

from .aliyun_ocr import AliyunOCRProvider
from .baidu_ocr import BaiduOCRProvider
from .base import OCRProvider, OCRResult
from .mock_provider import MockOCRProvider
from .paddle_ocr import PaddleOCRProvider
from .tencent_ocr import TencentOCRProvider

__all__ = [
    "AliyunOCRProvider",
    "BaiduOCRProvider",
    "MockOCRProvider",
    "OCRProvider",
    "OCRResult",
    "PaddleOCRProvider",
    "TencentOCRProvider",
]