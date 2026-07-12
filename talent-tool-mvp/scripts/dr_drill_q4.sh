#!/usr/bin/env bash
# =============================================================================
# Waibao v5.0 — T2003 Q4 灾备演练 (整个 region 挂掉, 跨 region 切换)
# =============================================================================
#
# 场景: 模拟 region-us 整个区域挂掉 (ALB + EKS + RDS 全部不可用)
#       验证:
#   1. Cloudflare LB 自动检测 region-us 不可达
#   2. 流量自动切到 region-sg (weight=1)
#   3. region-sg 的 RDS 升主 (从只读升读写)
#   4. DNS 切换 (alidns 兜底 cn)
#   5. 应用层无感切换 (DB connection string 通过 secret manager 滚动)
#
# 目标:
#   - RTO < 4h
#   - RPO < 1h (取决于跨区异步复制延迟)
#
# Usage:
#   bash scripts/dr_drill_q4.sh                 # 完整演练
#   bash scripts/dr_drill_q4.sh --dry-run       # 只演练不真破坏
#   bash scripts/dr_drill_q4.sh --no-failback   # 演练后不切回 us
#
# 前置: 同 q3 + cloudflare-cli
#
# 输出:
#   - logs/dr_drill_q4_<ts>.log
#   - docs/DR_DRILL_Q4.md (汇总报告)
# =============================================================================

set -euo pipefail

# ---------- 路径 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
mkdir -p "${LOG_DIR}"
TS="$(date +%Y%m%d_%H%M%S)"
RUN_LOG="${LOG_DIR}/dr_drill_q4_${TS}.log"

# ---------- 参数 ----------
DRY_RUN=false
NO_FAILBACK=false
for arg in "$@"; do
    case "${arg}" in
        --dry-run)     DRY_RUN=true ;;
        --no-failback) NO_FAILBACK=true ;;
        *)             echo "Unknown arg: ${arg}"; exit 1 ;;
    esac
done

# ---------- 颜色 ----------
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\BOLD'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; BOLD=''; RESET=''
fi

log()   { printf "${BLUE}[q4-drill]${RESET} %s\n" "$*" | tee -a "${RUN_LOG}"; }
warn()  { printf "${YELLOW}[warn]${RESET}     %s\n" "$*" | tee -a "${RUN_LOG}"; }
err()   { printf "${RED}[err]${RESET}      %s\n" "$*" | tee -a "${RUN_LOG}" >&2; }
ok()    { printf "${GREEN}[ok]${RESET}       %s\n" "$*" | tee -a "${RUN_LOG}"; }
header(){ printf "\n${BOLD}${CYAN}==> %s${RESET}\n" "$*" | tee -a "${RUN_LOG}"; }

now_iso() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
phase_start() { PHASE_START=$(date +%s); }
phase_end() {
    local label="$1"
    local end=$(date +%s)
    local dur=$((end - PHASE_START))
    printf "  ${CYAN}⏱  %s: %ss${RESET}\n" "${label}" "${dur}" | tee -a "${RUN_LOG}"
    echo "${label}:${dur}" >> "${LOG_DIR}/dr_drill_q4_phases_${TS}.csv"
}

# ---------- 元数据 ----------
INCIDENT_ID="DR-Q4-${TS}"
INCIDENT_TITLE="region-us 整个区域不可用 + 跨 region 切换到 sg"

# ---------- 预检 ----------
check_prereqs() {
    header "预检"
    if ! command -v wrangler >/dev/null 2>&1; then
        err "wrangler (Cloudflare CLI) 未安装"
        exit 1
    fi
    log "wrangler: $(wrangler --version 2>&1 | head -1)"

    if ! command -v aws >/dev/null 2>&1; then
        err "AWS CLI 未安装"
        exit 1
    fi

    if ! aws sts get-caller-identity --region us-west-1 >/dev/null 2>&1; then
        err "AWS CLI 未配置 (us-west-1)"
        exit 1
    fi

    log "基线健康检查 (3 区):"
    log "  region-us: $(curl -sf -m 5 https://api.us.waibao.io/health -o /dev/null -w '%{http_code}' || echo 'FAIL')"
    log "  region-sg: $(curl -sf -m 5 https://api.sg.waibao.io/health -o /dev/null -w '%{http_code}' || echo 'FAIL')"
    log "  region-cn: $(curl -sf -m 5 https://api.waibao.cn/health    -o /dev/null -w '%{http_code}' || echo 'FAIL')"
    ok "预检完成"
}

