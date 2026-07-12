"""WebSocket 高并发压测 (T1105) — 用 asyncio + websockets.

启动 5000 个并发连接, 测量:
  - 连接成功率
  - 连接建立延迟 (connect latency)
  - 端到端消息延迟 (publish → ack)

默认从环境变量读取:
  WS_URL=ws://localhost:8000/api/realtime/ws/rooms/{room_id}?token=...
  CONCURRENCY=5000
  DURATION_SEC=60
  PUBLISH_INTERVAL_MS=200

Usage:
    pip install websockets
    python -m tests.load.ws_concurrent

    CONCURRENCY=5000 DURATION_SEC=60 python -m tests.load.ws_concurrent

退出码: 0=PASS, 2=连接成功率 < 99%, 3=p95 延迟 > 200ms
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import statistics
import sys
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import websockets
    from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException
except ImportError as e:  # pragma: no cover
    print(
        "ERROR: websockets 未安装. 请先: pip install websockets",
        file=sys.stderr,
    )
    raise

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from scenarios import fake_room_id, fake_short_code  # noqa: E402

logger = logging.getLogger("recruittech.load.ws_async")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

DEFAULT_WS_TEMPLATE = (
    "ws://localhost:8000/api/realtime/ws/rooms/{room_id}?token={token}"
)
WS_URL_TEMPLATE = os.getenv("WS_URL_TEMPLATE", DEFAULT_WS_TEMPLATE)
TOKEN = os.getenv("WS_TOKEN", "mock-jwt-ws")
CONCURRENCY = int(os.getenv("CONCURRENCY", "5000"))
DURATION_SEC = int(os.getenv("DURATION_SEC", "60"))
PUBLISH_INTERVAL_MS = int(os.getenv("PUBLISH_INTERVAL_MS", "200"))
CONNECT_TIMEOUT_SEC = float(os.getenv("CONNECT_TIMEOUT_SEC", "10"))
TARGET_P95_MS = int(os.getenv("TARGET_P95_MS", "200"))
TARGET_SUCCESS_RATE = float(os.getenv("TARGET_SUCCESS_RATE", "0.99"))


# ---------------------------------------------------------------------------
# 数据收集
# ---------------------------------------------------------------------------

@dataclass
class AggregatedStats:
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    total_attempted: int = 0
    total_connected: int = 0
    total_publish_sent: int = 0
    total_ack_received: int = 0
    connect_latencies_ms: list[float] = field(default_factory=list)
    ack_latencies_ms: list[float] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        p = self._percentile
        return {
            "duration_sec": round(self.finished_at - self.started_at, 2),
            "concurrency_attempted": self.total_attempted,
            "connected": self.total_connected,
            "connect_success_rate": round(self.total_connected / max(1, self.total_attempted), 4),
            "publish_sent": self.total_publish_sent,
            "ack_received": self.total_ack_received,
            "ack_delivery_rate": round(self.total_ack_received / max(1, self.total_publish_sent), 4),
            "connect_latency_ms": {
                "p50": round(p(self.connect_latencies_ms, 50), 2),
                "p95": round(p(self.connect_latencies_ms, 95), 2),
                "p99": round(p(self.connect_latencies_ms, 99), 2),
                "max": round(max(self.connect_latencies_ms, default=0.0), 2),
            },
            "ack_latency_ms": {
                "p50": round(p(self.ack_latencies_ms, 50), 2),
                "p95": round(p(self.ack_latencies_ms, 95), 2),
                "p99": round(p(self.ack_latencies_ms, 99), 2),
                "max": round(max(self.ack_latencies_ms, default=0.0), 2),
            },
            "failures_sample": self.failures[:10],
        }

    @staticmethod
    def _percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        # Use statistics.quantiles for accurate percentile
        try:
            qs = statistics.quantiles(values, n=100)
            idx = max(0, min(99, pct - 1))
            return qs[idx]
        except Exception:
            return statistics.median(values)


STATS = AggregatedStats()


# ---------------------------------------------------------------------------
# 单个客户端 worker
# ---------------------------------------------------------------------------

async def client_worker(
    worker_id: int,
    stop_at: float,
    sem: asyncio.Semaphore,
) -> None:
    """一个客户端: 连接 → 订阅 → 周期 publish → 等 ack."""
    room_id = fake_room_id()
    url = WS_URL_TEMPLATE.format(room_id=room_id, token=TOKEN)

    STATS.total_attempted += 1

    async with sem:  # limit concurrency for connect phase
        t0 = time.perf_counter()
        try:
            ws = await websockets.connect(
                url,
                open_timeout=CONNECT_TIMEOUT_SEC,
                max_queue=64,
                ping_interval=20,
                ping_timeout=20,
            )
        except (InvalidStatus, ConnectionClosed, WebSocketException, OSError) as e:
            STATS.failures.append(f"connect failed #{worker_id}: {type(e).__name__}: {e}")
            return
        except Exception as e:  # pragma: no cover
            STATS.failures.append(f"connect crash #{worker_id}: {type(e).__name__}: {e}")
            return

    connect_ms = (time.perf_counter() - t0) * 1000
    STATS.connect_latencies_ms.append(connect_ms)
    STATS.total_connected += 1

    try:
        await ws.send(
            json.dumps({"type": "subscribe", "token": TOKEN, "user_id": f"w{worker_id}"})
        )

        async def reader() -> None:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                if data.get("type") == "ack":
                    sent_ts = data.get("sent_ts")
                    if isinstance(sent_ts, (int, float)):
                        STATS.ack_latencies_ms.append(
                            (time.perf_counter() * 1000) - sent_ts
                        )
                    STATS.total_ack_received += 1

        reader_task = asyncio.create_task(reader())

        while time.perf_counter() < stop_at:
            delivery_id = fake_short_code(12)
            sent_ts_ms = int(time.perf_counter() * 1000)
            payload = {
                "type": "publish",
                "delivery_id": delivery_id,
                "sent_ts": sent_ts_ms,
                "payload": {"text": f"hi-{random.randint(1, 99999)}", "ts": sent_ts_ms},
            }
            try:
                await ws.send(json.dumps(payload))
                STATS.total_publish_sent += 1
            except (ConnectionClosed, WebSocketException, OSError) as e:
                STATS.failures.append(f"publish #{worker_id}: {type(e).__name__}: {e}")
                break

            # 主动测一次 RTT — 等 ack 或超时
            try:
                ack_raw = await asyncio.wait_for(
                    ws.recv(), timeout=CONNECT_TIMEOUT_SEC
                )
                try:
                    data = json.loads(ack_raw)
                    if data.get("type") == "ack":
                        sent_ts = data.get("sent_ts")
                        if isinstance(sent_ts, (int, float)):
                            STATS.ack_latencies_ms.append(
                                (time.perf_counter() * 1000) - sent_ts
                            )
                        STATS.total_ack_received += 1
                except Exception:
                    pass
            except asyncio.TimeoutError:
                pass  # not fatal, server may be busy

            await asyncio.sleep(PUBLISH_INTERVAL_MS / 1000.0)

        reader_task.cancel()
        with suppress(asyncio.CancelledError):
            await reader_task

    finally:
        with suppress(Exception):
            await ws.close()


# ---------------------------------------------------------------------------
# 主流程: 分批连接, 避免 fd 风暴
# ---------------------------------------------------------------------------

async def run_load_test() -> AggregatedStats:
    print(
        f"Starting WebSocket load test | concurrency={CONCURRENCY} "
        f"duration={DURATION_SEC}s interval={PUBLISH_INTERVAL_MS}ms"
    )

    # 连接阶段: 限制瞬时并发握手 (避免 fd 风暴), 但 worker 数 = CONCURRENCY
    connect_sem = asyncio.Semaphore(min(200, CONCURRENCY))
    stop_at = time.perf_counter() + DURATION_SEC

    tasks = [
        asyncio.create_task(client_worker(i, stop_at, connect_sem))
        for i in range(CONCURRENCY)
    ]
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        STATS.finished_at = time.time()
        for t in tasks:
            if not t.done():
                t.cancel()

    return STATS


def main() -> int:
    stats = asyncio.run(run_load_test())
    summary = stats.summary()

    print("\n=== WebSocket Load Test Result ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # 落盘
    out = Path(__file__).resolve().parent.parent.parent.parent / "reports"
    out.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    report_path = out / f"ws_concurrent_{CONCURRENCY}_{ts}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"Report written: {report_path}")

    # SLA 检查
    code = 0
    if summary["connect_success_rate"] < TARGET_SUCCESS_RATE:
        print(
            f"FAIL: connect success rate {summary['connect_success_rate']*100:.2f}% "
            f"< target {TARGET_SUCCESS_RATE*100:.2f}%"
        )
        code = 2
    p95 = summary["ack_latency_ms"]["p95"]
    if p95 > TARGET_P95_MS:
        print(f"FAIL: ack p95 {p95}ms > target {TARGET_P95_MS}ms")
        code = 3 if code == 0 else code
    if code == 0:
        print(
            f"PASS: connect_rate={summary['connect_success_rate']*100:.2f}% "
            f"p95_ack={p95}ms"
        )
    return code


if __name__ == "__main__":
    sys.exit(main())