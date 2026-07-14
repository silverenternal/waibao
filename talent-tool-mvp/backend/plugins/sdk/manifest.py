"""plugin.yaml manifest parser for the plugin SDK."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # manifest parsing requires PyYAML; explicit error raised below


# Strict semver-ish regex. We don't enforce the whole spec — just basic shape.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([\-+][\w.]+)?$")
# Allowed permission tokens — anything else triggers a validation error.
_VALID_PERMS = {
    "db:read", "db:write",
    "events:emit", "events:subscribe",
    "http:call", "http:listen",
    "files:read", "files:write",
    "llm:call",
    "metrics:emit",
    "admin",
}


@dataclass
class PluginManifest:
    name: str
    version: str
    entry_point: str
    type: str = "agent"
    author: str = "unknown"
    description: str = ""
    permissions: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    source_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "version": self.version, "entry_point": self.entry_point,
            "type": self.type, "author": self.author, "description": self.description,
            "permissions": list(self.permissions), "config_schema": dict(self.config_schema),
            "dependencies": list(self.dependencies), "source_path": self.source_path,
        }


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ManifestError(ValueError):
    """Raised when a plugin.yaml is malformed or fails validation."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _require_yaml() -> None:
    if yaml is None:  # pragma: no cover
        raise ManifestError("PyYAML is required for plugin manifests: pip install pyyaml")


def parse_manifest(data: Dict[str, Any], *, source_path: str = "") -> PluginManifest:
    """Validate and convert a raw dict (loaded from plugin.yaml) into a
    PluginManifest instance."""
    _require_yaml()

    if not isinstance(data, dict):
        raise ManifestError("plugin manifest must be a mapping")

    name = data.get("name")
    version = data.get("version")
    entry_point = data.get("entry_point") or data.get("entry")

    if not name or not isinstance(name, str):
        raise ManifestError("manifest.name is required (str)")
    if not version or not _VERSION_RE.match(str(version)):
        raise ManifestError(f"manifest.version {version!r} is not valid semver")
    if not entry_point or not isinstance(entry_point, str):
        raise ManifestError("manifest.entry_point is required (str)")

    permissions = data.get("permissions") or []
    if not isinstance(permissions, list):
        raise ManifestError("manifest.permissions must be a list")
    bad = [p for p in permissions if p not in _VALID_PERMS]
    if bad:
        raise ManifestError(f"manifest.permissions contains invalid tokens: {bad}")

    return PluginManifest(
        name=name,
        version=str(version),
        entry_point=entry_point,
        type=str(data.get("type", "agent")),
        author=str(data.get("author", "unknown")),
        description=str(data.get("description", "")),
        permissions=list(permissions),
        config_schema=dict(data.get("config_schema") or {}),
        dependencies=list(data.get("dependencies") or []),
        source_path=source_path,
    )


def load_manifest_file(path: str) -> PluginManifest:
    _require_yaml()
    if not os.path.isfile(path):
        raise ManifestError(f"manifest file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return parse_manifest(raw or {}, source_path=path)


def load_entry_point(manifest: PluginManifest) -> Any:
    """Import `module:attr` and return the resolved Plugin subclass instance.

    The runner wraps this in exception isolation, so any import error is
    surfaced as a PluginLoadError (caught by the runner).
    """
    module_name, _, attr = manifest.entry_point.partition(":")
    if not module_name or not attr:
        raise ManifestError(
            f"manifest.entry_point must be 'module.path:Class' — got {manifest.entry_point!r}"
        )
    import importlib
    module = importlib.import_module(module_name)
    cls = getattr(module, attr, None)
    if cls is None:
        raise ManifestError(f"{module_name}.{attr} not found")
    if not isinstance(cls, type):
        raise ManifestError(f"{module_name}.{attr} must be a class")
    return cls()


# ===========================================================================
# v10.0 T5004 — Manifest signature verification
# ===========================================================================
#
# A signed plugin bundle ships a detached signature over the canonical
# manifest bytes. The loader refuses to install a plugin whose signature
# does not verify against the configured public key. This closes the audit
# finding that a malicious plugin.yaml could be dropped into the plugins
# directory and auto-loaded.

import binascii
import hashlib
import hmac as _hmac


class SignatureError(ManifestError):
    """Raised when a plugin manifest signature is missing, malformed, or
    does not verify against the trusted key."""


# Algorithms we accept. ``ed25519`` is the default (asymmetric, modern);
# ``hmac-sha256`` is the symmetric fallback for environments without the
# ``cryptography`` package.
SUPPORTED_SIG_ALGS = ("ed25519", "hmac-sha256")


def _b64decode(value: str) -> bytes:
    """URL-safe base64 decode with padding tolerance."""
    import base64

    try:
        pad = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + pad)
    except (binascii.Error, ValueError) as exc:
        raise SignatureError(f"signature is not valid base64: {exc}") from exc


