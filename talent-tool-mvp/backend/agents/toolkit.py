"""智能体工具包 — 常用 Tool 集合.

供各 Agent 注册使用,包括:
- db_query: Supabase 查询
- llm_call: LLM 调用
- notify: 推送通知
- search_web: 网页搜索 (mock)
"""
from __future__ import annotations

import logging
from typing import Any

from supabase import Client

from agents.runtime import LLMClient

logger = logging.getLogger("recruittech.agents.toolkit")


async def db_query(supabase: Client, table: str, filters: dict, limit: int = 20) -> list[dict]:
    """通用 Supabase 查询工具."""
    q = supabase.table(table).select("*")
    for k, v in filters.items():
        if v is None:
            continue
        if k.endswith("__gt"):
            q = q.gt(k[:-4], v)
        elif k.endswith("__lt"):
            q = q.lt(k[:-4], v)
        elif k.endswith("__like"):
            q = q.ilike(k[:-6], f"%{v}%")
        elif k.endswith("__in"):
            q = q.in_(k[:-4], v)
        else:
            q = q.eq(k, v)
    q = q.limit(limit)
    result = q.execute()
    return result.data or []


async def db_insert(supabase: Client, table: str, record: dict) -> dict:
    result = supabase.table(table).insert(record).execute()
    return result.data[0] if result.data else {}


async def llm_call(llm: LLMClient, prompt: str, system: str = "", json_mode: bool = False) -> str:
    """标准 LLM 调用工具."""
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    fmt = {"type": "json_object"} if json_mode else None
    text, _, _ = await llm.call(msgs, response_format=fmt)
    return text


async def notify_user(channel: str, user_id: str, content: str) -> bool:
    """推送通知(Web Push / 邮件 / 钉钉 / 飞书)."""
    logger.info(f"[notify] {channel} -> {user_id}: {content[:80]}")
    return True


async def search_web(query: str, top_k: int = 5) -> list[dict]:
    """网页搜索(MVP 阶段返回 mock,后续接入 Tavily/SerpAPI)."""
    return [{"title": f"Result for {query}", "url": "", "snippet": "mock"}]


async def ocr_document(file_url: str) -> dict:
    """OCR 文档解析(占位,生产环境接入 Tesseract/百度 OCR/阿里云 OCR)."""
    return {"text": f"[OCR-mock] {file_url}", "fields": {}}


async def company_lookup(name: str) -> dict:
    """企业工商信息查询(MVP mock,生产环境接入天眼查/启信宝)."""
    return {
        "name": name,
        "registered_capital": "1000万",
        "status": "存续",
        "credit_code": "91*******MA****",
        "established": "2018-05-01",
    }


def make_default_toolkit(supabase: Client, llm: LLMClient) -> dict[str, Any]:
    """生成默认 toolkit 字典,Agent 注册时 spread 进去即可."""
    return {
        "db_query": lambda **kw: db_query(supabase, **kw),
        "db_insert": lambda **kw: db_insert(supabase, **kw),
        "llm_call": lambda **kw: llm_call(llm, **kw),
        "notify": notify_user,
        "search_web": search_web,
        "ocr": ocr_document,
        "company_lookup": company_lookup,
    }