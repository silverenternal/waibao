"""字段级加密服务 — T403 (PII 加密).

支持 AES-GCM 加密身份证/手机/邮箱/地址等敏感字段.
"""
from __future__ import annotations

import base64
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("recruittech.services.crypto")


def _get_key() -> bytes:
    """获取或生成主密钥(MVP: 环境变量; 生产: KMS)."""
    raw = os.getenv("PII_ENCRYPTION_KEY")
    if raw:
        try:
            return base64.b64decode(raw)
        except Exception:
            return raw.encode()[:32].ljust(32, b"0")
    # 兜底: 开发用固定 key (生产必须替换)
    return b"dev-only-32-byte-key-replace-me!"


_KEY = _get_key()
_aead = AESGCM(_KEY)


def encrypt(plaintext: str, associated_data: str = "") -> str:
    """加密为 base64(nonce + ciphertext + tag)."""
    if not plaintext:
        return ""
    nonce = os.urandom(12)
    ct = _aead.encrypt(nonce, plaintext.encode("utf-8"), associated_data.encode("utf-8"))
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt(ciphertext_b64: str, associated_data: str = "") -> str:
    """解密 base64 字符串."""
    if not ciphertext_b64:
        return ""
    raw = base64.b64decode(ciphertext_b64)
    nonce, ct = raw[:12], raw[12:]
    return _aead.decrypt(nonce, ct, associated_data.encode("utf-8")).decode("utf-8")


def mask(plaintext: str, visible_prefix: int = 3, visible_suffix: int = 2) -> str:
    """脱敏: 仅显示前 N 位 + **** + 后 M 位."""
    if not plaintext or len(plaintext) <= visible_prefix + visible_suffix:
        return "*" * len(plaintext or "")
    return f"{plaintext[:visible_prefix]}{'*' * (len(plaintext) - visible_prefix - visible_suffix)}{plaintext[-visible_suffix:]}"