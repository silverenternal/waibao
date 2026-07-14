"""v10.0 T5004 — Provider + Plugin resilience + sandbox tests.

Covers:
* ``ProviderContract`` / ``ProviderErrorKind`` taxonomy + retry mapping.
* Explicit mock gate (``WAIBAO_PROVIDER_MOCK``) — fail-closed by default.
* Docker container sandbox spec + iptables egress deny.
* ``NetworkGuard`` deny-all posture.
* ``SignatureVerifier`` (ed25519 + hmac-sha256) sign/verify/tamper.
"""

from __future__ import annotations

import os
import socket
import threading

import pytest

from providers import (
    AuthError,
    InvalidRequestError,
    MockGateError,
    ProviderContract,
    ProviderErrorKind,
    RateLimitError,
    TimeoutError as ProviderTimeoutError,
    UpstreamUnavailableError,
    make_contract,
)
from providers.base import RetryPolicy
from providers.mock import MockProvider
from providers.registry import _mock_gate_open, assert_mock_gate, record_mock_fallback
from plugins.sdk.manifest import (
    SignatureError,
    SignatureVerifier,
    canonical_manifest_bytes,
    require_signed_manifest,
)
from plugins.sdk.sandbox import (
    ContainerSandboxSpec,
    NetworkGuard,
    SandboxConfig,
    apply_network_mode,
    build_container_spec,
    egress_deny_iptables_rules,
    sandboxed,
)


# ===========================================================================
# ProviderContract basics
# ===========================================================================
def test_contract_defaults_from_env(monkeypatch):
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("PROVIDER_MAX_RETRIES", "7")
    monkeypatch.setenv("PROVIDER_BASE_DELAY", "0.5")
    c = make_contract("openai", "llm")
    assert c.timeout_seconds == 12.0
    assert c.retry.max_retries == 7
    assert c.retry.base_delay == 0.5


def test_contract_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", "99")
    c = make_contract("x", "llm", timeout_seconds=5.0)
    assert c.timeout_seconds == 5.0


def test_contract_rejects_bad_timeout():
    with pytest.raises(ValueError):
        ProviderContract(name="x", contract_type="llm", timeout_seconds=0)


def test_contract_rejects_negative_retries():
    with pytest.raises(ValueError):
        ProviderContract(
            name="x", contract_type="llm", retry=RetryPolicy(max_retries=-1)
        )


def test_contract_to_dict_roundtrip():
    c = ProviderContract(name="x", contract_type="llm", supported_models=["a", "b"])
    d = c.to_dict()
    assert d["name"] == "x"
    assert d["contract_type"] == "llm"
    assert d["supported_models"] == ["a", "b"]
    assert "retry" in d and "timeout_seconds" in d


# ===========================================================================
# ProviderErrorKind taxonomy
# ===========================================================================
@pytest.mark.parametrize("exc,kind,retryable", [
    (ProviderTimeoutError("t"), ProviderErrorKind.TIMEOUT, True),
    (RateLimitError("r"), ProviderErrorKind.RATE_LIMITED, True),
    (UpstreamUnavailableError("u"), ProviderErrorKind.UPSTREAM_UNAVAILABLE, True),
    (AuthError("a"), ProviderErrorKind.AUTH, False),
    (InvalidRequestError("i"), ProviderErrorKind.INVALID_REQUEST, False),
])
def test_error_kind_from_exception(exc, kind, retryable):
    assert ProviderErrorKind.from_exception(exc) == kind
    assert kind.is_retryable() is retryable


def test_error_kind_from_none_is_ok():
    assert ProviderErrorKind.from_exception(None) == ProviderErrorKind.OK
    assert ProviderErrorKind.OK.is_retryable() is False


def test_error_kind_from_generic_exception():
    assert ProviderErrorKind.from_exception(ValueError("x")) == ProviderErrorKind.UNKNOWN


def test_error_kind_string_value():
    # values are stable strings usable as Prometheus labels
    assert ProviderErrorKind.RATE_LIMITED.value == "rate_limited"
    assert ProviderErrorKind.CIRCUIT_OPEN.value == "circuit_open"


# ===========================================================================
# Explicit mock gate
# ===========================================================================
def test_mock_gate_closed_by_default(monkeypatch):
    monkeypatch.delenv("WAIBAO_PROVIDER_MOCK", raising=False)
    assert _mock_gate_open() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on"])
def test_mock_gate_opens_with_env(monkeypatch, val):
    monkeypatch.setenv("WAIBAO_PROVIDER_MOCK", val)
    assert _mock_gate_open() is True


@pytest.mark.parametrize("val", ["0", "false", "", "no"])
def test_mock_gate_stays_closed(monkeypatch, val):
    monkeypatch.setenv("WAIBAO_PROVIDER_MOCK", val)
    assert _mock_gate_open() is False


