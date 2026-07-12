#!/usr/bin/env bash
# =============================================================================
# Waibao v5.0 — 真实业务压测一键脚本 (T1703)
# =============================================================================
#
# 三档压测: HTTP 1000 并发 / WebSocket 5000 并发 / 全链路
#
# Usage:
#   bash scripts/run_real_loadtest.sh                # 默认: http 1000 + ws 5000
#   bash scripts/run_real_loadtest.sh http           # 仅 HTTP 1000
#   bash scripts/run_real_loadtest.sh ws             # 仅 WebSocket 5000
#   bash scripts/run_real_loadtest.sh smoke          # 100 并发烟囱
#   bash scripts/run_real_loadtest.sh full           # 100 + 500 + 1000 三档
#   bash scripts/run_real_loadtest.sh ramp 100 1000  # 从 100 阶梯到 1000
#
# Env:
#   HOST              压测目标 (default: http://localhost:8000)
#   WS_HOST           WS 目标 host (default: localhost:8000)
#   LOAD_USERS        并发数 (default: 1000)
#   SPAWN_RATE        爬升速率 (default: 50)
#   RUN_TIME          持续时间 (default: 10m)
#   WS_CONCURRENCY    WS 并发数 (default: 5000)
#   WS_DURATION_SEC   WS 持续秒数 (default: 60)
#
# SLA 检查: P95 < 2000ms / 错误率 < 0.5% / WS 消息延迟 P95 < 200ms
# =============================================================================

set -euo pipefail

# ---------- 路径 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
REPORT_DIR="${PROJECT_ROOT}/reports"
mkdir -p "${REPORT_DIR}"
TS="$(date +%Y%m%d_%H%M%S)"

# ---------- 颜色 ----------
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; BOLD=''; RESET=''
fi

log()   { printf "${BLUE}[loadtest]${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}[warn]${RESET}    %s\n" "$*"; }
err()   { printf "${RED}[err]${RESET}     %s\n" "$*" >&2; }
ok()    { printf "${GREEN}[ok]${RESET}      %s\n" "$*"; }
header(){ printf "\n${BOLD}${CYAN}==> %s${RESET}\n" "$*"; }

# ---------- 默认值 ----------
MODE="${1:-default}"
HOST="${HOST:-http://localhost:8000}"
WS_HOST="${WS_HOST:-localhost:8000}"
LOAD_USERS="${LOAD_USERS:-1000}"
SPAWN_RATE="${SPAWN_RATE:-50}"
RUN_TIME="${RUN_TIME:-10m}"
WS_CONCURRENCY="${WS_CONCURRENCY:-5000}"
WS_DURATION_SEC="${WS_DURATION_SEC:-60}"

# ---------- 预检 ----------
check_prereqs() {
    if ! command -v locust >/dev/null 2>&1; then
        err "locust 未安装。请先: pip install locust locust-plugins faker websockets"
        exit 1
    fi
    if [ ! -d "${BACKEND_DIR}/tests/load" ]; then
        err "tests/load 目录不存在: ${BACKEND_DIR}/tests/load"
        exit 1
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        err "python3 未安装"
        exit 1
    fi
}

health_check() {
    log "健康检查 ${HOST}/health ..."
    if curl -sf -m 5 "${HOST}/health" >/dev/null 2>&1; then
        ok "服务健康"
        return 0
    else
        warn "服务健康检查失败 (可能未启动或端点不可用) — 继续执行"
        return 0
    fi
}

# ---------- HTTP 压测 ----------
run_http() {
    local users="$1"
    local spawn="$2"
    local runtime="$3"
    local label="${4:-http_${users}}"

    header "[${label}] HTTP 压测: users=${users} spawn=${spawn} time=${runtime}"
    local html="${REPORT_DIR}/locust_${label}_${TS}.html"
    local csv="${REPORT_DIR}/locust_${label}_${TS}"
    local summary="${REPORT_DIR}/locust_${label}_${TS}_summary.txt"

    cd "${BACKEND_DIR}"
    LOAD_REPORT_OUT="${summary}" \
    LOAD_USERS="${users}" SPAWN_RATE="${spawn}" RUN_TIME="${runtime}" \
    bash tests/load/run_locust.sh "${users}" || true

    # 校验 SLA
    if [ -f "${csv}_stats.csv" ]; then
        python3 - "${csv}" "${summary}" <<'PY'
import csv, json, sys, pathlib
prefix = sys.argv[1]
summary_path = pathlib.Path(sys.argv[2])
with open(f"{prefix}_stats.csv") as f:
    rows = list(csv.DictReader(f))
agg = next((r for r in rows if r.get("Name") == "Aggregated"), None)
if not agg:
    print("WARN: 未找到 Aggregated 行")
    sys.exit(0)
p95 = int(agg.get("95%", 0) or 0)
fail = int(agg.get("Failure Count", 0) or 0)
req = int(agg.get("Request Count", 1) or 1)
err = fail / req
result = {
    "p95_ms": p95,
    "error_rate": err,
    "requests": req,
    "failures": fail,
    "pass_p95": p95 < 2000,
    "pass_err": err < 0.005,
}
summary_path.write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
sys.exit(0 if (result["pass_p95"] and result["pass_err"]) else 4)
PY
        local rc=$?
        if [ $rc -eq 0 ]; then
            ok "[${label}] HTTP 压测 PASS"
        else
            err "[${label}] HTTP 压测 FAIL (exit=$rc)"
        fi
    fi
}

