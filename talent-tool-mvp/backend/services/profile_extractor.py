"""Profile Extractor — 纯 LLM 版,删除所有正则/关键词."""
from __future__ import annotations

import logging

from agents.llm_extractor import extract_resume
from agents.runtime import LLMClient

logger = logging.getLogger("recruittech.services.profile_extractor")


async def extract_profile_from_text(text: str, llm: LLMClient | None = None) -> dict:
    """LLM 抽取简历信息(替代旧正则版本)."""
    return await extract_resume(llm or LLMClient(), text)


async def extract_profile_from_url(url: str, llm: LLMClient | None = None) -> dict:
    """从 URL 抓取 + LLM 抽取."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            text = r.text[:50000]   # 限制大小
        return await extract_profile_from_text(text, llm)
    except Exception as e:
        logger.exception(f"fetch failed: {e}")
        return {"_error": str(e)}


async def ocr_image(url: str) -> str:
    """OCR 图片(MVP 占位)."""
    return f"[OCR-mock for {url}]"


# 兼容性:保留旧函数名,但内部走 LLM
async def parse_email(text: str) -> str | None:
    """保留旧 API 兼容性 — 内部走 LLM 抽取."""
    result = await extract_profile_from_text(text)
    return result.get("basic", {}).get("email", {}).get("value") if isinstance(result.get("basic"), dict) else None


async def parse_phone(text: str) -> str | None:
    result = await extract_profile_from_text(text)
    return result.get("basic", {}).get("phone", {}).get("value") if isinstance(result.get("basic"), dict) else None