def test_assert_mock_gate_raises_when_closed(monkeypatch):
    monkeypatch.delenv("WAIBAO_PROVIDER_MOCK", raising=False)
    with pytest.raises(MockGateError):
        assert_mock_gate()


def test_assert_mock_gate_passes_when_open(monkeypatch):
    monkeypatch.setenv("WAIBAO_PROVIDER_MOCK", "1")
    assert_mock_gate()  # must not raise


def test_assert_mock_gate_allow_mock_bypasses(monkeypatch):
    monkeypatch.delenv("WAIBAO_PROVIDER_MOCK", raising=False)
    assert_mock_gate(allow_mock=True)  # explicit test bypass


def test_mock_provider_declares_mock_enabled():
    m = MockProvider("llm")
    assert m.provider_contract.mock_enabled is True
    assert m.provider_contract.name == "mock_llm"
    assert m.provider_contract.contract_type == "llm"


def test_contract_assert_real_allowed_fails_for_mock(monkeypatch):
    monkeypatch.delenv("WAIBAO_PROVIDER_MOCK", raising=False)
    m = MockProvider("llm")
    with pytest.raises(MockGateError):
        m.provider_contract.assert_real_allowed()


def test_contract_assert_real_allowed_passes_when_gate_open(monkeypatch):
    monkeypatch.setenv("WAIBAO_PROVIDER_MOCK", "1")
    m = MockProvider("llm")
    m.provider_contract.assert_real_allowed()  # ok


def test_record_mock_fallback_does_not_raise():
    # metrics may be disabled in tests — must be a no-op, never raise.
    record_mock_fallback("llm", reason="no_key")


# ===========================================================================
# Docker container sandbox spec
# ===========================================================================
def test_container_spec_defaults_hardened():
    spec = ContainerSandboxSpec()
    args = spec.to_docker_args()
    assert "--network=none" in args
    assert any(a.startswith("--memory=") for a in args)
    assert any(a.startswith("--cpus=") for a in args)
    assert "--read-only" in args
    assert "--security-opt=no-new-privileges" in args
    assert "--cap-drop=ALL" in args
    assert "--user=65534:65534" in args
    assert any(a.startswith("--tmpfs=/tmp") for a in args)


def test_container_spec_env_passthrough():
    spec = ContainerSandboxSpec(env={"FOO": "bar"})
    assert "-e=FOO=bar" in spec.to_docker_args()


def test_build_container_spec_deny_all_uses_no_network():
    cfg = SandboxConfig(network_mode="deny_all")
    spec = build_container_spec(cfg)
    assert spec.network == "none"


def test_build_container_spec_allowlist_uses_default_network():
    cfg = SandboxConfig(network_mode="allowlist", allow_network_hosts=["api.x.com"])
    spec = build_container_spec(cfg)
    assert spec.network == "default"


def test_egress_deny_iptables_rules_shape():
    rules = egress_deny_iptables_rules()
    # loopback first, then DROP
    assert "iptables -A OUTPUT -o lo -j ACCEPT" in rules
    assert "iptables -A OUTPUT -j DROP" in rules
    assert rules.index("iptables -A OUTPUT -o lo -j ACCEPT") < rules.index(
        "iptables -A OUTPUT -j DROP"
    )


def test_apply_network_mode_surfaces_posture():
    assert apply_network_mode(SandboxConfig(network_mode="deny_all")) == "deny_all"
    assert apply_network_mode(
        SandboxConfig(network_mode="allowlist", allow_network_hosts=["x"])
    ) == "allowlist"
    assert apply_network_mode(
        SandboxConfig(network_mode="allowlist", allow_network_hosts=[])
    ) == "open"


# ===========================================================================
# NetworkGuard deny-all posture
# ===========================================================================
def test_network_guard_deny_all_blocks_create_connection():
    with NetworkGuard(mode="deny_all"):
        with pytest.raises(PermissionError):
            socket.create_connection(("1.1.1.1", 53), timeout=0.1)


def test_network_guard_deny_all_is_allowed_never_true():
    g = NetworkGuard(mode="deny_all")
    assert g._is_allowed("anything.com") is False
    assert g._is_allowed("localhost") is False


def test_network_guard_allowlist_still_works():
    g = NetworkGuard(allow=["allowed.example.com"], mode="allowlist")
    assert g._is_allowed("allowed.example.com") is True
    assert g._is_allowed("blocked.example.com") is False


def test_network_guard_restores_socket_on_exit():
    real = socket.socket
    real_create = socket.create_connection
    with NetworkGuard(mode="deny_all"):
        pass
    assert socket.socket is real
    assert socket.create_connection is real_create


