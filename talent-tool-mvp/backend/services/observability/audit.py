"""T1004 - 审计服务.

- @audit('read', 'candidate') 装饰器: 自动记录对 PII 的访问.
- record(action, resource_type, resource_id, user_id, ...): 主动写审计日志.
- 装饰器可通过 kwargs.resource_id 或函数返回值推断 resource_id.
- 失败只 warn 不抛出 (审计是辅助能力).
"""
from __future__ import annotations

import functools
import json
import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger("waibao.audit")


def _supabase_admin():
    try:
        from api.deps import get_supabase_admin

        return get_supabase_admin()
    except Exception:  # noqa: BLE001
        return None


def record(
    *,
    actor_user_id: Optional[str],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """写一条审计日志. 失败仅 warn 不抛."""
    try:
        sb = _supabase_admin()
        if sb is None:
            return
        payload = {
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "action": action,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "user_id": str(user_id) if user_id else None,
            "ip_address": ip_address,
            "user_agent": (user_agent or "")[:512],
            "metadata": metadata or {},
        }
        # filter None 让 PG 自动忽略
        payload = {k: v for k, v in payload.items() if v is not None}
        sb.table("audit_log").insert(payload).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit.record_failed action=%s resource=%s err=%s", action, resource_type, exc)


def audit(
    action: str,
    resource_type: str,
    *,
    user_id_arg: Optional[str] = None,
    resource_id_arg: Optional[str] = None,
    metadata_fn: Optional[Callable[..., dict]] = None,
):
    """装饰器: 把函数调用记入审计日志.

    - user_id_arg: 从 kwargs 取 user_id
    - resource_id_arg: 从 kwargs 取 resource_id
    - metadata_fn: (args, kwargs, result) -> dict, 自定义 metadata
    """

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            result = await fn(*args, **kwargs)
            try:
                actor_id = None
                if "user" in kwargs and hasattr(kwargs["user"], "id"):
                    actor_id = str(kwargs["user"].id)
                user_id = (
                    kwargs.get(user_id_arg) if user_id_arg else actor_id
                )
                resource_id = (
                    kwargs.get(resource_id_arg) if resource_id_arg else None
                )
                # Fallback: from URL path (FastAPI Request)
                if resource_id is None:
                    request = kwargs.get("request")
                    if request is not None and hasattr(request, "path_params"):
                        resource_id = request.path_params.get("id") or request.path_params.get(
                            resource_type + "_id"
                        )
                metadata: dict = {}
                if metadata_fn is not None:
                    try:
                        metadata = metadata_fn(args, kwargs, result) or {}
                    except Exception:  # noqa: BLE001
                        metadata = {}
                record(
                    actor_user_id=actor_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=str(resource_id) if resource_id else None,
                    user_id=str(user_id) if user_id else None,
                    metadata=metadata,
                )
            except Exception:  # noqa: BLE001
                logger.exception("audit.decorator_failed action=%s", action)
            return result

        return wrapper

    return decorator