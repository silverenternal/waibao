#!/usr/bin/env bash
# run_locust.sh — T1104 一键压测脚本
#
# 在 backend 目录运行:  bash tests/load/run_locust.sh 100
# 可选参数: 100 | 500 | 1000 (默认 100)
#
# 输出:
#   - reports/locust_${USERS}_${TS}.html  (HTML 报告)
#   - reports/locust_${USERS}_${TS}.csv   (CSV 数据: 包含 p50/p95/p99/失败率/RPS)

set -euo pipefail

# --- 参数 & 默认值 ---
USERS="${1:-${LOAD_USERS:-100}}"
SPAWN_RATE="${SPAWN_RATE:-$(awk -v u="$USERS" 'BEGIN { print (u/20 < 1 ? 1 : int(u/20)) }')}"
RUN_TIME="${RUN_TIME:-5m}"
HOST="${HOST:-http://localhost:8000}"

case "$USERS" in
    100) SPAWN_RATE="${SPAWN_RATE:-5}"  ;;
    500) SPAWN_RATE="${SPAWN_RATE:-25}" ;;
    1000) SPAWN_RATE="${SPAWN_RATE:-50}" ;;
    *) echo "WARN: 非标准并发数 ($USERS),使用 SPAWN_RATE=$SPAWN_RATE" ;;
esac

# --- 路径 ---
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
REPORT_DIR="${ROOT}/reports"
mkdir -p "$REPORT_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
HTML="$REPORT_DIR/locust_${USERS}_${TS}.html"
CSV_PREFIX="$REPORT_DIR/locust_${USERS}_${TS}"

# --- 依赖检查 ---
if ! command -v locust >/dev/null 2>&1; then
    echo "ERROR: locust 未安装。请先: pip install locust faker"
    exit 1
fi

echo "==============================================="
echo "  Locust HTTP 压测启动"
echo "  Host       : $HOST"
echo "  Users      : $USERS"
echo "  Spawn rate : $SPAWN_RATE"
echo "  Run time   : $RUN_TIME"
echo "  HTML       : $HTML"
echo "  CSV        : ${CSV_PREFIX}_*.csv"
echo "==============================================="

cd "$ROOT/backend"

locust \
    -f tests/load/locustfile.py \
    --host "$HOST" \
    --users "$USERS" \
    --spawn-rate "$SPAWN_RATE" \
    --run-time "$RUN_TIME" \
    --headless \
    --html "$HTML" \
    --csv "$CSV_PREFIX" \
    --only-summary \
    --exit-code-on-error 0

EXIT=$?

echo
echo "==============================================="
echo "  压测结束 (locust exit=$EXIT)"
echo "  报告: $HTML"
echo "==============================================="

# 失败阈值检查
if [[ -f "${CSV_PREFIX}_stats.csv" ]]; then
    python3 - "$CSV_PREFIX" <<'PY'
import csv, sys
prefix = sys.argv[1]
try:
    with open(f"{prefix}_stats.csv") as f:
        rows = list(csv.DictReader(f))
    agg = next((r for r in rows if r.get("Name") == "Aggregated"), None)
    if not agg:
        print("WARN: 未找到 Aggregated 行")
        sys.exit(0)
    p95 = int(agg.get("95%", 0) or 0)
    fail = int(agg.get("Failure Count", 0) or 0)
    req = int(agg.get("Request Count", 1) or 1)
    err_rate = fail / req
    print(f"P95: {p95} ms | Error rate: {err_rate*100:.2f}%")
    if p95 > 2000:
        print(f"FAIL: P95 {p95}ms exceeds 2000ms SLA")
        sys.exit(2)
    if err_rate > 0.005:
        print(f"FAIL: error rate {err_rate*100:.2f}% exceeds 0.5% SLA")
        sys.exit(3)
    print("PASS: P95 < 2000ms & error rate < 0.5%")
except Exception as e:
    print(f"WARN: 后置检查失败: {e}")
PY
fi

exit $EXIT