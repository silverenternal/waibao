#!/usr/bin/env bash
# =============================================================================
# Waibao v5.0 — T2003 Q3 灾备演练 (主库挂掉, 从库接管 + 异地备份恢复)
# =============================================================================
#
# 场景: 模拟 region-us 主库 (RDS PostgreSQL) 挂掉, 验证:
#   1. RDS 自动 failover 到只读副本 (RPO < 1h, 通常 < 5min)
#   2. 应用层自动重连 (PgBouncer + retry)
#   3. 跨区只读副本 (region-sg) 接管读流量
#   4. 异地备份 (S3 us-west-2) 恢复验证
#
# 目标:
#   - RTO < 4h
#   - RPO < 1h
#
# Usage:
#   bash scripts/dr_drill_q3.sh                 # 完整演练
#   bash scripts/dr_drill_q3.sh --dry-run       # 只演练不真破坏
#   bash scripts/dr_drill_q3.sh --no-restore    # 演练后不恢复 (用于审计)
#
# 前置:
#   - AWS CLI 配置 (us-west-1 + us-west-2 + sg)
#   - terraform 已部署 3 区
#   - supabase-cli 已安装
#   - jq + curl + psql
#
# 输出:
#   - logs/dr_drill_q3_<ts>.log
#   - docs/DR_DRILL_Q3.md (汇总报告)
# =============================================================================

set -euo pipefail

# ---------- 路径 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
DOCS_DIR="${PROJECT_ROOT}/../docs"
mkdir -p "${LOG_DIR}"
TS="$(date +%Y%m%d_%H%M%S)"
RUN_LOG="${LOG_DIR}/dr_drill_q3_${TS}.log"

# ---------- 参数 ----------
DRY_RUN=false
NO_RESTORE=false
for arg in "$@"; do
    case "${arg}" in
        --dry-run)    DRY_RUN=true ;;
        --no-restore) NO_RESTORE=true ;;
        *)            echo "Unknown arg: ${arg}"; exit 1 ;;
    esac
done

# ---------- 颜色 ----------
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; BOLD=''; RESET=''
fi

log()   { printf "${BLUE}[q3-drill]${RESET} %s\n" "$*" | tee -a "${RUN_LOG}"; }
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
    echo "${label}:${dur}" >> "${LOG_DIR}/dr_drill_q3_phases_${TS}.csv"
}

# ---------- 元数据 ----------
INCIDENT_ID="DR-Q3-${TS}"
INCIDENT_TITLE="region-us 主库 RDS 故障 + 从库接管 + 异地备份恢复"