def _b64encode(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def canonical_manifest_bytes(manifest: Any) -> bytes:
    """Serialise a manifest to a deterministic byte string for signing.

    We sort keys and emit compact JSON so that signing is reproducible across
    machines / Python versions. ``manifest`` may be a :class:`PluginManifest`
    or a raw dict (pre-parse).
    """
    import json

    if isinstance(manifest, PluginManifest):
        payload = {
            "name": manifest.name,
            "version": manifest.version,
            "entry_point": manifest.entry_point,
            "type": manifest.type,
            "permissions": sorted(manifest.permissions),
            "dependencies": sorted(manifest.dependencies),
        }
    elif isinstance(manifest, dict):
        payload = {
            "name": manifest.get("name"),
            "version": manifest.get("version"),
            "entry_point": manifest.get("entry_point") or manifest.get("entry"),
            "type": manifest.get("type", "agent"),
            "permissions": sorted(manifest.get("permissions") or []),
            "dependencies": sorted(manifest.get("dependencies") or []),
        }
    else:
        raise SignatureError(f"cannot canonicalise manifest of type {type(manifest)!r}")
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class SignatureVerifier:
    """Verify detached plugin manifest signatures.

    Construction:

    * ``SignatureVerifier(public_key=<ed25519-pub-b64>)`` — asymmetric.
    * ``SignatureVerifier(shared_key=<bytes-or-str>)`` — symmetric HMAC.

    The verifier is deliberately stateless and side-effect free. It raises
    :class:`SignatureError` on any verification failure and returns the
    canonical bytes on success so callers can re-sign / log them.
    """

    def __init__(self, *, public_key: Optional[str] = None,
                 shared_key: Optional[Any] = None,
                 alg: Optional[str] = None) -> None:
        self.public_key = public_key
        self.shared_key = shared_key
        if alg is None:
            alg = "ed25519" if public_key else "hmac-sha256"
        if alg not in SUPPORTED_SIG_ALGS:
            raise SignatureError(f"unsupported signature alg {alg!r}")
        if alg == "ed25519" and not public_key:
            raise SignatureError("ed25519 verification requires public_key")
        if alg == "hmac-sha256" and shared_key is None:
            raise SignatureError("hmac-sha256 verification requires shared_key")
        self.alg = alg

    # ---- verification -----------------------------------------------------
    def verify(self, manifest: Any, signature: str) -> bytes:
        """Verify ``signature`` over ``manifest``.

        Raises :class:`SignatureError` on failure. Returns the canonical
        manifest bytes that were verified.
        """
        if not signature:
            raise SignatureError("signature is empty")
        payload = canonical_manifest_bytes(manifest)
        sig_bytes = _b64decode(signature)
        if self.alg == "ed25519":
            self._verify_ed25519(payload, sig_bytes)
        else:
            self._verify_hmac(payload, sig_bytes)
        return payload

    def _verify_ed25519(self, payload: bytes, signature: bytes) -> None:
        try:
            from cryptography.exceptions import InvalidSignature  # type: ignore
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # type: ignore
                Ed25519PublicKey,
            )
        except ImportError as exc:  # pragma: no cover
            raise SignatureError(
                "ed25519 verification requires the 'cryptography' package"
            ) from exc
        try:
            pub_bytes = _b64decode(self.public_key)  # type: ignore[arg-type]
            pub = Ed25519PublicKey.from_public_bytes(pub_bytes)
            pub.verify(signature, payload)
        except InvalidSignature as exc:
            raise SignatureError("ed25519 signature did not verify") from exc
        except (ValueError, TypeError) as exc:
            raise SignatureError(f"ed25519 verification error: {exc}") from exc

    def _verify_hmac(self, payload: bytes, signature: bytes) -> None:
        key = self.shared_key
        if isinstance(key, str):
            key = key.encode("utf-8")
        expected = _hmac.new(key, payload, hashlib.sha256).digest()
        if not _hmac.compare_digest(expected, signature):
            raise SignatureError("hmac-sha256 signature did not verify")

    # ---- signing (for trusted publishers / tests) ------------------------
    @staticmethod
    def sign(manifest: Any, *, private_key: Any = None,
             shared_key: Optional[Any] = None) -> str:
        """Produce a detached signature for trusted publishers.

        Either ``private_key`` (an Ed25519PrivateKey object or b64 string) or
        ``shared_key`` (bytes/str) must be supplied. Returns the URL-safe
        base64 signature string.
        """
        payload = canonical_manifest_bytes(manifest)
        if private_key is not None:
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # type: ignore
                    Ed25519PrivateKey,
                )
            except ImportError as exc:  # pragma: no cover
                raise SignatureError(
                    "ed25519 signing requires the 'cryptography' package"
                ) from exc
            if isinstance(private_key, str):
                # treat as raw b64 of the 32-byte seed first, else PEM
                try:
                    seed = _b64decode(private_key)
                    key = Ed25519PrivateKey.from_private_bytes(seed)
                except Exception:
                    from cryptography.hazmat.primitives.serialization import (  # type: ignore
                        load_pem_private_key,
                    )
                    key = load_pem_private_key(private_key.encode(), password=None)
            else:
                key = private_key
            raw = key.sign(payload)
            return _b64encode(raw)
        if shared_key is not None:
            key = shared_key.encode("utf-8") if isinstance(shared_key, str) else shared_key
            raw = _hmac.new(key, payload, hashlib.sha256).digest()
            return _b64encode(raw)
        raise SignatureError("sign() requires private_key or shared_key")


def require_signed_manifest(verifier: SignatureVerifier, manifest: Any,
                            signature: str) -> bytes:
    """Convenience wrapper used by the loader: verify or raise.

    Returns the canonical bytes on success so callers can log exactly what
    was attested.
    """
    return verifier.verify(manifest, signature)