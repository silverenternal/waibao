"""T1204 — 第三方通讯录同步服务 (钉钉 + 飞书 + 企微).

职责:
  1. 拉取企业通讯录 → 写入 corp_user_mappings
  2. 根据 admin / boss / dept_leader 标志自动映射到 waibao 角色
  3. 调度审批流 / IM 推送
  4. 同步状态记录到 corp_sync_logs

复用:
  - supabase admin client (api.deps.get_supabase_admin)
  - providers.notify.{dingtalk,feishu}_provider (已存在)

不直接发起 HTTP — 调用方传入已获取的 access_token,避免重复授权握手。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol

from api.deps import get_supabase_admin  # type: ignore

logger = logging.getLogger("waibao.corp_sync")

# 角色映射: 第三方标志 → waibao 角色
ROLE_BOSS = "boss"
ROLE_HR = "hr"
ROLE_DEPT_HEAD = "dept_head"
ROLE_EMPLOYEE = "employee"


@dataclass
class CorpUser:
    """通用通讯录用户 (钉钉 / 飞书都映射到这个结构)."""

    external_user_id: str
    external_union_id: str | None = None
    name: str = ""
    mobile: str | None = None
    email: str | None = None
    title: str | None = None
    dept_ids: list[str] = field(default_factory=list)
    is_admin: bool = False
    is_boss: bool = False
    is_hr: bool = False
    is_dept_head: bool = False
    active: bool = True

    def role(self) -> str:
        if self.is_boss:
            return ROLE_BOSS
        if self.is_hr:
            return ROLE_HR
        if self.is_dept_head:
            return ROLE_DEPT_HEAD
        return ROLE_EMPLOYEE


@dataclass
class CorpDept:
    id: str
    name: str
    parent_id: str | None = None


@dataclass
class SyncResult:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def accuracy(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.succeeded / self.total, 4)

    def to_log(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "accuracy": self.accuracy,
            "duration_ms": self.duration_ms,
            "errors": self.errors[:20],
        }


class CorpClient(Protocol):
    """钉钉 / 飞书 client 必须实现的接口 (用于测试时 mock)."""

    corp_type: str

    def fetch_departments(self) -> list[CorpDept]: ...

    def fetch_users(self, dept_id: str | None = None) -> list[CorpUser]: ...


class CorpSyncService:
    """通讯录同步服务 (单绑定)."""

    def __init__(self, binding_id: str) -> None:
        self.binding_id = binding_id
        self._sb = get_supabase_admin()

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def sync_all(self, client: CorpClient) -> SyncResult:
        """拉取 + 映射 + 写库 (整个企业)."""
        t0 = time.time()
        result = SyncResult()

        try:
            depts = client.fetch_departments()
            logger.info("corp=%s fetched %d depts", self.binding_id, len(depts))
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"fetch_departments: {exc}")
            self._log("dept", "pull", "failed", 0, 0, 1, str(exc), int((time.time() - t0) * 1000))
            return result

        users: list[CorpUser] = []
        for dept in depts:
            try:
                users.extend(client.fetch_users(dept.id))
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"fetch_users[{dept.id}]: {exc}")

        # 去重 (按 external_user_id)
        seen: dict[str, CorpUser] = {}
        for u in users:
            seen.setdefault(u.external_user_id, u)
        deduped = list(seen.values())

        result.total = len(deduped)
        for u in deduped:
            try:
                self._upsert_user(u)
                result.succeeded += 1
            except Exception as exc:  # noqa: BLE001
                result.failed += 1
                result.errors.append(f"{u.external_user_id}: {exc}")

        result.duration_ms = int((time.time() - t0) * 1000)

        status = "success" if result.failed == 0 else ("partial" if result.succeeded else "failed")
        self._log(
            "user",
            "pull",
            status,
            result.total,
            result.succeeded,
            result.failed,
            "; ".join(result.errors[:5]) or None,
            result.duration_ms,
        )

        # 更新 binding.sync_state / last_synced_at
        self._sb.table("corp_bindings").update(
            {
                "sync_state": result.to_log(),
                "last_synced_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        ).eq("id", self.binding_id).execute()

        return result

    def list_users(self, role: str | None = None) -> list[dict[str, Any]]:
        q = self._sb.table("corp_user_mappings").select("*").eq("binding_id", self.binding_id)
        if role:
            q = q.eq("role", role)
        res = q.order("name").execute()
        return res.data or []

    def get_user(self, external_user_id: str) -> dict[str, Any] | None:
        res = (
            self._sb.table("corp_user_mappings")
            .select("*")
            .eq("binding_id", self.binding_id)
            .eq("external_user_id", external_user_id)
            .maybe_single()
            .execute()
        )
        return res.data if res.data else None

    def upsert_internal_user(self, external_user_id: str, internal_user_id: str) -> dict[str, Any]:
        """手动绑定 external → internal user."""
        res = (
            self._sb.table("corp_user_mappings")
            .update({"internal_user_id": internal_user_id, "synced_at": _now()})
            .eq("binding_id", self.binding_id)
            .eq("external_user_id", external_user_id)
            .execute()
        )
        return res.data[0] if res.data else {}

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _upsert_user(self, u: CorpUser) -> None:
        role = u.role()
        row = {
            "binding_id": self.binding_id,
            "external_user_id": u.external_user_id,
            "external_union_id": u.external_union_id,
            "external_dept_ids": u.dept_ids,
            "role": role,
            "name": u.name,
            "mobile": u.mobile,
            "email": u.email,
            "title": u.title,
            "is_admin": u.is_admin,
            "is_boss": u.is_boss,
            "is_hr": u.is_hr,
            "is_dept_head": u.is_dept_head,
            "active": u.active,
            "synced_at": _now(),
        }
        self._sb.table("corp_user_mappings").upsert(
            row, on_conflict="binding_id,external_user_id"
        ).execute()

    def _log(
        self,
        sync_type: str,
        direction: str,
        status: str,
        total: int,
        succeeded: int,
        failed: int,
        error: str | None,
        duration_ms: int,
    ) -> None:
        try:
            self._sb.table("corp_sync_logs").insert(
                {
                    "binding_id": self.binding_id,
                    "sync_type": sync_type,
                    "direction": direction,
                    "status": status,
                    "total": total,
                    "succeeded": succeeded,
                    "failed": failed,
                    "error": error,
                    "duration_ms": duration_ms,
                }
            ).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("corp_sync_logs insert failed: %s", exc)


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ------------------------------------------------------------
# 角色自动映射规则 (可在 admin API 中改)
# ------------------------------------------------------------
DEFAULT_AUTO_RULES: dict[str, Any] = {
    "boss": {
        "match": {"is_boss": True, "admin_scope_any": ["CORP", "ORG"]},
        "waibao_role": ROLE_BOSS,
    },
    "hr": {
        "match": {"title_keywords": ["HR", "人力", "招聘", "人事"]},
        "waibao_role": ROLE_HR,
    },
    "dept_head": {
        "match": {"is_dept_leader": True},
        "waibao_role": ROLE_DEPT_HEAD,
    },
    "default": {"waibao_role": ROLE_EMPLOYEE},
}


__all__ = [
    "CorpClient",
    "CorpDept",
    "CorpSyncService",
    "CorpUser",
    "DEFAULT_AUTO_RULES",
    "ROLE_BOSS",
    "ROLE_DEPT_HEAD",
    "ROLE_EMPLOYEE",
    "ROLE_HR",
    "SyncResult",
]