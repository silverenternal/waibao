"""PII 字段级透明加密服务 — T1202.

覆盖字段:
- name / full_name          (L2 一般)
- email                     (L2 一般)
- phone                     (L2 一般)
- id_card / id_card_no      (L4 核心)
- address                   (L3 重要)
- bank_card                 (L3 重要)
- resume_text               (L3 重要)
- cv_text                   (L3 重要,alias of resume_text)

提供:
- encrypt_pii(plaintext, field_name) -> str (urlsafe-base64)
- decrypt_pii(ciphertext, field_name) -> str
- encrypt_pii_fields(data, field_list) -> dict
- decrypt_pii_fields(data, field_list) -> dict
- 装饰器 @pii_encrypted_fields 用于自动透明加解密

与 backend.compliance.encryption.PIIEncryptor 协作,使用同一 Fernet 实现.
"""
from __future__ import annotations

import functools
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from compliance.audit import get_audit_logger
from compliance.encryption import PIIEncryptor, get_pii_encryptor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 字段级别定义
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FieldSpec:
    """单个 PII 字段的元数据."""

    name: str
    level: int  # 1=公开, 2=一般, 3=重要, 4=核心
    description: str = ""
    aliases: tuple[str, ...] = ()


# 字段注册表 — 关键 PII 字段清单
PII_FIELDS: dict[str, FieldSpec] = {
    "full_name": FieldSpec("full_name", 2, "姓名", ("name",)),
    "name": FieldSpec("name", 2, "姓名 alias"),
    "email": FieldSpec("email", 2, "邮箱"),
    "phone": FieldSpec("phone", 2, "手机号"),
    "id_card": FieldSpec("id_card", 4, "身份证号", ("id_card_no", "id_number")),
    "id_card_no": FieldSpec("id_card_no", 4, "身份证号 alias"),
    "address": FieldSpec("address", 3, "通讯地址"),
    "bank_card": FieldSpec("bank_card", 3, "银行卡号", ("bank_account",)),
    "resume_text": FieldSpec("resume_text", 3, "简历正文", ("cv_text",)),
    "cv_text": FieldSpec("cv_text", 3, "简历正文 alias"),
    "bio": FieldSpec("bio", 2, "个人简介"),
    "headline": FieldSpec("headline", 1, "职位头衔", ("title",)),
    "company_name": FieldSpec("company_name", 1, "公司名"),
    "location": FieldSpec("location", 1, "所在地"),
}


def resolve_canonical(name: str) -> FieldSpec | None:
    """解析字段名,支持 alias."""
    if name in PII_FIELDS:
        return PII_FIELDS[name]
    for spec in PII_FIELDS.values():
        if name in spec.aliases:
            return spec
    return None


def list_pii_fields(level_min: int = 2) -> list[str]:
    """列出所有 ≥ level_min 级别的 PII 字段."""
    return [n for n, spec in PII_FIELDS.items() if spec.level >= level_min]


# ---------------------------------------------------------------------------
# 加密 / 解密
# ---------------------------------------------------------------------------

