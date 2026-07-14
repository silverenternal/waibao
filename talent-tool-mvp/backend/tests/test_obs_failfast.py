"""v10.0 T5005 — Observability fail-fast gate + telemetry tests.

Covers:
* Production fail-fast: metrics/telemetry must init or the process refuses
  to start (no running blind).
* Non-production graceful degradation.
* Config schema validation (JSON-Schema subset).
* Secret redaction before logging/auditing.
* PII scrubber (id card / phone / email / card / token).
* trace_id generation + thread-local context.
* Prometheus metrics registration: provider_mock_fallback / degraded /
  queue_lag exist with the right labels.
"""

from __future__ import annotations

import threading

import pytest

from services.platform import resilience
from services.platform.resilience import (
    ConfigValidationError,
    clear_trace_id,
    current_trace_id,
    init_production_observability,
    is_production_env,
    new_trace_id,
    redact_secrets,
    scrub_pii,
    set_trace_id,
    validate_config_schema,
)


# ===========================================================================
# Production fail-fast gate
# ===========================================================================
def test_is_production_env_detects_prod(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    assert is_production_env() is True
    monkeypatch.setenv("ENV", "prod-cn")
    assert is_production_env() is True


def test_is_production_env_detects_nonprod(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert is_production_env() is False
    monkeypatch.setenv("ENV", "staging")
    assert is_production_env() is False


def test_init_obs_succeeds_when_metrics_enabled(monkeypatch):
    # Simulate a healthy metrics subsystem.
    monkeypatch.setattr("services.observability.metrics.is_enabled", lambda: True)
    monkeypatch.delenv("ENV", raising=False)
    # must not raise
    init_production_observability()


def test_init_obs_fails_fast_in_production(monkeypatch):
    """In production, a dead metrics subsystem must abort startup."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setattr("services.observability.metrics.is_enabled", lambda: False)
    with pytest.raises(RuntimeError, match="fail-fast"):
        init_production_observability()


def test_init_obs_degrades_in_nonprod(monkeypatch):
    """In non-prod, a dead metrics subsystem logs + continues."""
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setattr("services.observability.metrics.is_enabled", lambda: False)
    # must not raise
    init_production_observability()


def test_init_obs_telemetry_required_fails_fast_in_prod(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setattr("services.observability.metrics.is_enabled", lambda: True)
    monkeypatch.setattr("services.observability.telemetry.get_tracer", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="telemetry"):
        init_production_observability(require_telemetry=True)


def test_init_obs_telemetry_optional_in_nonprod(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setattr("services.observability.metrics.is_enabled", lambda: True)
    monkeypatch.setattr("services.observability.telemetry.get_tracer", lambda *a, **k: None)
    init_production_observability(require_telemetry=True)  # must not raise


# ===========================================================================
# Config schema validation
# ===========================================================================
_OBJECT_SCHEMA = {
    "type": "object",
    "required": ["endpoint"],
    "properties": {
        "endpoint": {"type": "string", "minLength": 1},
        "timeout": {"type": "number", "minimum": 0, "maximum": 300},
        "retries": {"type": "integer", "minimum": 0},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}


def test_schema_validates_good_object():
    out = validate_config_schema(
        {"endpoint": "http://x", "timeout": 5.0, "retries": 3, "tags": ["a", "b"]},
        _OBJECT_SCHEMA,
    )
    assert out["endpoint"] == "http://x"
    assert out["tags"] == ["a", "b"]


def test_schema_rejects_missing_required():
    with pytest.raises(ConfigValidationError, match="endpoint"):
        validate_config_schema({"timeout": 5}, _OBJECT_SCHEMA)


def test_schema_rejects_additional_property():
    with pytest.raises(ConfigValidationError, match="unexpected"):
        validate_config_schema({"endpoint": "x", "evil": True}, _OBJECT_SCHEMA)


def test_schema_rejects_wrong_type():
    with pytest.raises(ConfigValidationError, match="expected number"):
        validate_config_schema({"endpoint": "x", "timeout": "five"}, _OBJECT_SCHEMA)


def test_schema_rejects_below_minimum():
    with pytest.raises(ConfigValidationError, match="minimum"):
        validate_config_schema({"endpoint": "x", "timeout": -1}, _OBJECT_SCHEMA)


def test_schema_rejects_above_maximum():
    with pytest.raises(ConfigValidationError, match="maximum"):
        validate_config_schema({"endpoint": "x", "timeout": 999}, _OBJECT_SCHEMA)


def test_schema_rejects_bool_as_integer():
    """bool is a subclass of int — must not sneak through as integer."""
    with pytest.raises(ConfigValidationError):
        validate_config_schema({"endpoint": "x", "retries": True}, _OBJECT_SCHEMA)


def test_schema_rejects_array_item_wrong_type():
    with pytest.raises(ConfigValidationError):
        validate_config_schema(
            {"endpoint": "x", "tags": ["ok", 123]}, _OBJECT_SCHEMA
        )


def test_schema_passes_through_when_no_schema():
    val = {"anything": "goes", "n": 1}
    assert validate_config_schema(val, None) is val


def test_schema_validates_nested_objects():
    schema = {
        "type": "object",
        "properties": {
            "db": {
                "type": "object",
                "required": ["host"],
                "properties": {"host": {"type": "string"}, "port": {"type": "integer"}},
            }
        },
    }
    out = validate_config_schema({"db": {"host": "h", "port": 5432}}, schema)
    assert out["db"]["port"] == 5432
    with pytest.raises(ConfigValidationError):
        validate_config_schema({"db": {"port": 5432}}, schema)  # missing host


# ===========================================================================
# Secret redaction
# ===========================================================================
def test_redact_secrets_top_level():
    out = redact_secrets({"api_key": "sk-123", "name": "x"})
    assert out["api_key"] == "***REDACTED***"
    assert out["name"] == "x"


def test_redact_secrets_nested():
    out = redact_secrets({
        "service": "llm",
        "config": {"OPENAI_API_KEY": "sk-xxx", "model": "gpt-4o"},
    })
    assert out["config"]["OPENAI_API_KEY"] == "***REDACTED***"
    assert out["config"]["model"] == "gpt-4o"


def test_redact_secrets_does_not_mutate_input():
    src = {"password": "p", "ok": 1}
    out = redact_secrets(src)
    assert src["password"] == "p"  # original untouched
    assert out["password"] == "***REDACTED***"


def test_redact_secrets_handles_lists():
    out = redact_secrets([{"token": "t"}, {"name": "n"}])
    assert out[0]["token"] == "***REDACTED***"
    assert out[1]["name"] == "n"


@pytest.mark.parametrize("key", [
    "password", "PASSWORD", "api_key", "API-KEY", "clientSecret",
    "accessToken", "private_key", "refresh_token",
])
def test_redact_secret_key_patterns(key):
    assert resilience._is_secret_key(key) is True


@pytest.mark.parametrize("key", ["name", "endpoint", "model", "timeout", "version"])
def test_non_secret_keys_not_redacted(key):
    assert resilience._is_secret_key(key) is False


# ===========================================================================
# PII scrubber
# ===========================================================================
def test_scrub_pii_redacts_email():
    out = scrub_pii({"email": "alice@example.com", "name": "alice"})
    assert out["email"] == "***"
    assert out["name"] == "alice"


def test_scrub_pii_redacts_phone():
    out = scrub_pii({"phone": "13812345678"})
    assert out["phone"] == "***"


def test_scrub_pii_redacts_id_card():
    out = scrub_pii({"id_card": "110101199003071234"})
    assert out["id_card"] == "***"


def test_scrub_pii_redacts_in_strings():
    msg = "contact me at alice@example.com or 13812345678"
    out = scrub_pii(msg)
    assert "alice@example.com" not in out
    assert "13812345678" not in out


def test_scrub_pii_redacts_bearer_token():
    out = scrub_pii("Authorization: Bearer abcdefghij1234567890abcdefghij")
    assert "Bearer" in out  # label kept
    assert "abcdefghij1234567890abcdefghij" not in out  # secret gone


def test_scrub_pii_preserves_non_pii():
    out = scrub_pii({"user_id": 42, "org": "acme", "msg": "hello world"})
    assert out == {"user_id": 42, "org": "acme", "msg": "hello world"}


def test_scrub_pii_handles_nested_and_lists():
    out = scrub_pii({"users": [{"email": "a@b.com"}, {"phone": "13900001111"}]})
    assert out["users"][0]["email"] == "***"
    assert out["users"][1]["phone"] == "***"


def test_scrub_pii_custom_replacement():
    out = scrub_pii({"email": "a@b.com"}, replacement="[REDACTED]")
    assert out["email"] == "[REDACTED]"


# ===========================================================================
# trace_id
# ===========================================================================
def test_new_trace_id_is_hex_string():
    tid = new_trace_id()
    assert isinstance(tid, str)
    assert len(tid) == 32  # uuid4 hex
    int(tid, 16)  # parses as hex


def test_current_trace_id_returns_last_generated():
    tid = new_trace_id()
    assert current_trace_id() == tid


def test_set_and_clear_trace_id():
    set_trace_id("external-id-123")
    assert current_trace_id() == "external-id-123"
    clear_trace_id()
    assert current_trace_id() is None


def test_trace_id_thread_local():
    """Each thread gets its own trace id."""
    results = {}

    def worker(name):
        tid = new_trace_id()
        results[name] = tid

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert results["a"] != results["b"]


# ===========================================================================
# Prometheus metrics exist with correct labels
# ===========================================================================
def test_resilience_metrics_registered():
    """provider_mock_fallback / degraded / queue_lag must be registered."""
    from services.observability import metrics

    metrics.init_metrics()
    # the helpers must be callable without error (no-op when disabled)
    metrics.inc_mock_fallback(contract="llm", reason="no_key")
    metrics.inc_degraded(service="flag:x", reason="fail_open")
    metrics.set_queue_lag(queue="eventbus", lag_seconds=1.5)

    if metrics.is_enabled():
        reg = metrics.get_registry()
        # Counter family names drop the _total suffix in the registry's
        # .name attribute; the exposed sample still carries _total.
        families = {m.name for m in reg.collect()}
        samples = {s.name for m in reg.collect() for s in m.samples}
        assert "provider_mock_fallback" in families or "provider_mock_fallback_total" in samples
        assert "service_degraded" in families or "service_degraded_total" in samples
        assert "queue_lag_seconds" in families
