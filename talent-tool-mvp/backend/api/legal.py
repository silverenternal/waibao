"""Legal / Compliance 文档 API — T1201.

GET  /api/legal/{type}        返回指定语言版本的法律文档
GET  /api/legal/versions      列出所有可用文档 / 版本

支持 type ∈ {terms, privacy, dpa, cookies}
支持 lang ∈ {zh-CN, en-US, ja-JP}

策略:
- 优先返回 docs/legal/ 下的 Markdown 文件原文
- 文件不存在时,fallback 到 PolicyGenerator 生成的模板
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# 文件位置
# ---------------------------------------------------------------------------

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "legal"

DOC_FILE_MAP: dict[str, dict[str, str]] = {
    "terms": {
        "zh-CN": "TERMS_OF_SERVICE.md",
        "en-US": "TERMS_OF_SERVICE.en.md",
        "en": "TERMS_OF_SERVICE.en.md",
        "zh": "TERMS_OF_SERVICE.md",
        "ja-JP": "TERMS_OF_SERVICE.ja.md",
        "ja": "TERMS_OF_SERVICE.ja.md",
    },
    "privacy": {
        "zh-CN": "PRIVACY_POLICY.md",
        "en-US": "PRIVACY_POLICY.en.md",
        "en": "PRIVACY_POLICY.en.md",
        "zh": "PRIVACY_POLICY.md",
        "ja-JP": "PRIVACY_POLICY.ja.md",
        "ja": "PRIVACY_POLICY.ja.md",
    },
    "dpa": {
        "zh-CN": "DATA_PROCESSING_AGREEMENT.md",
        "en-US": "DATA_PROCESSING_AGREEMENT.md",
        "zh": "DATA_PROCESSING_AGREEMENT.md",
        "en": "DATA_PROCESSING_AGREEMENT.md",
        "ja-JP": "DATA_PROCESSING_AGREEMENT.md",
        "ja": "DATA_PROCESSING_AGREEMENT.md",
    },
    "cookies": {
        "zh-CN": "COOKIE_POLICY.md",
        "en-US": "COOKIE_POLICY.md",
        "zh": "COOKIE_POLICY.md",
        "en": "COOKIE_POLICY.md",
        "ja-JP": "COOKIE_POLICY.md",
        "ja": "COOKIE_POLICY.md",
    },
    "china": {
        "zh-CN": "CHINA_COMPLIANCE.md",
        "en-US": "CHINA_COMPLIANCE.md",
        "zh": "CHINA_COMPLIANCE.md",
        "en": "CHINA_COMPLIANCE.md",
        "ja-JP": "CHINA_COMPLIANCE.md",
        "ja": "CHINA_COMPLIANCE.md",
    },
}


CANONICAL_LANGS = {"zh-CN", "en-US", "ja-JP"}


def _resolve_lang(lang: str | None) -> str:
    """规整化语言标签.

    仅 zh-CN / en-US / ja-JP 三个规范标签;短形式 (zh/en/ja) 自动扩展.
    """
    if not lang:
        return "zh-CN"
    lang = lang.strip()
    if lang in CANONICAL_LANGS:
        return lang
    # 短形式 / 其他 → 扩展
    short = lang.split("-")[0].lower()
    mapping = {
        "zh": "zh-CN",
        "en": "en-US",
        "ja": "ja-JP",
    }
    return mapping.get(short, "zh-CN")


def _read_doc(doc_type: str, lang: str) -> tuple[str, str] | None:
    """读取文档文件,返回 (filename, content) 或 None."""
    lang = _resolve_lang(lang)
    files = DOC_FILE_MAP.get(doc_type, {})
    filename = files.get(lang)
    if not filename:
        return None
    path = DOCS_DIR / filename
    if not path.exists():
        return None
    try:
        return filename, path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        logger.exception(f"legal.read_failed path={path}")
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/legal/versions")
async def list_legal_versions() -> dict[str, Any]:
    """列出所有可用文档及其支持的语言."""
    versions = []
    for doc_type, files in DOC_FILE_MAP.items():
        supported_langs = []
        for lang, fname in files.items():
            path = DOCS_DIR / fname
            if path.exists():
                supported_langs.append({
                    "lang": lang,
                    "file": fname,
                    "size": path.stat().st_size,
                })
        # 只显示规范化的语言
        canonical = [
            l for l in supported_langs
            if l["lang"] in ("zh-CN", "en-US", "ja-JP")
        ]
        versions.append({
            "type": doc_type,
            "languages": canonical,
            "total_variants": len(supported_langs),
        })
    return {
        "versions": versions,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/legal/{doc_type}")
async def get_legal_doc(
    doc_type: str,
    lang: str = Query(default="zh-CN", description="zh-CN / en-US / ja-JP"),
) -> dict[str, Any]:
    """获取指定类型 + 语言的法律文档."""
    if doc_type not in DOC_FILE_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"unknown doc_type: {doc_type}; valid: {list(DOC_FILE_MAP.keys())}",
        )

    lang = _resolve_lang(lang)
    result = _read_doc(doc_type, lang)
    if result is None:
        # fallback 到 en-US
        if lang != "en-US":
            result = _read_doc(doc_type, "en-US")
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"legal doc not found: type={doc_type}, lang={lang}",
            )

    filename, content = result
    return {
        "type": doc_type,
        "lang": lang,
        "filename": filename,
        "content": content,
        "version": "v1.0",
        "effective_at": "2026-07-12",
        "size": len(content),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/legal")
async def legal_root() -> dict[str, Any]:
    """法律文档 API 根索引."""
    return {
        "service": "waibao legal",
        "endpoints": {
            "list_versions": "GET /api/legal/versions",
            "get_doc": "GET /api/legal/{type}?lang=zh-CN|en-US|ja-JP",
        },
        "doc_types": list(DOC_FILE_MAP.keys()),
        "supported_langs": ["zh-CN", "en-US", "ja-JP"],
    }