class PIIFieldService:
    """PII 字段级加密服务.

    包装 PIIEncryptor,加入字段元数据 + 自动审计.
    """

    def __init__(self, encryptor: PIIEncryptor | None = None) -> None:
        self._lock = threading.RLock()
        self._enc = encryptor or get_pii_encryptor()
        self._audit_enabled = True

    def enable_audit(self, on: bool = True) -> None:
        self._audit_enabled = on

    @property
    def backend(self) -> str:
        return self._enc.backend

    def encrypt_pii(self, plaintext: str, field_name: str) -> str:
        if plaintext is None:
            return plaintext  # type: ignore[return-value]
        if not isinstance(plaintext, str):
            raise TypeError(f"plaintext must be str, got {type(plaintext).__name__}")
        spec = resolve_canonical(field_name)
        if spec is None:
            raise ValueError(f"unknown PII field: {field_name}")
        with self._lock:
            token = self._enc.encrypt(plaintext)
        self._audit("encrypt", field_name, spec, plaintext_length=len(plaintext))
        return token

    def decrypt_pii(self, ciphertext: str, field_name: str) -> str:
        if ciphertext is None:
            return ciphertext  # type: ignore[return-value]
        if not isinstance(ciphertext, str):
            raise TypeError(f"ciphertext must be str, got {type(ciphertext).__name__}")
        spec = resolve_canonical(field_name)
        if spec is None:
            raise ValueError(f"unknown PII field: {field_name}")
        with self._lock:
            plaintext = self._enc.decrypt(ciphertext)
        self._audit("decrypt", field_name, spec, ciphertext_length=len(ciphertext))
        return plaintext

    def encrypt_pii_fields(
        self,
        data: dict[str, Any],
        fields: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """加密 data 中指定字段;fields=None 表示加密所有已知 PII 字段."""
        out = dict(data)
        target_fields = list(fields) if fields is not None else list_pii_fields(level_min=2)
        for fname in target_fields:
            v = out.get(fname)
            if isinstance(v, str) and v and self._looks_like_ciphertext(v) is False:
                try:
                    out[fname] = self.encrypt_pii(v, fname)
                except (TypeError, ValueError) as exc:
                    logger.warning(f"pii_encrypt_failed field={fname}: {exc}")
        return out

    def decrypt_pii_fields(
        self,
        data: dict[str, Any],
        fields: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """解密 data 中指定字段;非密文 / 解密失败时静默跳过."""
        out = dict(data)
        target_fields = list(fields) if fields is not None else list_pii_fields(level_min=2)
        for fname in target_fields:
            v = out.get(fname)
            if isinstance(v, str) and v and self._looks_like_ciphertext(v):
                try:
                    out[fname] = self.decrypt_pii(v, fname)
                except (TypeError, ValueError) as exc:
                    logger.debug(f"pii_decrypt_failed field={fname}: {exc}")
                    # 保留原值,业务层可感知
                except Exception:  # noqa: BLE001
                    # fernet InvalidToken 等 — 视为非密文保留原值
                    logger.debug(f"pii_decrypt_invalid_token field={fname}")
        return out

    def _looks_like_ciphertext(self, value: str) -> bool:
        """简单启发式判断:Fernet 输出是 urlsafe-base64,以 'gAAAAA' 开头."""
        return value.startswith("gAAAAA") or value.startswith("gAAAAE")

    def _audit(
        self,
        action: str,
        field_name: str,
        spec: FieldSpec,
        *,
        plaintext_length: int | None = None,
        ciphertext_length: int | None = None,
    ) -> None:
        if not self._audit_enabled:
            return
        try:
            logger = get_audit_logger()
            logger.log(
                actor_id=None,  # 由调用方上下文注入
                actor_role="system",
                action=f"pii_{action}",
                resource="pii_field",
                resource_id=field_name,
                data_categories=[field_name, "pii"],
                legal_basis="contract_necessity",
                metadata={
                    "field_name": field_name,
                    "level": spec.level,
                    "backend": self.backend,
                    "plaintext_length": plaintext_length,
                    "ciphertext_length": ciphertext_length,
                },
            )
        except Exception:  # noqa: BLE001
            logger_inst = logging.getLogger(__name__)
            logger_inst.exception("pii_audit_failed")


_singleton: PIIFieldService | None = None


def get_pii_field_service() -> PIIFieldService:
    global _singleton
    if _singleton is None:
        _singleton = PIIFieldService()
    return _singleton


# ---------------------------------------------------------------------------
# 装饰器 — 自动透明加解密
# ---------------------------------------------------------------------------

def pii_encrypted_fields(
    fields: list[str],
    *,
    direction: str = "both",  # "encrypt" | "decrypt" | "both"
) -> Callable:
    """装饰器:对函数返回 / 接收 dict 中的 PII 字段自动加解密.

    加密时只加密 fields 中指定的字段;解密时同样只解密这些字段.

    用法:
        @pii_encrypted_fields(["full_name", "email"])
        async def create_candidate(data: dict) -> dict: ...
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            svc = get_pii_field_service()
            if direction in ("encrypt", "both"):
                args = tuple(
                    svc.encrypt_pii_fields(a, fields) if isinstance(a, dict) else a for a in args
                )
                kwargs = {
                    k: svc.encrypt_pii_fields(v, fields) if isinstance(v, dict) else v
                    for k, v in kwargs.items()
                }
            result = await fn(*args, **kwargs)
            if direction in ("decrypt", "both") and isinstance(result, dict):
                result = svc.decrypt_pii_fields(result, fields)
            return result

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            svc = get_pii_field_service()
            if direction in ("encrypt", "both"):
                args = tuple(
                    svc.encrypt_pii_fields(a, fields) if isinstance(a, dict) else a for a in args
                )
                kwargs = {
                    k: svc.encrypt_pii_fields(v, fields) if isinstance(v, dict) else v
                    for k, v in kwargs.items()
                }
            result = fn(*args, **kwargs)
            if direction in ("decrypt", "both") and isinstance(result, dict):
                result = svc.decrypt_pii_fields(result, fields)
            return result

        if _is_coroutine(fn):
            return async_wrapper
        return sync_wrapper

    return decorator


def _is_coroutine(fn: Callable) -> bool:
    import inspect

    return inspect.iscoroutinefunction(fn)


# ---------------------------------------------------------------------------
# Module-level helpers for easy migration of existing services
# ---------------------------------------------------------------------------

def encrypt_dict(data: dict[str, Any], fields: list[str] | None = None) -> dict[str, Any]:
    """便捷:对 dict 中的 PII 字段加密."""
    return get_pii_field_service().encrypt_pii_fields(data, fields)


def decrypt_dict(data: dict[str, Any], fields: list[str] | None = None) -> dict[str, Any]:
    """便捷:对 dict 中的 PII 字段解密."""
    return get_pii_field_service().decrypt_pii_fields(data, fields)