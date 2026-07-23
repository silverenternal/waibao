"""简历解析服务.

功能链路:
    file_url → OCR (默认 OCR_PROVIDER) → OCRResult.text
                            ↓ 失败 fallback
                            Vision (LLM Vision OCR) → str
                            ↓ 失败 fallback
                            报错 (要求用户提供 .txt)

    OCR result (text) + (可选 hint) → LLM 抽取 → structured profile dict

主入口:
    parse_resume_from_url(url, *, llm=None, hint=None) -> dict
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx

from agents.llm_extractor import extract_resume
from agents.runtime import LLMClient

logger = logging.getLogger("recruittech.services.resume_parser")


# ---------- 1. 拉远程文件 ----------

async def _fetch_bytes(url: str, *, timeout: float = 30.0) -> bytes:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content


def _is_probably_text(data: bytes) -> bool:
    """粗略判断字节流是不是文本 (用于纯 .txt 简历)。"""
    if not data:
        return False
    sample = data[:512]
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        pass
    try:
        sample.decode("latin-1")
        # 再剔除控制字符比例
        ctrl = sum(1 for ch in sample if ord(ch) < 8 and ch not in (b"\n", b"\r", b"\t"))
        return ctrl / max(len(sample), 1) < 0.05
    except Exception:  # noqa: BLE001
        return False


# ---------- 2. OCR ----------

async def _ocr_via_registry(url: str, *, language: str = "auto") -> str:
    """通过 providers.registry.get_ocr_provider() 调用 OCR."""
    from providers.registry import get_ocr_provider

    provider = get_ocr_provider()
    res = await provider.recognize_url(url, language=language)
    return res.text or ""


async def _vision_fallback(url: str) -> str:
    """OCR 失败时的兜底 — 用 Vision provider 把图片当文字转录."""
    try:
        from providers.registry import get_vision_provider
        from providers.vision.base import ImageInput

        vision = get_vision_provider()
        img = ImageInput(url=url)
        return await vision.ocr(img)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"vision OCR fallback failed: {e}")
        return ""


async def extract_text_from_url(url: str, *, language: str = "auto") -> str:
    """Extract raw text from a file URL.

    流程:
    1) 拉字节流
    2) 如果像文本 (pdf/txt/csv) — 直接返回解码结果
    3) 否则走 OCR (OCR_PROVIDER) — 失败 fallback Vision
    4) 仍失败抛 ProviderError
    """
    data = await _fetch_bytes(url)

    # 文本路径
    if _is_probably_text(data):
        return data.decode("utf-8", errors="replace")

    # OCR 路径
    try:
        text = await _ocr_via_registry(url, language=language)
        if text and text.strip():
            return text
        logger.warning("OCR returned empty text, trying vision fallback")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"OCR via registry failed: {e}; falling back to vision")

    # Vision fallback
    text = await _vision_fallback(url)
    if not text:
        from providers.exceptions import ProviderError

        raise ProviderError(
            f"failed to extract text from {url} (OCR + Vision both empty)",
            provider="resume_parser",
        )
    return text


# ---------- 3. LLM 抽取 ----------

# v11.6: resume 提取 schema 已统一到 agents/schemas.py (RESUME_SCHEMA),
# 此处不再保留 inline 副本以避免字段漂移复发.


async def _post_process(structured: dict) -> dict:
    """轻微清洗 — 规范化 email / phone / years.

    T1202 — basic 字段(name/email/phone/location)走 PII 字段加密.
    """
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    phone_re = re.compile(r"(\+?\d[\d\s\-]{8,}\d)")

    basic = structured.get("basic") or {}
    if isinstance(basic, dict):
        for k in ("name", "email", "phone", "location"):
            v = basic.get(k)
            if isinstance(v, dict):
                basic[k] = v.get("value") if v.get("value") is not None else ""
            elif v is None:
                basic[k] = ""
        # email regex safety net
        if not basic.get("email"):
            m = email_re.search(json.dumps(structured, ensure_ascii=False))
            if m:
                basic["email"] = m.group(0)
        if not basic.get("phone"):
            m = phone_re.search(json.dumps(structured, ensure_ascii=False))
            if m:
                basic["phone"] = m.group(1).strip()
        # T1202: 加密 PII 字段(name/email/phone).
        # NOTE: must pass the *actual dict keys* produced by the LLM schema
        # (name/email/phone). The canonical PII registry resolves "name" as an
        # alias of "full_name", so encrypting the "name" key is correct — the
        # earlier "full_name" key never existed in `basic`, so the candidate
        # name was stored in plaintext. (PII leak fix.)
        try:
            from services.pii_field_encryption import get_pii_field_service

            pii_svc = get_pii_field_service()
            basic = pii_svc.encrypt_pii_fields(
                basic,
                fields=["name", "email", "phone"],
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"pii_encrypt_in_resume_failed: {e}")
        structured["basic"] = basic

    # experience durations
    for e in structured.get("experience") or []:
        if isinstance(e, dict) and isinstance(e.get("duration_months"), str):
            try:
                e["duration_months"] = int(float(e["duration_months"]))
            except (ValueError, TypeError):
                e["duration_months"] = 0
    for s in structured.get("skills") or []:
        if isinstance(s, dict) and isinstance(s.get("years"), str):
            try:
                s["years"] = int(float(s["years"]))
            except (ValueError, TypeError):
                s["years"] = 0
    return structured


# ---------- 4. 主入口 ----------

def _has_meaningful_fields(extracted: Any) -> bool:
    """判断 LLM 抽取结果里是否至少有一个可用字段 (非空 basic/skills/experience/...).

    用于区分"真成功"与"LLM 返回空结构 / {} / 全 null" — 后者是 silent-failure
    的最坏情况: 本地 LLM JSON 解析脆弱,空 {} 看起来像成功但实际没提取到任何东西.
    """
    if not isinstance(extracted, dict):
        return False
    basic = extracted.get("basic")
    if isinstance(basic, dict) and any(
        str(v).strip() for v in basic.values() if not isinstance(v, (dict, list))
    ):
        return True
    for k in ("skills", "experience", "education", "highlights", "red_flags"):
        items = extracted.get(k)
        if isinstance(items, list) and items:
            return True
    if extracted.get("overall_impression"):
        return True
    return False


async def parse_resume_from_url(
    url: str,
    *,
    llm: LLMClient | None = None,
    hint: dict[str, Any] | None = None,
    language: str = "auto",
) -> dict:
    """High-level: 从 file_url 解析出结构化简历.

    Returns:
        {
            "source_url": "...",
            "raw_text": "...",        # OCR / 文件原文
            "language": "auto",
            "extracted": {...},       # LLM 结构化结果
            "provider_chain": ["ocr", "llm"],   # 实际触发的链路
            "ocr_provider": "tencent",          # OCR_PROVIDER env
            "status": "ok" | "extract_failed",  # 提取是否真成功 (silent-failure 防护)
            "ok": bool,                         # status == "ok" 的便捷布尔
            "errors": [str, ...],               # 任何降级/失败原因 (空列表=全成功)
        }

    失败语义 (合同要求: 证件/字段无法求证 → 标记而非假装成功):
        - OCR/文本提取失败 → 直接 raise ProviderError (上游决定"待上传").
        - LLM 抽取失败/返回空结构 → status="extract_failed", errors 记录原因,
          extracted 仍返回 (可能含 _error) 供 debug, 但 ok=False 让调用方
          (profile_agent / 身份验证) 走"待上传/人工补录"分支, 而非当成有效画像.
    """
    chain: list[str] = []
    errors: list[str] = []

    raw_text = await extract_text_from_url(url, language=language)
    chain.append("ocr")

    # 记录实际触发的 provider name (无副作用; mock 仅 dev, 合同要求本地 Paddle)
    ocr_provider_name = (os.getenv("OCR_PROVIDER") or "mock").lower()
    if ocr_provider_name == "mock":
        chain.append("ocr:mock")
        errors.append("ocr_provider=mock — 返回占位文字, 非真实 OCR (仅 dev)")

    # 跑到这里说明 OCR 成功(主路径或 vision fallback)
    if "ocr:mock" not in chain:
        try:
            from providers.registry import get_ocr_provider

            prov = get_ocr_provider()
            if getattr(prov, "provider_name", "") == "gpt4v":
                chain.append("vision:gpt4v")
        except Exception as e:  # noqa: BLE001 — provider 探测失败不影响主链路
            logger.warning(f"ocr provider introspection failed: {e}")

    # LLM 抽取
    _llm = llm or LLMClient()
    extracted = await extract_resume(_llm, raw_text)
    chain.append("llm")

    # ---- silent-failure 防护: 区分真成功 vs 空/垃圾 ----
    llm_failed = not isinstance(extracted, dict) or "_error" in (extracted or {})
    if llm_failed:
        reason = (extracted or {}).get("_error") if isinstance(extracted, dict) else "non-dict"
        errors.append(f"llm_extract_failed: {reason}")
        logger.warning("resume LLM extraction failed (kept extracted for debug): %s", reason)
    else:
        if not _has_meaningful_fields(extracted):
            errors.append("llm_extract_empty: LLM 返回空结构 (无可用字段)")
            logger.warning("resume LLM extraction returned empty structure for %s", url)
        try:
            extracted = await _post_process(extracted)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"post_process failed: {e}")
            errors.append(f"post_process_failed: {e}")

    ok = not errors or all("ocr_provider=mock" in e for e in errors)
    # mock-only 是预期的 dev 降级, 不算 extract 失败; 但任何 llm/空结构错误都 = 失败
    has_real_error = any(
        ("llm_extract" in e or "post_process" in e) for e in errors
    )

    return {
        "source_url": url,
        "raw_text": raw_text,
        "language": language,
        "extracted": extracted,
        "provider_chain": chain,
        "ocr_provider": os.getenv("OCR_PROVIDER") or "mock",
        "llm_provider": _llm.provider.provider_name if hasattr(_llm, "provider") else "unknown",
        # 新增 (向后兼容): 显式状态, 杜绝"空 {} 当成功"
        "status": "ok" if not has_real_error else "extract_failed",
        "ok": not has_real_error,
        "errors": errors,
    }


# ---------- 5. 便捷同步 wrapper (供需要同步接口的代码使用) ----------

def parse_resume_sync(url: str, **kwargs: Any) -> dict:
    """同步便捷 wrapper — 内部走 asyncio.run."""
    return asyncio.run(parse_resume_from_url(url, **kwargs))