# ---------- WebSocket 压测 ----------
run_ws() {
    local concurrency="$1"
    local duration="$2"
    local label="${3:-ws_${concurrency}}"

    header "[${label}] WebSocket 压测: concurrency=${concurrency} duration=${duration}s"
    local html="${REPORT_DIR}/ws_${label}_${TS}.html"
    local csv="${REPORT_DIR}/ws_${label}_${TS}"
    local log="${REPORT_DIR}/ws_${label}_${TS}.log"

    cd "${BACKEND_DIR}"

    # 优先用 Locust (50-1000 稳)
    if [ "${concurrency}" -le 1000 ]; then
        locust -f tests/load/ws_locustfile.py \
            --host "${HOST}" \
            --users "${concurrency}" \
            --spawn-rate 50 \
            --run-time "${duration}s" \
            --headless \
            --html "${html}" \
            --csv "${csv}" \
            --exit-code-on-error 0 2>&1 | tee "${log}" || true
    else
        # 1000+ 用 asyncio
        CONCURRENCY="${concurrency}" DURATION_SEC="${duration}" \
        PUBLISH_INTERVAL_MS="${PUBLISH_INTERVAL_MS:-200}" \
        WS_URL_TEMPLATE="ws://${WS_HOST}/api/realtime/ws/rooms/{room_id}?token=mock-jwt-ws" \
        python3 -m tests.load.ws_concurrent 2>&1 | tee "${log}" || true
    fi

    ok "[${label}] WebSocket 压测完成"
}

# ---------- 主流程 ----------
main() {
    check_prereqs
    health_check

    case "${MODE}" in
        http)
            run_http "${LOAD_USERS}" "${SPAWN_RATE}" "${RUN_TIME}" "http_${LOAD_USERS}"
            ;;
        ws)
            run_ws "${WS_CONCURRENCY}" "${WS_DURATION_SEC}" "ws_${WS_CONCURRENCY}"
            ;;
        smoke)
            run_http 100 10 2m "smoke_100"
            ;;
        full)
            header "全链路: 100 → 500 → 1000 三档"
            run_http 100  10  2m  "ramp_100"
            run_http 500  25  5m  "ramp_500"
            run_http 1000 50  10m "ramp_1000"
            run_ws  5000 60  "ws_5000"
            ;;
        ramp)
            local from="${2:-100}"
            local to="${3:-1000}"
            header "阶梯压测: ${from} → ${to}"
            local cur="${from}"
            while [ "${cur}" -le "${to}" ]; do
                run_http "${cur}" $((cur / 20 < 1 ? 1 : cur / 20)) 3m "ramp_${cur}"
                cur=$((cur * 2))
                if [ "${cur}" -gt "${to}" ] && [ "${cur}" -ne "${to}" ]; then
                    run_http "${to}" 50 5m "ramp_${to}"
                    break
                fi
            done
            ;;
        default|"")
            header "默认: HTTP 1000 + WS 5000"
            run_http "${LOAD_USERS}" "${SPAWN_RATE}" "${RUN_TIME}" "http_${LOAD_USERS}"
            run_ws  "${WS_CONCURRENCY}" "${WS_DURATION_SEC}" "ws_${WS_CONCURRENCY}"
            ;;
        *)
            err "未知模式: ${MODE}"
            echo "用法: $0 [http|ws|smoke|full|ramp <from> <to>|default]"
            exit 1
            ;;
    esac

    echo ""
    header "压测完成"
    echo "  报告目录: ${REPORT_DIR}/"
    echo "  下一步:   编辑 docs/PERFORMANCE_v5.md 第 3 节回填实测数据"
    echo ""
}

main "$@"
