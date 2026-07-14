"""PII 字段级加密 (Fernet).

T1202 — 简历中的身份证号 / 银行卡 / 地址 等 PII 字段必须加密存储.
Fernet (AES-128-CBC + HMAC-SHA256) 是 cryptography 库提供的高层接口.

T5014 — fail-fast: cryptography 不再是可选依赖. 过去本模块在
cryptography 缺失时静默降级到一个只做 HMAC 的伪加密后端 (plaintext
被原样拼接进 blob), 这会让 PII 在弱环境里**以可读形式落库**. 现在
import / 构造时会显式校验 cryptography 可用, 缺失则抛出
:class:`CryptographyUnavailableError` 而不是继续运行.
"""
from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import json
import os
import threading
from typing import Any


class CryptographyUnavailableError(RuntimeError):
    """Raised when the ``cryptography`` package is not importable (T5014).

    PII 加密现在强制要求 cryptography (Fernet). 静默降级到 HMAC 伪加密
    会让明文 PII 落库, 所以我们 fail-fast.
    """


_FERNET_BACKEND: str | None = None
_FERNET_CLS: Any = None


def _detect_backend(*, require: bool = True) -> None:
    """Detect the cryptography Fernet backend.

    T5014 — when ``require`` is True (default) a missing ``cryptography``
    raises :class:`CryptographyUnavailableError` instead of falling back to
    the insecure HMAC pseudo-encryption path.
    """
    global _FERNET_BACKEND, _FERNET_CLS
    if _FERNET_BACKEND is not None:
        if _FERNET_BACKEND == "fallback" and require:
            raise CryptographyUnavailableError(
                "cryptography (Fernet) backend is required for PII encryption "
                "but is not available (T5014 fail-fast). Install the "
                "`cryptography` package."
            )
        return
    try:
        from cryptography.fernet import Fernet  # type: ignore[import-not-found]

        _FERNET_CLS = Fernet
        _FERNET_BACKEND = "fernet"
        return
    except Exception as exc:  # noqa: BLE001
        _FERNET_BACKEND = "fallback"
        if require:
            raise CryptographyUnavailableError(
                f"cryptography (Fernet) is required for PII encryption but "
                f"could not be imported: {exc} (T5014 fail-fast)."
            ) from exc


def assert_cryptography_available() -> None:
    """Public fail-fast gate used by the startup security check."""
    _detect_backend(require=True)


class PIIEncryptor:
    """PII 字段加密.

    - encrypt(plaintext) -> str (urlsafe-base64)
    - decrypt(token) -> str
    - encrypt_dict / decrypt_dict:对 dict 中的指定字段加密,其它字段透传

    环境变量 PII_ENCRYPTION_KEY 控制 Fernet 主密钥 (必须是 urlsafe-base64
    编码的 32 字节). 未提供密钥时自动生成一个进程内 key (开发模式,重启即
    失效) — 生产环境必须显式提供 PII_ENCRYPTION_KEY 或 KMS DEK.

    T5015 — 当 ``kms`` 提供时, 主密钥来自 KMS DEK 而非本地环境变量.
    """

    def __init__(
        self,
        key: bytes | None = None,
        *,
        kms: Any = None,
    ) -> None:
        _detect_backend(require=True)
        self._lock = threading.RLock()
        self._kms = kms
        self._fernet: Any = None
        if kms is not None:
            # T5015: KMS-backed DEK. The DEK is a Fernet key (urlsafe-base64).
            dek = kms.current_dek()
            self._key = dek.key if hasattr(dek, "key") else dek
        elif key is not None:
            self._key = key
        else:
            env_key = os.getenv("PII_ENCRYPTION_KEY")
            if env_key:
                self._key = env_key.encode("utf-8")
            else:
                # 开发模式: 进程内随机 key. 生产必须由 KMS 或 env 提供.
                self._key = _FERNET_CLS.generate_key()
        self._init_fernet()

    def _init_fernet(self) -> None:
        if _FERNET_BACKEND != "fernet" or _FERNET_CLS is None:  # pragma: no cover
            raise CryptographyUnavailableError(
                "Fernet backend not initialised (T5014 fail-fast)."
            )
        key = self._key
        if isinstance(key, str):
            key = key.encode("utf-8")
        try:
            self._fernet = _FERNET_CLS(key)
        except Exception as exc:  # noqa: BLE001
            # key 不是合法的 Fernet key — fail-fast 而不是降级.
            raise CryptographyUnavailableError(
                f"PII encryption key is not a valid Fernet key: {exc} "
                "(T5014 fail-fast). Set PII_ENCRYPTION_KEY to a 32-byte "
                "urlsafe-base64 string."
            ) from exc

    @property
    def backend(self) -> str:
        return _FERNET_BACKEND or "unknown"

    def encrypt(self, plaintext: str) -> str:
        if not isinstance(plaintext, str):
            raise TypeError("plaintext must be str")
        if self._fernet is None:  # pragma: no cover
            raise CryptographyUnavailableError("Fernet backend missing")
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        if self._fernet is None:  # pragma: no cover
            raise CryptographyUnavailableError("Fernet backend missing")
        return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")

    def encrypt_dict(
        self,
        data: dict[str, Any],
        fields: list[str],
    ) -> dict[str, Any]:
        out = dict(data)
        with self._lock:
            for f in fields:
                v = out.get(f)
                if isinstance(v, str) and v:
                    out[f] = self.encrypt(v)
        return out

    def decrypt_dict(
        self,
        data: dict[str, Any],
        fields: list[str],
    ) -> dict[str, Any]:
        out = dict(data)
        with self._lock:
            for f in fields:
                v = out.get(f)
                if isinstance(v, str) and v:
                    try:
                        out[f] = self.decrypt(v)
                    except Exception:  # noqa: BLE001
                        # 未加密的值静默跳过,业务层负责兜底
                        pass
        return out

    def rotate_key(self, new_key: bytes) -> None:
        """轮换密钥(操作员触发,解密旧 token 需保留旧 key)."""
        self._key = new_key
        self._init_fernet()


_singleton: PIIEncryptor | None = None
_singleton_lock = threading.Lock()


def get_pii_encryptor() -> PIIEncryptor:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            # T5015: 如果 KMS 已配置, 用 KMS DEK 作为 Fernet 主密钥.
            kms = _try_get_kms()
            _singleton = PIIEncryptor(kms=kms)
        return _singleton


def reset_pii_encryptor() -> None:
    """Test helper: drop the cached singleton so the next call rebuilds it."""
    global _singleton
    with _singleton_lock:
        _singleton = None


def _try_get_kms() -> Any:
    """Best-effort KMS lookup. Returns None when no KMS is configured."""
    try:  # pragma: no cover - import cycle guard
        from compliance.kms import get_kms  # type: ignore[import-not-found]

        return get_kms()
    except Exception:  # noqa: BLE001
        return None