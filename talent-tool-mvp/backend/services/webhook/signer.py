"""Webhook HMAC 签名工具 (T802).

签名格式 (与 GitHub 一致):
    X-Waibao-Signature: sha256=<hex>

算法:
    signature = HMAC_SHA256(secret, body_bytes).hexdigest()
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Final

SIGNATURE_HEADER: Final = "X-Waibao-Signature"
SIGNATURE_PREFIX: Final = "sha256="
TIMESTAMP_HEADER: Final = "X-Waibao-Timestamp"


class SignatureError(Exception):
    """签名校验失败."""


def generate_secret(nbytes: int = 32) -> str:
    """生成一个新的 HMAC 密钥 (hex 编码)."""
    return secrets.token_hex(nbytes)


def compute_signature(secret: str, body: bytes) -> str:
    """计算 HMAC-SHA256 签名."""
    if not isinstance(body, (bytes, bytearray)):
        raise TypeError("body 必须为 bytes")
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256)
    return SIGNATURE_PREFIX + mac.hexdigest()


def verify_signature(
    secret: str,
    body: bytes,
    provided_signature: str | None,
    *,
    timestamp: str | None = None,
    tolerance_seconds: int = 300,
) -> bool:
    """校验 HMAC 签名.

    Args:
        secret: 共享密钥.
        body: 原始 body bytes.
        provided_signature: 从 header 取出的值 (含 sha256= 前缀).
        timestamp: 可选的时间戳 (ISO8601),用于重放保护.
        tolerance_seconds: 时间戳容差.

    Returns:
        True 通过, False 失败.

    Raises:
        SignatureError: 签名格式错误或时间戳漂移过大.
    """
    if not provided_signature:
        raise SignatureError("缺少签名头")
    if not provided_signature.startswith(SIGNATURE_PREFIX):
        raise SignatureError("签名必须以 sha256= 开头")
    if timestamp:
        try:
            from datetime import datetime, timezone
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            now = datetime.now(tz=timezone.utc)
            delta = abs((now - ts).total_seconds())
            if delta > tolerance_seconds:
                raise SignatureError(
                    f"时间戳漂移 {delta:.0f}s 超过容差 {tolerance_seconds}s"
                )
        except SignatureError:
            raise
        except Exception as exc:
            raise SignatureError(f"时间戳格式错误: {exc}") from exc

    expected = compute_signature(secret, body)
    return hmac.compare_digest(expected, provided_signature)