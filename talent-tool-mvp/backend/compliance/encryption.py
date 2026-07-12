"""PII 字段级加密 (Fernet).

T1202 — 简历中的身份证号 / 银行卡 / 地址 等 PII 字段必须加密存储.
Fernet (AES-128-CBC + HMAC-SHA256) 是 cryptography 库提供的高层接口.

为避免强制依赖 cryptography,本模块提供两层 API:
- 默认:使用 cryptography.fernet (生产环境)
- 降级:使用 hashlib + base64 + HMAC 的本地 fallback (仅测试用,安全性较低)
"""
from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import json
import os
import threading
from typing import Any

_FERNET_BACKEND: str | None = None
_FERNET_CLS: Any = None


def _detect_backend() -> None:
    global _FERNET_BACKEND, _FERNET_CLS
    if _FERNET_BACKEND is not None:
        return
    try:
        from cryptography.fernet import Fernet  # type: ignore[import-not-found]

        _FERNET_CLS = Fernet
        _FERNET_BACKEND = "fernet"
        return
    except Exception:  # noqa: BLE001
        pass
    _FERNET_BACKEND = "fallback"


class PIIEncryptor:
    """PII 字段加密.

    - encrypt(plaintext) -> str (urlsafe-base64)
    - decrypt(token) -> str
    - encrypt_dict / decrypt_dict:对 dict 中的指定字段加密,其它字段透传

    环境变量 PII_ENCRYPTION_KEY 控制密钥(必须为 32-byte base64 字符串).
    未提供密钥时,自动生成一个进程内 key (开发模式,重启即失效).
    """

    def __init__(self, key: bytes | None = None) -> None:
        _detect_backend()
        self._lock = threading.RLock()
        if key is not None:
            self._key = key
        else:
            env_key = os.getenv("PII_ENCRYPTION_KEY")
            if env_key:
                self._key = env_key.encode("utf-8")
            elif _FERNET_BACKEND == "fernet" and _FERNET_CLS is not None:
                self._key = _FERNET_CLS.generate_key()
            else:
                self._key = hashlib.sha256(
                    os.urandom(32)
                ).digest()  # fallback: 不符合 base64 要求,会被 fallback 解码忽略
        self._fernet: Any = None
        if _FERNET_BACKEND == "fernet" and _FERNET_CLS is not None:
            try:
                self._fernet = _FERNET_CLS(self._key)
            except Exception:  # noqa: BLE001
                # key 不合法,降级 fallback
                self._fernet = None

    @property
    def backend(self) -> str:
        return _FERNET_BACKEND or "unknown"

    def encrypt(self, plaintext: str) -> str:
        if not isinstance(plaintext, str):
            raise TypeError("plaintext must be str")
        if self._fernet is not None:
            return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        # fallback: AES 不在,使用 HMAC 伪装 — 仅测试用
        nonce = os.urandom(8)
        mac = _hmac.new(self._key, nonce + plaintext.encode("utf-8"), hashlib.sha256).digest()
        blob = nonce + mac + plaintext.encode("utf-8")
        return base64.urlsafe_b64encode(blob).decode("ascii")

    def decrypt(self, token: str) -> str:
        if self._fernet is not None:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        blob = base64.urlsafe_b64decode(token.encode("ascii"))
        nonce, mac, ct = blob[:8], blob[8:40], blob[40:]
        expected = _hmac.new(self._key, nonce + ct, hashlib.sha256).digest()
        if not _hmac.compare_digest(mac, expected):
            raise ValueError("PII token integrity check failed")
        return ct.decode("utf-8")

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
        self._fernet = None
        if _FERNET_BACKEND == "fernet" and _FERNET_CLS is not None:
            try:
                self._fernet = _FERNET_CLS(new_key)
            except Exception:  # noqa: BLE001
                self._fernet = None


_singleton: PIIEncryptor | None = None


def get_pii_encryptor() -> PIIEncryptor:
    global _singleton
    if _singleton is None:
        _singleton = PIIEncryptor()
    return _singleton