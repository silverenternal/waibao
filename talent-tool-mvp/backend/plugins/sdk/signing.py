"""T5023 — ed25519 plugin signing + verification.

Plugins are cryptographically signed so the loader can reject tampered or
untrusted code before it ever reaches the sandbox. This module uses
ed25519 (fast, small signatures, deterministic):

* **KeyPair.generate()** — create a new signing key + verification key.
* **KeyPair.sign(payload)** — produce a detached signature.
* **verify(public_key, payload, signature)** — verify a signature.

We vendor two backends:

  1. ``cryptography`` (preferred — already a project dependency for PII).
  2. ``nacl`` (PyNaCl) fallback.

Keys + signatures are encoded as urlsafe base64 for easy JSON transport.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SignatureError(Exception):
    """Raised when signing/verification fails or inputs are malformed."""


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _ub64(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _canonical(payload: Any) -> bytes:
    """Canonical serialisation of the payload prior to signing.

    Deterministic JSON (sorted keys, no whitespace) so that the same
    logical payload always produces the same digest.
    """
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


# ---------------------------------------------------------------------------
# Key pair
# ---------------------------------------------------------------------------

@dataclass
class KeyPair:
    """An ed25519 signing key + its verification key (both base64)."""

    private_key_b64: str
    public_key_b64: str
    backend: str = "cryptography"

    # ------------------------------------------------------------------
    @classmethod
    def generate(cls) -> "KeyPair":
        last_exc: Optional[Exception] = None
        for backend in ("cryptography", "nacl"):
            try:
                return getattr(cls, f"_gen_{backend}")()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.debug("ed25519 backend %s unavailable: %s", backend, exc)
        raise SignatureError(f"no ed25519 backend available: {last_exc}")

    # ------------------------------------------------------------------
    def sign(self, payload: Any) -> str:
        msg = _canonical(payload)
        try:
            return _b64(self._signing_key().sign(msg))
        except Exception as exc:  # noqa: BLE001
            raise SignatureError(f"signing failed: {exc}") from exc

    def public_key(self) -> str:
        return self.public_key_b64

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------
    def _signing_key(self):
        if self.backend == "cryptography":
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            return Ed25519PrivateKey.from_private_bytes(_ub64(self.private_key_b64))
        from nacl.signing import SigningKey  # type: ignore
        return SigningKey(_ub64(self.private_key_b64))

    @classmethod
    def _gen_cryptography(cls) -> "KeyPair":
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
        )
        priv = Ed25519PrivateKey.generate()
        priv_bytes = priv.private_bytes(
            encoding=Encoding.Raw,
            format=PrivateFormat.Raw,
            encryption_algorithm=NoEncryption(),
        )
        pub_bytes = priv.public_key().public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )
        return cls(
            private_key_b64=_b64(priv_bytes),
            public_key_b64=_b64(pub_bytes),
            backend="cryptography",
        )

    @classmethod
    def _gen_nacl(cls) -> "KeyPair":
        from nacl.signing import SigningKey  # type: ignore
        sk = SigningKey.generate()
        return cls(
            private_key_b64=_b64(bytes(sk)),
            public_key_b64=_b64(bytes(sk.verify_key)),
            backend="nacl",
        )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify(public_key_b64: str, payload: Any, signature_b64: str) -> bool:
    """Return True iff ``signature_b64`` is a valid ed25519 signature of
    ``payload`` under ``public_key_b64``. Raises :class:`SignatureError`
    on malformed input."""
    try:
        pub_bytes = _ub64(public_key_b64)
        sig_bytes = _ub64(signature_b64)
    except Exception as exc:  # noqa: BLE001
        raise SignatureError(f"malformed key/signature: {exc}") from exc
    msg = _canonical(payload)
    last_exc: Optional[Exception] = None
    for backend in ("cryptography", "nacl"):
        try:
            return _verify_with(backend, pub_bytes, msg, sig_bytes)
        except SignatureError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.debug("verify backend %s failed: %s", backend, exc)
    raise SignatureError(f"verification failed: {last_exc}")


def _verify_with(backend: str, pub_bytes: bytes, msg: bytes, sig_bytes: bytes) -> bool:
    if backend == "cryptography":
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
        vk = Ed25519PublicKey.from_public_bytes(pub_bytes)
        try:
            vk.verify(sig_bytes, msg)
            return True
        except InvalidSignature:
            return False
    from nacl.signing import VerifyKey  # type: ignore
    from nacl.exceptions import BadSignatureError  # type: ignore
    try:
        VerifyKey(pub_bytes).verify(msg, sig_bytes)
        return True
    except BadSignatureError:
        return False


# ---------------------------------------------------------------------------
# Manifest signing helper
# ---------------------------------------------------------------------------

def sign_manifest(manifest: dict[str, Any], key_pair: KeyPair) -> dict[str, Any]:
    """Attach ``signature`` + ``signing_key`` to a manifest dict.

    The signature covers the manifest minus the signature fields, so it is
    stable across re-serialisation.
    """
    body = {k: v for k, v in manifest.items() if k not in ("signature", "signing_key")}
    digest = hashlib.sha256(_canonical(body)).hexdigest()
    sig = key_pair.sign(body)
    return {**manifest, "signature": sig, "signing_key": key_pair.public_key_b64,
            "content_sha256": digest}


def verify_manifest(manifest: dict[str, Any]) -> bool:
    sig = manifest.get("signature")
    key = manifest.get("signing_key")
    if not sig or not key:
        raise SignatureError("manifest is missing signature/signing_key")
    body = {k: v for k, v in manifest.items()
            if k not in ("signature", "signing_key", "content_sha256")}
    return verify(key, body, sig)