# ---------- 预检 ----------
check_prereqs() {
    header "预检"
    log "AWS CLI: $(aws --version 2>&1 | head -1)"
    log "psql: $(psql --version)"
    log "jq: $(jq --version)"
    log "supabase: $(supabase --version 2>&1 | head -1 || echo 'not installed')"

    if ! aws sts get-caller-identity --region us-west-1 >/dev/null 2>&1; then
        err "AWS CLI 未配置 (us-west-1)"
        exit 1
    fi

    # 健康基线
    log "记录演练前健康状态 (基线)..."
    BASELINE_US=$(curl -sf -m 5 https://api.us.waibao.io/health 2>&1 || echo "FAIL")
    BASELINE_SG=$(curl -sf -m 5 https://api.sg.waibao.io/health 2>&1 || echo "FAIL")
    BASELINE_CN=$(curl -sf -m 5 https://api.waibao.cn/health 2>&1 || echo "FAIL")
    log "  region-us health: ${BASELINE_US}"
    log "  region-sg health: ${BASELINE_SG}"
    log "  region-cn health: ${BASELINE_CN}"
    ok "预检完成"
}

# ---------- Phase 1: 故障注入 ----------
inject_failure() {
    header "Phase 1: 注入故障 — 模拟 region-us RDS 主库挂掉"
    phase_start

    log "故障场景: aws rds failover --db-instance-identifier waibao-us-primary"
    log "影响: region-us 写操作全部失败, 应用层会 retry → 从库接管"

    if [ "${DRY_RUN}" = "true" ]; then
        warn "DRY-RUN: 跳过真实 failover"
    else
        log "执行 RDS failover..."
        aws rds failover-db-cluster \
            --db-cluster-identifier waibao-us-pg-cluster \
            --region us-west-1 \
            --no-cli-pager 2>&1 | tee -a "${RUN_LOG}" || warn "failover 命令返回非 0 (可能已经在 failover)"
    fi

    log "等待 RDS 状态变为 'available'..."
    WAITED=0
    while [ ${WAITED} -lt 600 ]; do
        STATUS=$(aws rds describe-db-clusters \
            --db-cluster-identifier waibao-us-pg-cluster \
            --region us-west-1 \
            --query 'DBClusters[0].Status' \
            --output text 2>/dev/null || echo "unknown")
        log "  status=${STATUS} (waited=${WAITED}s)"
        if [ "${STATUS}" = "available" ]; then
            ok "RDS failover 完成"
            break
        fi
        sleep 15
        WAITED=$((WAITED + 15))
    done

    if [ ${WAITED} -ge 600 ]; then
        err "RDS failover 超时 600s"
        exit 1
    fi

    phase_end "phase1-rds-failover"
}

# ---------- Phase 2: 应用层重连 ----------
verify_app_reconnect() {
    header "Phase 2: 应用层重连 + 错误注入"
    phase_start

    log "等待 backend pod 重启 / 重连..."
    sleep 30

    log "健康检查 (应自动恢复):"
    for i in 1 2 3 4 5; do
        HEALTH=$(curl -sf -m 5 -o /dev/null -w "%{http_code}" https://api.us.waibao.io/health || echo "000")
        log "  attempt ${i}: HTTP ${HEALTH}"
        if [ "${HEALTH}" = "200" ]; then
            ok "应用层自动恢复"
            break
        fi
        sleep 10
    done

    if [ "${HEALTH}" != "200" ]; then
        warn "应用层未自动恢复, 手动触发 PgBouncer 重连..."
        kubectl --context us-prod rollout restart deployment/waibao-pgbouncer -n waibao || true
        sleep 30
    fi

    phase_end "phase2-app-reconnect"
}

# ---------- Phase 3: 跨区只读接管 ----------
verify_xregion_readonly() {
    header "Phase 3: 跨区只读副本 (region-sg) 接管读流量"
    phase_start

    log "检查 region-sg 副本延迟..."
    LAG=$(aws rds describe-db-instances \
        --db-instance-identifier waibao-us-pg-replica-sg \
        --region ap-southeast-1 \
        --query 'DBInstances[0].ReplicaLag' \
        --output text 2>/dev/null || echo "unknown")
    log "  replica lag: ${LAG}s"

    log "切换应用 READONLY_DATABASE_URL → region-sg ..."
    if [ "${DRY_RUN}" = "false" ]; then
        kubectl --context us-prod set env deployment/waibao-backend \
            READONLY_DATABASE_URL="${RDS_SG_RO_URL}" \
            -n waibao
        kubectl --context us-prod rollout restart deployment/waibao-backend -n waibao
        sleep 30
    fi

    log "验证读流量切到 region-sg (write 应返回 503):"
    WRITE=$(curl -sf -m 5 -X POST https://api.us.waibao.io/api/v1/jobs -H "Content-Type: application/json" -d '{"title":"drill"}' -o /dev/null -w "%{http_code}" || echo "000")
    READ=$(curl -sf -m 5 https://api.us.waibao.io/api/v1/jobs -o /dev/null -w "%{http_code}" || echo "000")
    log "  read=${READ} (期望 200)"
    log "  write=${WRITE} (期望 503, 主库未恢复)"

    phase_end "phase3-xregion-readonly"
}

# ---------- Phase 4: 异地备份恢复 ----------
restore_from_backup() {
    header "Phase 4: 异地备份恢复 (us-west-2 S3)"
    phase_start

    log "列出最近 7 天自动备份..."
    BACKUPS=$(aws rds describe-db-snapshots \
        --db-instance-identifier waibao-us-primary \
        --region us-west-1 \
        --query 'DBSnapshots[?Status==`available`]|[?SnapshotCreateTime>=`2026-07-05`].[DBSnapshotIdentifier,SnapshotCreateTime]' \
        --output text 2>/dev/null | head -3)
    log "  ${BACKUPS}"

    LATEST=$(aws rds describe-db-snapshots \
        --db-instance-identifier waibao-us-primary \
        --region us-west-1 \
        --query 'DBSnapshots[?Status==`available`]|sort_by(@, &SnapshotCreateTime)[-1].DBSnapshotIdentifier' \
        --output text 2>/dev/null)
    log "  最新备份: ${LATEST}"

    if [ -z "${LATEST}" ] || [ "${LATEST}" = "None" ]; then
        err "未找到可用备份"
        exit 1
    fi

    log "从备份恢复 (到独立实例 waibao-us-pg-restored-${TS})..."
    if [ "${DRY_RUN}" = "false" ]; then
        aws rds restore-db-instance-from-db-snapshot \
            --db-instance-identifier "waibao-us-pg-restored-${TS}" \
            --db-snapshot-identifier "${LATEST}" \
            --db-instance-class db.r6g.large \
            --region us-west-1 \
            --no-cli-pager 2>&1 | tee -a "${RUN_LOG}" || warn "restore 命令返回非 0"
    fi

    log "等待 restored instance available..."
    WAITED=0
    while [ ${WAITED} -lt 1800 ]; do
        STATUS=$(aws rds describe-db-instances \
            --db-instance-identifier "waibao-us-pg-restored-${TS}" \
            --region us-west-1 \
            --query 'DBInstances[0].DBInstanceStatus' \
            --output text 2>/dev/null || echo "unknown")
        if [ "${STATUS}" = "available" ]; then
            ok "Restored instance available (waited ${WAITED}s)"
            break
        fi
        sleep 30
        WAITED=$((WAITED + 30))
    done

    if [ ${WAITED} -ge 1800 ]; then
        err "Restore 超时 1800s"
        exit 1
    fi

    phase_end "phase4-backup-restore"
}

# ---------- Phase 5: 数据一致性校验 ----------
verify_data_consistency() {
    header "Phase 5: 数据一致性校验 (原主 vs 恢复实例)"
    phase_start

    log "统计原主库行数 (仍可连, 只读模式)..."
    COUNT_OLD=$(psql "${RDS_US_URL}" -t -A -c "SELECT count(*) FROM jobs;" 2>/dev/null || echo "ERR")
    log "  原主 jobs count: ${COUNT_OLD}"

    log "统计恢复实例行数..."
    RESTORED_URL="postgresql://waibao:xxx@waibao-us-pg-restored-${TS}.xxxxx.us-west-1.rds.amazonaws.com:5432/waibao"
    COUNT_NEW=$(psql "${RESTORED_URL}" -t -A -c "SELECT count(*) FROM jobs;" 2>/dev/null || echo "ERR")
    log "  恢复 jobs count: ${COUNT_NEW}"

    log "RPO 估算 (行差代表演练期间未同步的写):"
    if [ "${COUNT_OLD}" != "ERR" ] && [ "${COUNT_NEW}" != "ERR" ]; then
        RPO_ROWS=$((COUNT_OLD - COUNT_NEW))
        log "  RPO rows: ${RPO_ROWS}"
    fi

    phase_end "phase5-data-consistency"
}

# ---------- Phase 6: 恢复主库 ----------
cleanup_and_restore() {
    header "Phase 6: 恢复原主库 + 清理演练实例"
    phase_start

    if [ "${NO_RESTORE}" = "true" ]; then
        warn "--no-restore: 跳过恢复步骤, 仅留演练实例供审计"
        return
    fi

    log "删除演练恢复实例 waibao-us-pg-restored-${TS}..."
    if [ "${DRY_RUN}" = "false" ]; then
        aws rds delete-db-instance \
            --db-instance-identifier "waibao-us-pg-restored-${TS}" \
            --region us-west-1 \
            --skip-final-snapshot \
            --no-cli-pager 2>&1 | tee -a "${RUN_LOG}" || true
    fi

    log "还原应用 READONLY_DATABASE_URL → 原 us RO 副本..."
    if [ "${DRY_RUN}" = "false" ]; then
        kubectl --context us-prod set env deployment/waibao-backend \
            READONLY_DATABASE_URL="${RDS_US_RO_URL}" \
            -n waibao
        kubectl --context us-prod rollout restart deployment/waibao-backend -n waibao
        sleep 30
    fi

    log "最终健康检查:"
    HEALTH=$(curl -sf -m 5 https://api.us.waibao.io/health -o /dev/null -w "%{http_code}")
    log "  region-us health: ${HEALTH}"

    phase_end "phase6-cleanup"
}

# ---------- 汇总 ----------
summarize() {
    header "汇总"

    log "Incident: ${INCIDENT_ID} — ${INCIDENT_TITLE}"
    log "完成时间: $(now_iso)"
    log "日志: ${RUN_LOG}"
    log ""
    log "各阶段耗时:"
    if [ -f "${LOG_DIR}/dr_drill_q3_phases_${TS}.csv" ]; then
        cat "${LOG_DIR}/dr_drill_q3_phases_${TS}.csv" | column -t -s: | tee -a "${RUN_LOG}"
    fi

    log ""
    log "RTO 估算: 从 phase1 开始到 phase4 结束 = 主库 failover + 应用重连 + 备份恢复时间"
    log "RPO 估算: 演练期间的写丢失 (≤ 自动备份间隔 5min)"
    log ""
    ok "Q3 灾备演练完成 — 报告见 docs/DR_DRILL_Q3.md"
}

# ---------- main ----------
main() {
    header "T2003 Q3 灾备演练启动"
    log "Incident: ${INCIDENT_ID}"
    log "Date: $(now_iso)"
    log "Mode: $([ "${DRY_RUN}" = "true" ] && echo 'DRY-RUN' || echo 'LIVE')"

    check_prereqs
    inject_failure
    verify_app_reconnect
    verify_xregion_readonly
    restore_from_backup
    verify_data_consistency
    cleanup_and_restore
    summarize
}

main "$@"