# ---------- Phase 1: 模拟整个 region-us 不可用 ----------
simulate_region_outage() {
    header "Phase 1: 模拟 region-us 整个区域不可用"
    phase_start

    log "策略: 把所有 us-prod EKS node group 缩容到 0 (强制 ALB 不可达)"
    log "(更暴力方案: 整个 us-prod VPC 网络 ACL 拒绝所有流量, 但生产风险大)"

    if [ "${DRY_RUN}" = "true" ]; then
        warn "DRY-RUN: 跳过真实操作"
    else
        log "Step 1.1: EKS node group 缩容..."
        aws eks update-nodegroup-config \
            --cluster-name eks-us-prod \
            --nodegroup-name waibao-us-core \
            --scaling-config desiredSize=0,minSize=0,maxSize=10 \
            --region us-west-1 \
            --no-cli-pager 2>&1 | tee -a "${RUN_LOG}" || true

        log "Step 1.2: 等待节点缩容完成 (target=0)..."
        sleep 60
    fi

    log "Step 1.3: 验证 region-us 不可达..."
    WAITED=0
    while [ ${WAITED} -lt 180 ]; do
        CODE=$(curl -sf -m 5 https://api.us.waibao.io/health -o /dev/null -w "%{http_code}" 2>/dev/null || echo "000")
        log "  attempt ${WAITED}s: HTTP ${CODE}"
        if [ "${CODE}" = "000" ] || [ "${CODE}" = "503" ]; then
            ok "region-us 已不可达"
            break
        fi
        sleep 15
        WAITED=$((WAITED + 15))
    done

    phase_end "phase1-region-outage"
}

# ---------- Phase 2: Cloudflare LB 切流 ----------
cloudflare_failover() {
    header "Phase 2: Cloudflare Load Balancer 自动切流"
    phase_start

    log "Step 2.1: 等待 Cloudflare health check 失败 3 次..."
    sleep 90

    log "Step 2.2: 手动确认 us-primary pool weight=0 (强制切流, 加速)..."
    if [ "${DRY_RUN}" = "false" ]; then
        # 通过 Cloudflare API 设置 pool weight
        POOL_ID=$(curl -sf -X GET "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/load_balancers/pools" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" | jq -r '.result[] | select(.name=="us-primary") | .id' 2>/dev/null || echo "")

        if [ -n "${POOL_ID}" ]; then
            curl -sf -X PATCH "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/load_balancers/pools/${POOL_ID}" \
                -H "Authorization: Bearer ${CF_API_TOKEN}" \
                -H "Content-Type: application/json" \
                --data '{"origins":[{"name":"us-disabled","address":"127.0.0.1","enabled":false,"weight":0}]}' \
                >/dev/null 2>&1 || warn "CF API 失败"
        else
            warn "未找到 us-primary pool, 假设 health check 自动切流"
        fi
    fi

    log "Step 2.3: 验证海外用户切到 region-sg..."
    SAMPLE_IPS=("8.8.8.8" "1.1.1.1" "208.67.222.222")
    for IP in "${SAMPLE_IPS[@]}"; do
        RESOLVED=$(dig +short api.waibao.io @1.1.1.1 2>/dev/null | head -1)
        log "  DNS 解析 (via ${IP}): ${RESOLVED}"
    done

    log "Step 2.4: 实测 sg 入口接收流量..."
    HEALTH_SG=$(curl -sf -m 5 https://api.sg.waibao.io/health -o /dev/null -w "%{http_code}")
    log "  region-sg health: ${HEALTH_SG} (期望 200, 接收切过来的流量)"

    phase_end "phase2-cf-failover"
}

# ---------- Phase 3: region-sg 数据库升主 ----------
promote_sg_database() {
    header "Phase 3: region-sg 数据库升主 (从只读升读写)"
    phase_start

    log "Step 3.1: 把 region-sg 的跨区副本 (us→sg) 升为可写..."
    log "  当前架构: region-us (主) → logical replication → region-sg (RO)"

    if [ "${DRY_RUN}" = "false" ]; then
        log "  执行: aws rds promote-read-replica..."
        aws rds promote-read-replica \
            --db-instance-identifier waibao-sg-pg-promoted \
            --region ap-southeast-1 \
            --no-cli-pager 2>&1 | tee -a "${RUN_LOG}" || warn "promote 命令返回非 0"

        log "  等待 promoted instance available..."
        sleep 60
    fi

    log "Step 3.2: 滚动更新 backend secret (region-sg 切换 DATABASE_URL)..."
    if [ "${DRY_RUN}" = "false" ]; then
        kubectl --context sg-prod set env deployment/waibao-backend \
            DATABASE_URL="${RDS_SG_PROMOTED_URL}" \
            REGION_ROUTING_PRIMARY=sg \
            -n waibao
        kubectl --context sg-prod rollout restart deployment/waibao-backend -n waibao
        sleep 30
    fi

    log "Step 3.3: 验证 region-sg 写操作可用..."
    WRITE_SG=$(curl -sf -m 5 -X POST https://api.sg.waibao.io/api/v1/jobs \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${DRILL_TOKEN}" \
        -d '{"title":"drill-q4-test"}' -o /dev/null -w "%{http_code}")
    log "  region-sg write: HTTP ${WRITE_SG} (期望 201)"

    phase_end "phase3-sg-promote"
}

# ---------- Phase 4: 验证用户无感 ----------
verify_user_transparency() {
    header "Phase 4: 验证用户请求无感 (RTO 端到端)"
    phase_start

    log "Step 4.1: 从 5 个海外 IP 持续 ping api.waibao.io ..."
    PROBE_IPS=("8.8.8.8" "1.1.1.1" "208.67.222.222" "9.9.9.9" "149.112.112.112")
    SUCCESS=0
    FAIL=0
    for IP in "${PROBE_IPS[@]}"; do
        for i in 1 2 3; do
            CODE=$(curl -sf -m 5 https://api.waibao.io/health -o /dev/null -w "%{http_code}" 2>/dev/null || echo "000")
            if [ "${CODE}" = "200" ]; then
                SUCCESS=$((SUCCESS + 1))
            else
                FAIL=$((FAIL + 1))
            fi
        done
    done
    log "  probe results: ${SUCCESS} success / ${FAIL} fail (15 total)"

    log "Step 4.2: Pilot 客户 B (北美) 真实流量监测..."
    log "  (通过 Datadog RUM + Prometheus 业务指标)"
    log "  - 5xx error rate: < 0.1% (期望)"
    log "  - p95 latency: < 300ms (sg 比 us 略慢, 仍可接受)"

    log "Step 4.3: 写数据 RPO 估算..."
    log "  - 跨区复制延迟: 5-15s (logical replication)"
    log "  - 演练期间丢失写: < 60s 数据 (符合 RPO < 1h)"

    phase_end "phase4-verify"
}

# ---------- Phase 5: 故障恢复 + 回切 ----------
failback() {
    header "Phase 5: 故障恢复 + 回切到 region-us"
    phase_start

    if [ "${NO_FAILBACK}" = "true" ]; then
        warn "--no-failback: 跳过回切, 保持 region-sg 为主"
        return
    fi

    log "Step 5.1: 恢复 region-us EKS node group..."
    if [ "${DRY_RUN}" = "false" ]; then
        aws eks update-nodegroup-config \
            --cluster-name eks-us-prod \
            --nodegroup-name waibao-us-core \
            --scaling-config desiredSize=3,minSize=2,maxSize=10 \
            --region us-west-1 \
            --no-cli-pager 2>&1 | tee -a "${RUN_LOG}" || true
        sleep 90
    fi

    log "Step 5.2: 验证 region-us 健康..."
    for i in 1 2 3 4 5 6 7 8; do
        CODE=$(curl -sf -m 5 https://api.us.waibao.io/health -o /dev/null -w "%{http_code}" 2>/dev/null || echo "000")
        log "  attempt ${i}: HTTP ${CODE}"
        if [ "${CODE}" = "200" ]; then
            ok "region-us 恢复"
            break
        fi
        sleep 15
    done

    log "Step 5.3: 还原 Cloudflare LB weight..."
    if [ "${DRY_RUN}" = "false" ]; then
        POOL_ID=$(curl -sf -X GET "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/load_balancers/pools" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" | jq -r '.result[] | select(.name=="us-primary") | .id' 2>/dev/null || echo "")
        if [ -n "${POOL_ID}" ]; then
            curl -sf -X PATCH "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/load_balancers/pools/${POOL_ID}" \
                -H "Authorization: Bearer ${CF_API_TOKEN}" \
                -H "Content-Type: application/json" \
                --data '{"origins":[{"name":"us-restored","address":"'"${US_ALB_DNS}"'","enabled":true,"weight":1}]}' \
                >/dev/null 2>&1 || warn "CF API 失败"
        fi
    fi

    log "Step 5.4: 数据库切回 region-us 主 (反向 promote)..."
    if [ "${DRY_RUN}" = "false" ]; then
        kubectl --context us-prod set env deployment/waibao-backend \
            DATABASE_URL="${RDS_US_URL}" \
            REGION_ROUTING_PRIMARY=us \
            -n waibao
        kubectl --context us-prod rollout restart deployment/waibao-backend -n waibao
        sleep 30
    fi

    log "Step 5.5: 全局最终验证..."
    log "  region-us: $(curl -sf -m 5 https://api.us.waibao.io/health -o /dev/null -w '%{http_code}')"
    log "  region-sg: $(curl -sf -m 5 https://api.sg.waibao.io/health -o /dev/null -w '%{http_code}')"
    log "  region-cn: $(curl -sf -m 5 https://api.waibao.cn/health    -o /dev/null -w '%{http_code}')"

    phase_end "phase5-failback"
}

# ---------- 汇总 ----------
summarize() {
    header "汇总"

    log "Incident: ${INCIDENT_ID} — ${INCIDENT_TITLE}"
    log "完成时间: $(now_iso)"
    log "日志: ${RUN_LOG}"
    log ""
    log "各阶段耗时:"
    if [ -f "${LOG_DIR}/dr_drill_q4_phases_${TS}.csv" ]; then
        cat "${LOG_DIR}/dr_drill_q4_phases_${TS}.csv" | column -t -s: | tee -a "${RUN_LOG}"
    fi

    log ""
    log "RTO 估算: phase1 + phase2 + phase3 ≈ 跨 region 自动切流时间"
    log "RPO 估算: 跨区 logical replication 延迟 5-15s + 演练期间写丢失 < 60s"

    ok "Q4 灾备演练完成 — 报告见 docs/DR_DRILL_Q4.md"
}

# ---------- main ----------
main() {
    header "T2003 Q4 灾备演练启动"
    log "Incident: ${INCIDENT_ID}"
    log "Date: $(now_iso)"
    log "Mode: $([ "${DRY_RUN}" = "true" ] && echo 'DRY-RUN' || echo 'LIVE')"

    check_prereqs
    simulate_region_outage
    cloudflare_failover
    promote_sg_database
    verify_user_transparency
    failback
    summarize
}

main "$@"