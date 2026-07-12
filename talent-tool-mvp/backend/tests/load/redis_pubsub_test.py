"""Redis pub/sub 瓶颈识别 (T1105).

目标: 量化 Redis pub/sub 在 N 路 publisher × M 路 subscriber 下的:
  - publish 延迟
  - 端到端消息投递延迟
  - 吞吐量上限

环境变量:
  REDIS_URL       redis://localhost:6379/0
  CHANNELS        16
  SUBSCRIBERS     500
  MSGS_PER_PUB    1000
  MSG_SIZE_BYTES  256

Usage:
    pip install redis
    REDIS_URL=redis://localhost:6379/0 python -m tests.load.redis_pubsub_test

输出: 控制台表格 + reports/redis_pubsub_<ts>.json
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import statistics
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Optional

try:
    import redis.asyncio as redis_asyncio
except ImportError:  # pragma: no cover
    print("ERROR: 请先安装 redis>=4.2: pip install redis", file=sys.stderr)
    raise

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("recruittech.load.redis_pubsub")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CHANNELS = int(os.getenv("CHANNELS", "16"))
SUBSCRIBERS = int(os.getenv("SUBSCRIBERS", "500"))
MSGS_PER_PUB = int(os.getenv("MSGS_PER_PUB", "1000"))
MSG_SIZE_BYTES = int(os.getenv("MSG_SIZE_BYTES", "256"))
CHANNEL_PREFIX = os.getenv("CHANNEL_PREFIX", "loadtest:room:")
TEST_RUN_ID = f"run-{int(time.time())}"


# ---------------------------------------------------------------------------
# Subscriber
# ---------------------------------------------------------------------------

async def subscriber(client: "redis_asyncio.Redis", channel: str, sink: list) -> None:
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            data = msg.get("data")
            if isinstance(data, bytes):
                try:
                    data = data.decode("utf-8")
                except Exception:
                    data = str(data)
            try:
                payload = json.loads(data)
            except Exception:
                continue
            sent_ts = payload.get("ts")
            if isinstance(sent_ts, (int, float)):
                sink.append((time.perf_counter() * 1000) - sent_ts)
    finally:
        with suppress(Exception):
            await pubsub.unsubscribe(channel)
            await pubsub.close()


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------

async def publisher(
    client: "redis_asyncio.Redis",
    channel: str,
    n_msgs: int,
    size: int,
    latencies: list[float],
) -> int:
    payload_body = "x" * max(0, size - 80)  # 留出 JSON 包装空间
    sent = 0
    for i in range(n_msgs):
        t0 = time.perf_counter()
        msg = json.dumps(
            {"i": i, "ts": t0 * 1000, "channel": channel, "body": payload_body}
        )
        try:
            await client.publish(channel, msg)
            sent += 1
        except Exception as e:  # pragma: no cover
            logger.warning("publish error: %s", e)
            break
        latencies.append((time.perf_counter() - t0) * 1000)
        # 不加 sleep: 压满 publish
    return sent


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    try:
        qs = statistics.quantiles(values, n=100)
        return qs[max(0, min(99, pct - 1))]
    except Exception:
        return statistics.median(values)


async def run() -> dict:
    print(
        f"Redis pub/sub benchmark | url={REDIS_URL} channels={CHANNELS} "
        f"subscribers={SUBSCRIBERS} msgs/pub={MSGS_PER_PUB} size={MSG_SIZE_BYTES}B"
    )

    client = redis_asyncio.from_url(REDIS_URL, decode_responses=False)
    try:
        await client.ping()
    except Exception as e:
        print(f"ERROR: 无法连接 Redis {REDIS_URL}: {e}", file=sys.stderr)
        return {"error": str(e)}

    channels = [f"{CHANNEL_PREFIX}{TEST_RUN_ID}:{i}" for i in range(CHANNELS)]
    sinks: list[list[float]] = [[] for _ in channels]
    subs_per_channel = max(1, SUBSCRIBERS // CHANNELS)

    # 启动所有 subscriber
    sub_tasks = []
    for ch, sink in zip(channels, sinks):
        for _ in range(subs_per_channel):
            sub_tasks.append(asyncio.create_task(subscriber(client, ch, sink)))
    await asyncio.sleep(0.5)  # 等订阅生效

    # 启动所有 publisher (并发)
    pub_latencies: list[float] = []
    pub_tasks = [
        asyncio.create_task(publisher(client, ch, MSGS_PER_PUB, MSG_SIZE_BYTES, pub_latencies))
        for ch in channels
    ]

    t_start = time.perf_counter()
    sent_counts = await asyncio.gather(*pub_tasks)
    pub_elapsed = time.perf_counter() - t_start

    # 给消息 5s 投递时间
    await asyncio.sleep(5)

    # 取消所有 subscriber
    for t in sub_tasks:
        t.cancel()
    await asyncio.gather(*sub_tasks, return_exceptions=True)

    await client.aclose()

    total_sent = sum(sent_counts)
    total_received = sum(len(s) for s in sinks)

    sub_latencies: list[float] = []
    for s in sinks:
        sub_latencies.extend(s)

    result = {
        "run_id": TEST_RUN_ID,
        "config": {
            "channels": CHANNELS,
            "subscribers_per_channel": subs_per_channel,
            "msgs_per_pub": MSGS_PER_PUB,
            "msg_size_bytes": MSG_SIZE_BYTES,
        },
        "publish": {
            "total_sent": total_sent,
            "elapsed_sec": round(pub_elapsed, 3),
            "throughput_msgs_per_sec": round(total_sent / max(0.001, pub_elapsed), 2),
            "latency_ms": {
                "p50": round(percentile(pub_latencies, 50), 3),
                "p95": round(percentile(pub_latencies, 95), 3),
                "p99": round(percentile(pub_latencies, 99), 3),
                "max": round(max(pub_latencies, default=0.0), 3),
            },
        },
        "subscribe": {
            "total_received": total_received,
            "delivery_rate": round(total_received / max(1, total_sent), 4),
            "end_to_end_ms": {
                "p50": round(percentile(sub_latencies, 50), 3),
                "p95": round(percentile(sub_latencies, 95), 3),
                "p99": round(percentile(sub_latencies, 99), 3),
                "max": round(max(sub_latencies, default=0.0), 3),
            },
        },
        "verdict": {},
    }

    # 简单阈值
    issues = []
    if result["subscribe"]["delivery_rate"] < 0.99:
        issues.append(
            f"delivery_rate {result['subscribe']['delivery_rate']*100:.2f}% < 99%"
        )
    p95_e2e = result["subscribe"]["end_to_end_ms"]["p95"]
    if p95_e2e > 200:
        issues.append(f"end_to_end p95 {p95_e2e}ms > 200ms")
    result["verdict"]["issues"] = issues
    result["verdict"]["pass"] = not issues

    return result


def main() -> int:
    result = asyncio.run(run())
    print("\n=== Redis Pub/Sub Benchmark ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    out = Path(__file__).resolve().parent.parent.parent.parent / "reports"
    out.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = out / f"redis_pubsub_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Report written: {path}")

    return 0 if result.get("verdict", {}).get("pass", False) else 4


if __name__ == "__main__":
    sys.exit(main())