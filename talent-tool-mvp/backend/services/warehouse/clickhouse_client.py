"""T2801 — ClickHouse client (单例 + 同步 API)."""
from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

logger = logging.getLogger("waibao.warehouse.clickhouse")


@dataclass
class ClickHouseConfig:
    host: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("CLICKHOUSE_PORT", "9000")))
    database: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_DB", "warehouse"))
    user: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_USER", "clickhouse"))
    password: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_PASSWORD", "clickhouse"))
    secure: bool = field(default_factory=lambda: os.getenv("CLICKHOUSE_SECURE", "0") == "1")
    connect_timeout: float = 5.0
    send_receive_timeout: float = 30.0
    # 性能调优
    settings: dict[str, Any] = field(default_factory=lambda: {
        "max_execution_time": 30,
        "max_memory_usage": 10_000_000_000,
        "use_uncompressed_cache": 1,
        "readonly": 1,  # 默认只读, ETL 用另一个 user
    })

    def to_driver_kwargs(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.password,
            "secure": self.secure,
            "connect_timeout": self.connect_timeout,
            "send_receive_timeout": self.send_receive_timeout,
            "settings": dict(self.settings),
        }


class ClickHouseClient:
    """clickhouse-driver 薄封装. 复用 connection (HTTP-like performance)."""

    def __init__(self, config: Optional[ClickHouseConfig] = None) -> None:
        self.config = config or ClickHouseConfig()
        self._client: Any = None
        self._lock = threading.Lock()
        self._closed = False

    # -------------------------------------------------------- lifecycle
    def connect(self) -> None:
        with self._lock:
            if self._client is not None:
                return
            try:
                from clickhouse_driver import Client  # type: ignore
            except ImportError as e:
                raise RuntimeError(
                    "clickhouse-driver not installed. Run: pip install clickhouse-driver"
                ) from e
            self._client = Client(**self.config.to_driver_kwargs())
            # 立刻 ping 一次, 启动就 fail-fast
            self._client.execute("SELECT 1")
            logger.info("Connected to ClickHouse at %s:%s/%s",
                        self.config.host, self.config.port, self.config.database)

    def close(self) -> None:
        with self._lock:
            if self._client is not None and not self._closed:
                try:
                    self._client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                self._closed = True

    @contextmanager
    def _conn(self) -> Iterator[Any]:
        if self._client is None:
            self.connect()
        assert self._client is not None
        yield self._client

    # -------------------------------------------------------- core
    def execute(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[tuple]:
        with self._conn() as c:
            return c.execute(query, params or {})

    def query(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(query, params or {}, with_column_types=True)
            if not rows:
                return []
            data, types = rows
            cols = [t[0] for t in types]
            return [dict(zip(cols, r)) for r in data]

    def query_one(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        rows = self.query(query, params)
        return rows[0] if rows else None

    # -------------------------------------------------------- helpers
    def ping(self) -> bool:
        try:
            r = self.execute("SELECT 1")
            return bool(r and r[0][0] == 1)
        except Exception:  # noqa: BLE001
            return False

    def table_exists(self, name: str, database: Optional[str] = None) -> bool:
        db = database or self.config.database
        r = self.execute(
            "SELECT count() FROM system.tables WHERE database=:db AND name=:n",
            {"db": db, "n": name},
        )
        return bool(r and r[0][0] > 0)

    def row_count(self, table: str) -> int:
        r = self.execute(f"SELECT count() FROM {table}")
        return int(r[0][0]) if r else 0

    def health(self) -> dict[str, Any]:
        try:
            ver = self.query_one("SELECT version() AS v") or {"v": "unknown"}
            return {
                "ok": True,
                "version": ver.get("v"),
                "host": self.config.host,
                "database": self.config.database,
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------- singleton
_client: Optional[ClickHouseClient] = None
_client_lock = threading.Lock()


def get_clickhouse_client() -> ClickHouseClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = ClickHouseClient()
        return _client


def reset_clickhouse_client() -> None:
    global _client
    with _client_lock:
        if _client is not None:
            _client.close()
        _client = None
