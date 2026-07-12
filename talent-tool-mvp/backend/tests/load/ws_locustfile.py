"""WebSocket Locust 压测 (T1105).

使用 Locust 的 WebSocket 支持 + 自定义 stats, 模拟:
  - 建立 /ws/rooms/{room_id} 连接
  - 周期发 publish
  - 测量端到端延迟 (ack round-trip)

目标: 500 并发 WebSocket 连接 / P95 消息延迟 < 200ms / 错误率 < 0.5%

Usage:
    locust -f ws_locustfile.py --host http://localhost:8000 \\
        -u 500 -r 50 --run-time 5m --headless
"""
from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
from pathlib import Path

from locust import between, events, task
from locust.contrib.websocket import WebSocketUser  # requires locust-plugins

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from scenarios import fake_room_id, fake_room_message, fake_short_code  # noqa: E402

logger = logging.getLogger("recruittech.load.ws")

MOCK_JWT = os.getenv("LOAD_JWT_WS", "mock-jwt-ws")


class WebSocketRoomUser(WebSocketUser):
    """单个用户加入一个协同房间, 持续收发消息."""

    wait_time = between(0.05, 0.3)
    abstract = False
    # Locust 启动时只跑这个类;通过 -u 控制总连接数

    def on_start(self) -> None:
        self.room_id = fake_room_id()
        self._send_count = 0
        self._recv_count = 0
        self._last_send_ts: float | None = None

        # 建立连接 — Locust 会自动算作 "connect" 事件
        ws_url = f"/api/realtime/ws/rooms/{self.room_id}?token={MOCK_JWT}"
        self.connect(ws_url)

        # 订阅消息
        self.send(
            json.dumps(
                {"type": "subscribe", "token": MOCK_JWT, "user_id": fake_short_code(8)}
            )
        )

    @task
    def publish_message(self) -> None:
        """发 publish, 测量 ack 延迟."""
        if not self.connected:
            return
        delivery_id = fake_short_code(12)
        msg = {
            "type": "publish",
            "delivery_id": delivery_id,
            "payload": {
                "text": f"hello-{random.randint(1, 99999)}",
                "ts": int(time.time() * 1000),
            },
        }
        self._last_send_ts = time.perf_counter()
        self._send_count += 1
        self.send(json.dumps(msg))

    def on_message(self, message) -> None:  # noqa: ANN001
        """收到消息 — 计算 ack 延迟."""
        self._recv_count += 1
        try:
            data = json.loads(message)
        except Exception:
            return
        if data.get("type") == "ack" and self._last_send_ts is not None:
            latency_ms = (time.perf_counter() - self._last_send_ts) * 1000
            self.environment.events.request.fire(
                request_type="WSS",
                name="ack_latency",
                response_time=latency_ms,
                response_length=len(message),
                exception=None,
                context={},
            )


# ---------------------------------------------------------------------------
# 启动 / 停止钩子
# ---------------------------------------------------------------------------

@events.test_start.add_listener
def _on_test_start(environment, **kwargs) -> None:  # pragma: no cover
    logger.info("WebSocket load test starting | host=%s", environment.host)


@events.test_stop.add_listener
def _on_test_stop(environment, **kwargs) -> None:  # pragma: no cover
    stats = environment.stats
    total = stats.total
    print("\n=== WS Load Test Summary ===")
    print(f"  Total frames : {total.num_requests}")
    print(f"  Failures     : {total.num_failures}")
    print(f"  p50          : {total.median_response_time} ms")
    print(f"  p95          : {total.get_response_time_percentile(0.95)} ms")
    print(f"  p99          : {total.get_response_time_percentile(0.99)} ms")
    print(f"  RPS          : {total.total_rps:.2f}")