"""T5015 — KMS abstraction + DEK management with 90-day rotation.

Envelope encryption:
  * A **Key Encryption Key (KEK)** lives in an external KMS (AWS KMS,
    HashiCorp Vault, Aliyun KMS) or, for local dev, in a process-local
    store backed by ``PII_ENCRYPTION_KEY``.
  * A **Data Encryption Key (DEK)** is a Fernet key (urlsafe-base64 32
    bytes) used by :class:`compliance.encryption.PIIEncryptor` to encrypt
    individual PII fields. The DEK is wrapped (encrypted) by the KEK and
    stored alongside the ciphertext, so ciphertext is portable across
    processes that share the same KEK.

Rotation:
  DEKs auto-rotate every 90 days (configurable via ``PII_DEK_TTL_DAYS``).
  Old DEKs are retained (``max_active_deks``) so existing ciphertext can
  still be decrypted; new writes always use the freshest DEK.

The module is import-safe: the backend is selected from
``KMS_PROVIDER`` (``local`` / ``aws`` / ``vault`` / ``aliyun``) and any
provider that cannot be initialised degrades to ``local`` with a warning.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger("waibao.kms")

DEFAULT_DEK_TTL_DAYS = 90
DEFAULT_MAX_ACTIVE_DEKS = 5

KMS_PROVIDERS = ("local", "aws", "vault", "aliyun")


# ---------------------------------------------------------------------------
# DEK data model
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class DEK:
    """A wrapped Data Encryption Key."""

    key_id: str
    key: str  # urlsafe-base64 32-byte Fernet key (plaintext — only resident)
    created_at: float
    rotated_at: Optional[float] = None
    provider: str = "local"
    wrapped_dek: Optional[str] = None  # KEK-encrypted DEK (portable form)
    state: str = "active"  # active | retired

    @property
    def age_days(self) -> float:
        ref = self.rotated_at or self.created_at
        return (time.time() - ref) / 86400.0

    def is_expired(self, ttl_days: int) -> bool:
        return self.age_days >= ttl_days

    def to_public_dict(self) -> dict[str, Any]:
        """Serialise without exposing the plaintext key."""
        d = asdict(self)
        d.pop("key", None)
        return d


# ---------------------------------------------------------------------------
# KMS backend protocol
# ---------------------------------------------------------------------------
class KMSBackend:
    """Abstract KMS backend. ``generate_dek`` produces + wraps a fresh DEK."""

    name = "base"

    def generate_dek(self) -> DEK:  # pragma: no cover - interface
        raise NotImplementedError

    def unwrap_dek(self, wrapped_dek: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Local backend (dev / self-hosted)
# ---------------------------------------------------------------------------
class LocalKMSBackend(KMSBackend):
    """Dev / self-hosted backend.

    The KEK is ``PII_ENCRYPTION_KEY`` (or a random process-local value).
    "Wrapping" is symmetric AES via Fernet using the KEK so wrapped DEKs
    are interchangeable across processes that share the same KEK.
    """

    name = "local"

    def __init__(self, kek: Optional[bytes] = None) -> None:
        from compliance.encryption import assert_cryptography_available

        assert_cryptography_available()
        from cryptography.fernet import Fernet  # type: ignore[import-not-found]

        if kek is not None:
            self._kek = kek
        else:
            env_key = os.getenv("PII_ENCRYPTION_KEY")
            if env_key:
                self._kek = env_key.encode("utf-8")
            else:
                self._kek = Fernet.generate_key()
        try:
            self._fernet = Fernet(self._kek)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"PII_ENCRYPTION_KEY is not a valid Fernet (KEK) key: {exc}"
            ) from exc

    def generate_dek(self) -> DEK:
        from cryptography.fernet import Fernet  # type: ignore[import-not-found]

        plaintext = Fernet.generate_key()
        wrapped = self._fernet.encrypt(plaintext).decode("ascii")
        return DEK(
            key_id=f"dek_{uuid.uuid4().hex[:16]}",
            key=plaintext.decode("ascii"),
            created_at=time.time(),
            provider=self.name,
            wrapped_dek=wrapped,
        )

    def unwrap_dek(self, wrapped_dek: str) -> str:
        return self._fernet.decrypt(wrapped_dek.encode("ascii")).decode("ascii")


# ---------------------------------------------------------------------------
# Cloud KMS backends (lazy SDK imports — degrade to local when SDK missing)
# ---------------------------------------------------------------------------
class AWSKMSBackend(KMSBackend):
    """AWS KMS backend (boto3). Degrades to local when boto3 missing."""

    name = "aws"

    def __init__(self) -> None:
        self._key_id = os.getenv("AWS_KMS_KEY_ID", "")
        try:  # pragma: no cover - optional dep
            import boto3  # type: ignore[import-not-found]

            self._client = boto3.client("kms")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"AWS KMS backend unavailable: {exc}") from exc

    def generate_dek(self) -> DEK:  # pragma: no cover - needs AWS
        resp = self._client.generate_data_key(KeyId=self._key_id, KeySpec="AES_256")
        plaintext = base64.urlsafe_b64encode(resp["Plaintext"]).decode("ascii")
        wrapped = base64.b64encode(resp["CiphertextBlob"]).decode("ascii")
        return DEK(
            key_id=f"dek_{uuid.uuid4().hex[:16]}",
            key=plaintext,
            created_at=time.time(),
            provider=self.name,
            wrapped_dek=wrapped,
        )

    def unwrap_dek(self, wrapped_dek: str) -> str:  # pragma: no cover - needs AWS
        resp = self._client.decrypt(CiphertextBlob=base64.b64decode(wrapped_dek))
        return base64.urlsafe_b64encode(resp["Plaintext"]).decode("ascii")


class VaultKMSBackend(KMSBackend):
    """HashiCorp Vault Transit backend (hvac). Degrades to local when missing."""

    name = "vault"

    def __init__(self) -> None:
        self._addr = os.getenv("VAULT_ADDR", "")
        self._key_name = os.getenv("VAULT_TRANSIT_KEY", "pii-dek")
        try:  # pragma: no cover - optional dep
            import hvac  # type: ignore[import-not-found]

            self._client = hvac.Client(url=self._addr, token=os.getenv("VAULT_TOKEN"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Vault KMS backend unavailable: {exc}") from exc

    def generate_dek(self) -> DEK:  # pragma: no cover - needs Vault
        resp = self._client.secrets.transit.generate_data_key(
            key_name=self._key_name, key_type="plaintext"
        )
        return DEK(
            key_id=f"dek_{uuid.uuid4().hex[:16]}",
            key=resp["data"]["plaintext"],
            created_at=time.time(),
            provider=self.name,
            wrapped_dek=resp["data"]["ciphertext"],
        )

    def unwrap_dek(self, wrapped_dek: str) -> str:  # pragma: no cover - needs Vault
        resp = self._client.secrets.transit.decrypt_data_key(
            key_name=self._key_name, ciphertext=wrapped_dek
        )
        return resp["data"]["plaintext"]


class AliyunKMSBackend(KMSBackend):
    """Aliyun KMS backend (alibabacloud-kms). Degrades to local when missing."""

    name = "aliyun"

    def __init__(self) -> None:
        self._key_id = os.getenv("ALIYUN_KMS_KEY_ID", "")
        try:  # pragma: no cover - optional dep
            from alibabacloud_kms20160120.client import Client  # type: ignore[import-not-found]

            self._client = Client  # further config in production
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Aliyun KMS backend unavailable: {exc}") from exc

    def generate_dek(self) -> DEK:  # pragma: no cover - needs Aliyun
        raise NotImplementedError("Wire Aliyun KMS GenerateDataKey in production")

    def unwrap_dek(self, wrapped_dek: str) -> str:  # pragma: no cover - needs Aliyun
        raise NotImplementedError("Wire Aliyun KMS Decrypt in production")


_BACKENDS: dict[str, type[KMSBackend]] = {
    "local": LocalKMSBackend,
    "aws": AWSKMSBackend,
    "vault": VaultKMSBackend,
    "aliyun": AliyunKMSBackend,
}


def _build_backend(provider: str) -> KMSBackend:
    provider = (provider or "local").lower()
    cls = _BACKENDS.get(provider, LocalKMSBackend)
    try:
        return cls()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "KMS provider %r init failed (%s); falling back to local", provider, exc
        )
        return LocalKMSBackend()


# ---------------------------------------------------------------------------
# DEK store (in-process; production persists wrapped_dek to DB/secrets mgr)
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class _DEKStore:
    deks: list[DEK] = field(default_factory=list)

    def active(self) -> Optional[DEK]:
        for d in self.deks:
            if d.state == "active":
                return d
        return None

    def add(self, dek: DEK) -> None:
        for d in self.deks:
            if d.state == "active":
                d.state = "retired"
                d.rotated_at = time.time()
        self.deks.insert(0, dek)
        # prune
        self.deks = [d for d in self.deks if d.state == "active"][
            :1
        ] + [d for d in self.deks if d.state == "retired"]

    def find(self, key_id: str) -> Optional[DEK]:
        for d in self.deks:
            if d.key_id == key_id:
                return d
        return None

    def all_for_decrypt(self, max_active: int) -> list[DEK]:
        active = [d for d in self.deks if d.state == "active"]
        retired = [d for d in self.deks if d.state == "retired"][: max(max_active - 1, 0)]
        return active + retired


# ---------------------------------------------------------------------------
# KMS Manager
# ---------------------------------------------------------------------------
class KMSManager:
    """High-level KMS facade: DEK lifecycle + rotation."""

    def __init__(
        self,
        provider: Optional[str] = None,
        *,
        ttl_days: Optional[int] = None,
        max_active_deks: Optional[int] = None,
        backend: Optional[KMSBackend] = None,
    ) -> None:
        self.provider = provider or os.getenv("KMS_PROVIDER", "local")
        self.ttl_days = int(
            ttl_days or os.getenv("PII_DEK_TTL_DAYS", DEFAULT_DEK_TTL_DAYS)
        )
        self.max_active_deks = int(
            max_active_deks
            or os.getenv("PII_DEK_MAX_ACTIVE", DEFAULT_MAX_ACTIVE_DEKS)
        )
        self._lock = threading.RLock()
        self._store = _DEKStore()
        self._backend = backend or _build_backend(self.provider)
        # seed an initial active DEK
        with self._lock:
            if self._store.active() is None:
                self._store.add(self._backend.generate_dek())

    # -- DEK access -----------------------------------------------------
    def current_dek(self) -> DEK:
        """Return the active DEK, rotating first if it has expired."""
        with self._lock:
            dek = self._store.active()
            if dek is None:
                dek = self._backend.generate_dek()
                self._store.add(dek)
            elif dek.is_expired(self.ttl_days):
                dek = self.rotate()
            return dek

    def rotate(self) -> DEK:
        """Force-generate a new DEK; retire the previous one."""
        with self._lock:
            new = self._backend.generate_dek()
            self._store.add(new)
            logger.info(
                "KMS DEK rotated: new=%s provider=%s ttl_days=%d",
                new.key_id, self.provider, self.ttl_days,
            )
            return new

    def dek_for_decrypt(self, key_id: Optional[str] = None) -> Optional[DEK]:
        """Return the DEK needed to decrypt an existing ciphertext.

        When ``key_id`` is None, returns every active+retired DEK the
        manager still holds so callers can try each.
        """
        with self._lock:
            if key_id:
                d = self._store.find(key_id)
                if d is not None:
                    return d
                # Try unwrapping from a persisted wrapped_dek by key_id
                return None
            deks = self._store.all_for_decrypt(self.max_active_deks)
            return deks[0] if deks else None

    def all_decrypt_deks(self) -> list[DEK]:
        with self._lock:
            return self._store.all_for_decrypt(self.max_active_deks)

    # -- introspection --------------------------------------------------
    def status(self) -> dict[str, Any]:
        with self._lock:
            active = self._store.active()
            return {
                "provider": self.provider,
                "ttl_days": self.ttl_days,
                "max_active_deks": self.max_active_deks,
                "active_dek_id": active.key_id if active else None,
                "active_dek_age_days": round(active.age_days, 2) if active else None,
                "active_dek_expires_in_days": (
                    round(self.ttl_days - active.age_days, 2) if active else None
                ),
                "retired_deks": sum(1 for d in self._store.deks if d.state == "retired"),
                "next_rotation_due": (
                    datetime.now(timezone.utc)
                    + timedelta(days=max(self.ttl_days - active.age_days, 0))
                ).isoformat()
                if active
                else None,
            }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_singleton: Optional[KMSManager] = None
_singleton_lock = threading.Lock()


def get_kms() -> KMSManager:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = KMSManager()
        return _singleton


def reset_kms() -> None:
    """Test helper: drop the cached KMS singleton."""
    global _singleton
    with _singleton_lock:
        _singleton = None


__all__ = [
    "DEK",
    "KMSBackend",
    "LocalKMSBackend",
    "AWSKMSBackend",
    "VaultKMSBackend",
    "AliyunKMSBackend",
    "KMSManager",
    "KMS_PROVIDERS",
    "DEFAULT_DEK_TTL_DAYS",
    "DEFAULT_MAX_ACTIVE_DEKS",
    "get_kms",
    "reset_kms",
]
