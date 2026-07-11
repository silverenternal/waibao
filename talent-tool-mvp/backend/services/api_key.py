"""API Key 管理服务 (T803).

设计:
- Key 格式:  ``wb_live_<22-char base32>`` = 总长 30 字符
- 前缀:      ``wb_live_<6-char>`` 在 UI 上展示 (用于区分、但不暴露密钥本身)
- 存储:      只存 SHA256 哈希 (``key_hash``) + 前缀 (``key_prefix``)
- 验证:      客户端传明文 -> 哈希 -> DB lookup -> 比对
- 速率:      Redis token bucket;无 Redis 时退化到内存 LRU
- 作用域:    ``candidates:read`` / ``candidates:write`` / ``roles:read`` /
              ``matches:write`` / ``tickets:write``
- 撤销:      设 ``revoked_at``,验证直接失败
- 一次性明文: 仅在 ``generate_key`` 返回 dict 中出现一次,后续 API 不返回

明文绝不写日志、不落审计。
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)

KEY_PREFIX_LITERAL = "wb_live_"
KEY_RANDOM_BYTES = 14  # 14 bytes -> 22 chars base32 (无 padding)
KEY_TOTAL_LEN = len(KEY_PREFIX_LITERAL) + 22  # 30 字符

VALID_SCOPES: frozenset[str] = frozenset(
    {
        "candidates:read",
        "candidates:write",
        "roles:read",
        "matches:write",
        "tickets:write",
    }
)

# Redis 抽象 (避免硬依赖);实现方在 init 时注入.
RateLimiter = Any  # Protocol,实际为 redis.asyncio.Redis


def _hash_key(plain: str) -> str:
    """SHA256 hex. 仅用于比对/检索,不用于签名."""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _generate_plain() -> str:
    """生成 30 字符明文 key. 14 random bytes -> 22 chars base32 (无 padding)."""
    raw = secrets.token_bytes(KEY_RANDOM_BYTES)
    b32 = secrets.base64.b32encode(raw).decode("ascii").rstrip("=")
    # base32 编码 14 字节 -> 23 字符;我们取前 22 字符 (去掉最后一个 '=' 补偿字符)
    return KEY_PREFIX_LITERAL + b32[:22]


def _split_prefix(plain: str) -> str:
    """前 12 字符: ``wb_live_`` + 前 4 个随机字符. 不足以反推密钥."""
    return plain[:12]


@dataclass(slots=True)
class GeneratedKey:
    """generate_key 返回值.

    Attributes:
        plaintext: 仅此时可见,后续 API 只返回 hash.
        key_hash:  写入 DB.
        key_prefix: 写入 DB,UI 展示用.
        id:  DB 行 ID.
    """

    id: str
    plaintext: str
    key_hash: str
    key_prefix: str


def generate_key(name: str, *, organisation_id: str) -> GeneratedKey:
    """生成新的 API Key. ``plaintext`` 只此一次."""
    import uuid

    plaintext = _generate_plain()
    return GeneratedKey(
        id=str(uuid.uuid4()),
        plaintext=plaintext,
        key_hash=_hash_key(plaintext),
        key_prefix=_split_prefix(plaintext),
    )


# ---------------------------------------------------------------------------
# 验证 / scope
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class VerifiedKey:
    """verify_key 成功返回."""

    id: str
    organisation_id: str
    scopes: list[str]
    rate_limit_per_min: int


def verify_key(plain: str, record: dict[str, Any]) -> VerifiedKey | None:
    """比对明文与 DB 哈希.

    Args:
        plain:  客户端传来的明文.
        record: api_keys 表中对应行 (含 key_hash / revoked_at / expires_at).

    Returns:
        VerifiedKey 成功;None 失败 (含过期 / 撤销 / 哈希不匹配).
    """
    if not plain or not record:
        return None
    if record.get("revoked_at"):
        return None
    if record.get("expires_at"):
        # expires_at 是 ISO 字符串;比较 epoch seconds
        try:
            exp = record["expires_at"]
            if isinstance(exp, str):
                ts = datetime.fromisoformat(exp.replace("Z", "+00:00")).timestamp()
            else:
                ts = float(exp)
            if ts < time.time():
                return None
        except Exception:  # noqa: BLE001
            return None
    if _hash_key(plain) != record.get("key_hash"):
        return None
    return VerifiedKey(
        id=record["id"],
        organisation_id=record["organisation_id"],
        scopes=list(record.get("scopes") or []),
        rate_limit_per_min=int(record.get("rate_limit_per_min") or 60),
    )


def check_scope(verified: VerifiedKey, required: str) -> bool:
    """检查 scope. ``*`` 是通配(预留)."""
    if not verified or not required:
        return False
    if "*" in verified.scopes:
        return True
    return required in verified.scopes


# ---------------------------------------------------------------------------
# Rate limit (Redis token bucket, fallback 内存)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Bucket:
    tokens: float
    last_refill: float


class InMemoryRateLimiter:
    """每个 key 一分钟桶: tokens 每秒 +rate/60,单桶上限 rate."""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._history: dict[str, deque[float]] = {}

    def allow(self, key: str, rate_per_min: int) -> bool:
        now = time.monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=rate_per_min, last_refill=now)
            self._buckets[key] = bucket
        elapsed = now - bucket.last_refill
        refill = (rate_per_min / 60.0) * elapsed
        bucket.tokens = min(rate_per_min, bucket.tokens + refill)
        bucket.last_refill = now
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True
        return False


class RedisTokenBucket:
    """Redis Lua 实现的滑动窗口 + 令牌桶,简化版用固定 60s 窗口."""

    _LUA = """
    local key = KEYS[1]
    local limit = tonumber(ARGV[1])
    local now_ms = tonumber(ARGV[2])
    local window = tonumber(ARGV[3])
    redis.call('ZREMRANGEBYSCORE', key, 0, now_ms - window)
    local count = redis.call('ZCARD', key)
    if count < limit then
        redis.call('ZADD', key, now_ms, now_ms .. ':' .. math.random(1,100000))
        redis.call('PEXPIRE', key, window)
        return 1
    end
    return 0
    """

    def __init__(self, redis_client: Any) -> None:
        self._r = redis_client
        self._sha: str | None = None

    async def allow(self, key: str, rate_per_min: int) -> bool:
        try:
            now_ms = int(time.time() * 1000)
            window = 60_000
            if self._sha is None:
                self._sha = await self._r.script_load(self._LUA)
            res = await self._r.evalsha(self._sha, 1, key, rate_per_min, now_ms, window)
            return int(res) == 1
        except Exception:  # noqa: BLE001
            # Redis 异常时退化:allow (避免硬阻塞业务)
            logger.exception("rate_limit.redis_fallback key=%s", key)
            return True


class RateLimitGuard:
    """统一入口. 优先 Redis,无则 in-memory."""

    def __init__(self, redis_client: Any | None = None) -> None:
        self._redis = RedisTokenBucket(redis_client) if redis_client else None
        self._mem = InMemoryRateLimiter()

    async def allow(self, key_id: str, rate_per_min: int) -> bool:
        if self._redis is not None:
            return await self._redis.allow(key_id, rate_per_min)
        return self._mem.allow(key_id, rate_per_min)


# ---------------------------------------------------------------------------
# 撤销 / 序列化
# ---------------------------------------------------------------------------


def revoke(record_id: str, *, at: datetime | None = None) -> dict[str, Any]:
    """构造 revoke 更新 dict. 由调用方负责写 DB."""
    return {
        "revoked_at": (at or datetime.now(tz=timezone.utc)).isoformat(),
    }


def to_public(record: dict[str, Any]) -> dict[str, Any]:
    """api_keys 行 -> API 响应. 永不包含 plaintext / key_hash."""
    if not record:
        return {}
    return {
        "id": record["id"],
        "name": record.get("name"),
        "key_prefix": record.get("key_prefix"),
        "scopes": list(record.get("scopes") or []),
        "rate_limit_per_min": int(record.get("rate_limit_per_min") or 60),
        "expires_at": record.get("expires_at"),
        "revoked_at": record.get("revoked_at"),
        "last_used_at": record.get("last_used_at"),
        "created_at": record.get("created_at"),
    }


def validate_scopes(scopes: Iterable[str]) -> list[str]:
    """校验 scope 拼写. 非法 scope 抛 ValueError."""
    out: list[str] = []
    for s in scopes or []:
        if s not in VALID_SCOPES:
            raise ValueError(
                f"非法 scope '{s}';合法: {sorted(VALID_SCOPES)}"
            )
        out.append(s)
    return out