def test_sandboxed_with_deny_all_blocks_connect(monkeypatch):
    # tmp dir not required for network-only test
    with sandboxed(SandboxConfig(network_mode="deny_all", allow_network_hosts=[])):
        with pytest.raises(PermissionError):
            socket.create_connection(("1.1.1.1", 53), timeout=0.1)


# ===========================================================================
# SignatureVerifier — ed25519
# ===========================================================================
def _ed25519_keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    priv = Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    import base64

    pub_b64 = base64.urlsafe_b64encode(pub_raw).decode().rstrip("=")
    return priv, pub_b64


def test_signature_ed25519_roundtrip():
    priv, pub_b64 = _ed25519_keypair()
    manifest = {
        "name": "x", "version": "1.0.0", "entry_point": "m:C",
        "permissions": ["db:read"],
    }
    sig = SignatureVerifier.sign(manifest, private_key=priv)
    v = SignatureVerifier(public_key=pub_b64)
    assert v.verify(manifest, sig) is not None


def test_signature_ed25519_detects_tamper():
    priv, pub_b64 = _ed25519_keypair()
    manifest = {"name": "x", "version": "1.0.0", "entry_point": "m:C"}
    sig = SignatureVerifier.sign(manifest, private_key=priv)
    v = SignatureVerifier(public_key=pub_b64)
    with pytest.raises(SignatureError):
        v.verify({**manifest, "version": "2.0.0"}, sig)


def test_signature_ed25519_rejects_wrong_key():
    priv, _ = _ed25519_keypair()
    _, other_pub = _ed25519_keypair()
    manifest = {"name": "x", "version": "1.0.0", "entry_point": "m:C"}
    sig = SignatureVerifier.sign(manifest, private_key=priv)
    v = SignatureVerifier(public_key=other_pub)
    with pytest.raises(SignatureError):
        v.verify(manifest, sig)


def test_signature_rejects_empty():
    v = SignatureVerifier(shared_key="k")
    with pytest.raises(SignatureError):
        v.verify({"name": "x", "version": "1.0.0", "entry_point": "m"}, "")


def test_signature_rejects_bad_base64():
    v = SignatureVerifier(shared_key="k")
    with pytest.raises(SignatureError):
        v.verify({"name": "x", "version": "1.0.0", "entry_point": "m"}, "!!!not-base64!!!")


# ===========================================================================
# SignatureVerifier — hmac-sha256
# ===========================================================================
def test_signature_hmac_roundtrip():
    manifest = {"name": "x", "version": "1.0.0", "entry_point": "m:C"}
    sig = SignatureVerifier.sign(manifest, shared_key="secret")
    SignatureVerifier(shared_key="secret").verify(manifest, sig)


def test_signature_hmac_wrong_key_detected():
    manifest = {"name": "x", "version": "1.0.0", "entry_point": "m:C"}
    sig = SignatureVerifier.sign(manifest, shared_key="secret")
    with pytest.raises(SignatureError):
        SignatureVerifier(shared_key="other").verify(manifest, sig)


def test_signature_hmac_detects_tamper():
    manifest = {"name": "x", "version": "1.0.0", "entry_point": "m:C"}
    sig = SignatureVerifier.sign(manifest, shared_key="secret")
    with pytest.raises(SignatureError):
        SignatureVerifier(shared_key="secret").verify(
            {**manifest, "permissions": ["admin"]}, sig
        )


# ===========================================================================
# SignatureVerifier construction + canonicalisation
# ===========================================================================
def test_canonical_bytes_deterministic():
    manifest = {"name": "x", "version": "1.0.0", "entry_point": "m:C",
                "permissions": ["b", "a"]}
    b1 = canonical_manifest_bytes(manifest)
    b2 = canonical_manifest_bytes(
        {"entry": "m:C", "version": "1.0.0", "name": "x", "permissions": ["a", "b"]}
    )
    assert b1 == b2  # key order + perm order must not matter


def test_verifier_rejects_unknown_alg():
    with pytest.raises(SignatureError):
        SignatureVerifier(shared_key="k", alg="rsa-fake")


def test_verifier_ed25519_requires_public_key():
    with pytest.raises(SignatureError):
        SignatureVerifier(alg="ed25519")


def test_require_signed_manifest_returns_bytes():
    manifest = {"name": "x", "version": "1.0.0", "entry_point": "m:C"}
    sig = SignatureVerifier.sign(manifest, shared_key="k")
    v = SignatureVerifier(shared_key="k")
    out = require_signed_manifest(v, manifest, sig)
    assert isinstance(out, bytes)


def test_sign_requires_key():
    with pytest.raises(SignatureError):
        SignatureVerifier.sign({"name": "x", "version": "1.0.0", "entry_point": "m"})
