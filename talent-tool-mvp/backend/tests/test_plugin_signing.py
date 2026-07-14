"""T5023 — ed25519 plugin signing tests."""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from plugins.sdk.signing import (  # noqa: E402
    KeyPair,
    SignatureError,
    sign_manifest,
    verify,
    verify_manifest,
)


def test_keypair_generate_produces_distinct_keys():
    a = KeyPair.generate()
    b = KeyPair.generate()
    assert a.private_key_b64 != b.private_key_b64
    assert a.public_key_b64 != b.public_key_b64
    assert a.public_key_b64  # non-empty


def test_sign_then_verify_roundtrip():
    kp = KeyPair.generate()
    payload = {"plugin": "ats-sync", "version": "1.2.0", "scopes": ["read:candidates"]}
    sig = kp.sign(payload)
    assert verify(kp.public_key_b64, payload, sig) is True


def test_verify_rejects_tampered_payload():
    kp = KeyPair.generate()
    payload = {"plugin": "ats-sync", "version": "1.0.0"}
    sig = kp.sign(payload)
    tampered = dict(payload, version="9.9.9")
    assert verify(kp.public_key_b64, tampered, sig) is False


def test_verify_rejects_wrong_key():
    kp_a = KeyPair.generate()
    kp_b = KeyPair.generate()
    payload = {"x": 1}
    sig = kp_a.sign(payload)
    assert verify(kp_b.public_key_b64, payload, sig) is False


def test_verify_rejects_malformed_signature():
    kp = KeyPair.generate()
    with pytest.raises(SignatureError):
        verify(kp.public_key_b64, {"x": 1}, "!!!notbase64!!!")


def test_canonical_payload_is_order_independent():
    kp = KeyPair.generate()
    payload_a = {"a": 1, "b": 2}
    payload_b = {"b": 2, "a": 1}
    sig = kp.sign(payload_a)
    assert verify(kp.public_key_b64, payload_b, sig) is True


def test_sign_manifest_and_verify_roundtrip():
    kp = KeyPair.generate()
    manifest = {
        "name": "ats-sync",
        "version": "1.0.0",
        "entrypoint": "main.py",
        "permissions": ["read:candidates"],
    }
    signed = sign_manifest(manifest, kp)
    assert "signature" in signed
    assert "signing_key" in signed
    assert "content_sha256" in signed
    assert verify_manifest(signed) is True


def test_signed_manifest_rejects_tampering():
    kp = KeyPair.generate()
    manifest = {"name": "ats-sync", "version": "1.0.0", "permissions": ["read"]}
    signed = sign_manifest(manifest, kp)
    tampered = copy.deepcopy(signed)
    tampered["permissions"] = ["read", "write", "admin"]  # privilege escalation
    assert verify_manifest(tampered) is False


def test_unsigned_manifest_raises():
    with pytest.raises(SignatureError):
        verify_manifest({"name": "x"})
