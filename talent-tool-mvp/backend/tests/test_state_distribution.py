"""v10.0 T5005 — Distributed state tests (Redis CAS + fail-open/closed)."""

from __future__ import annotations

import threading
import time

import pytest

from services.platform import resilience
from services.platform.resilience import (
    CASResult,
    ConfigValidationError,
    RedisCAS,
    distributed_flag_enabled,
    fail_closed,
    fail_open,
    redact_secrets,
    reset_redis_for_tests,
)


# ===========================================================================
# Fake Redis client — emulates SET NX PX, GET, DEL, EVAL (the subset CAS uses)
# ===========================================================================
class FakeRedis:
    """A minimal thread-safe in-memory Redis for CAS tests.

    It implements the exact calls ``RedisCAS`` makes: ``set(nx=, px=)``,
    ``get``, ``eval`` (for the two Lua scripts), and ``ping``.
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl: dict[str, float] = {}
        self._lock = threading.Lock()

    def ping(self) -> bool:
        return True

    def _expired(self, key: str) -> bool:
        exp = self.ttl.get(key)
        return exp is not None and exp < time.monotonic()

    def set(self, key, value, *, nx=False, px=None):
        with self._lock:
            if self._expired(key):
                self.store.pop(key, None)
                self.ttl.pop(key, None)
            if nx and key in self.store:
                return None
            self.store[key] = value
            if px is not None:
                self.ttl[key] = time.monotonic() + px / 1000.0
            else:
                self.ttl.pop(key, None)
            return True

    def get(self, key):
        with self._lock:
            if self._expired(key):
                self.store.pop(key, None)
                self.ttl.pop(key, None)
            return self.store.get(key)

    def delete(self, key):
        with self._lock:
            existed = key in self.store
            self.store.pop(key, None)
            self.ttl.pop(key, None)
            return 1 if existed else 0

    def eval(self, script, numkeys, *args):
        # CAS compare_and_set script: KEYS[1]=key ARGV[1]=expected ARGV[2]=new
        if "GET" in script and "ARGV[1]" in script and "SET" in script and "DEL" not in script:
            key = args[0]
            expected = args[1]
            new = args[2]
            with self._lock:
                if self.store.get(key) == expected:
                    self.store[key] = new
                    return 1
                return 0
        # release script: GET == ARGV[1] then DEL
        if "DEL" in script:
            key = args[0]
            owner = args[1]
            with self._lock:
                if self.store.get(key) == owner:
                    self.store.pop(key, None)
                    self.ttl.pop(key, None)
                    return 1
                return 0
        raise NotImplementedError(f"FakeRedis.eval unknown script: {script!r}")


@pytest.fixture
def fake_redis(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(resilience, "_get_redis", lambda: client)
    return client


@pytest.fixture(autouse=True)
def _reset_redis():
    reset_redis_for_tests()
    yield
    reset_redis_for_tests()


# ===========================================================================
# CAS — in-process fallback (no Redis)
# ===========================================================================
def test_cas_set_if_absent_inprocess():
    cas = RedisCAS()
    assert cas.set_if_absent("k", "A", ttl_s=5) is True
    assert cas.set_if_absent("k", "B", ttl_s=5) is False  # already held


def test_cas_release_inprocess():
    cas = RedisCAS()
    cas.set_if_absent("k", "A", ttl_s=5)
    assert cas.release("k", "A") is True
    assert cas.release("k", "A") is False  # already released


def test_cas_release_rejects_wrong_owner_inprocess():
    cas = RedisCAS()
    cas.set_if_absent("k", "A", ttl_s=5)
    assert cas.release("k", "B") is False


def test_cas_compare_and_set_inprocess():
    cas = RedisCAS()
    cas.set_if_absent("k", "A", ttl_s=5)
    res = cas.compare_and_set("k", "A", "B")
    assert isinstance(res, CASResult)
    assert res.success is True
    # mismatch
    res2 = cas.compare_and_set("k", "A", "C")
    assert res2.success is False


def test_cas_inprocess_ttl_expiry():
    cas = RedisCAS()
    cas.set_if_absent("k", "A", ttl_s=0.05)
    time.sleep(0.08)
    # after expiry the lock is acquirable again
    assert cas.set_if_absent("k", "B", ttl_s=5) is True


# ===========================================================================
# CAS — Redis path (via fake_redis fixture)
# ===========================================================================
def test_cas_redis_set_if_absent(fake_redis):
    cas = RedisCAS()
    assert cas.set_if_absent("k", "A", ttl_s=5) is True
    assert cas.set_if_absent("k", "B", ttl_s=5) is False


def test_cas_redis_release(fake_redis):
    cas = RedisCAS()
    cas.set_if_absent("k", "A", ttl_s=5)
    assert cas.release("k", "A") is True
    assert cas.release("k", "A") is False


def test_cas_redis_release_wrong_owner(fake_redis):
    cas = RedisCAS()
    cas.set_if_absent("k", "A", ttl_s=5)
    assert cas.release("k", "B") is False


def test_cas_redis_compare_and_set_success(fake_redis):
    cas = RedisCAS()
    cas.set_if_absent("k", "A", ttl_s=5)
    res = cas.compare_and_set("k", "A", "B")
    assert res.success is True
    assert res.reason == "redis.cas_ok"


def test_cas_redis_compare_and_set_mismatch(fake_redis):
    cas = RedisCAS()
    cas.set_if_absent("k", "A", ttl_s=5)
    res = cas.compare_and_set("k", "X", "B")
    assert res.success is False
    assert res.reason == "redis.cas_mismatch"


def test_cas_redis_ttl_expiry(fake_redis):
    cas = RedisCAS()
    cas.set_if_absent("k", "A", ttl_s=0.05)
    time.sleep(0.08)
    assert cas.set_if_absent("k", "B", ttl_s=5) is True


# ===========================================================================
# CAS — concurrent contention (the whole point of distributed state)
# ===========================================================================
def test_cas_only_one_writer_wins(fake_redis):
    """Under contention, exactly one of N writers acquires the lock."""
    cas = RedisCAS()
    winners = []
    barrier = threading.Barrier(10)

    def contender(i):
        barrier.wait()
        if cas.set_if_absent("shared", f"w{i}", ttl_s=10):
            winners.append(i)

    threads = [threading.Thread(target=contender, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(winners) == 1


# ===========================================================================
# fail-open / fail-closed
# ===========================================================================
def test_fail_open_returns_default_on_error():
    assert fail_open("svc", check=lambda: 1 / 0, default=True) is True
    assert fail_open("svc", check=lambda: 1 / 0, default=False) is False


def test_fail_open_returns_check_value_on_success():
    assert fail_open("svc", check=lambda: True) is True
    assert fail_open("svc", check=lambda: False) is False


def test_fail_closed_returns_false_on_error():
    assert fail_closed("svc", check=lambda: 1 / 0) is False


def test_fail_closed_returns_check_value_on_success():
    assert fail_closed("svc", check=lambda: True) is True


def test_distributed_flag_enabled_fail_open(monkeypatch):
    # feature_flag with no store returns False for unknown flags; if the
    # read itself throws, fail_open returns True.
    def boom():
        raise RuntimeError("store down")
    monkeypatch.setattr(
        "services.platform.feature_flag.is_enabled", lambda *a, **k: boom()
    )
    assert distributed_flag_enabled("f", posture="fail_open") is True


def test_distributed_flag_enabled_fail_closed(monkeypatch):
    def boom():
        raise RuntimeError("store down")
    monkeypatch.setattr(
        "services.platform.feature_flag.is_enabled", lambda *a, **k: boom()
    )
    assert distributed_flag_enabled("f", posture="fail_closed") is False


def test_distributed_flag_enabled_happy_path(monkeypatch):
    monkeypatch.setattr("services.platform.feature_flag.is_enabled", lambda *a, **k: True)
    assert distributed_flag_enabled("f") is True
