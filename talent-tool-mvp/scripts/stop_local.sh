#!/usr/bin/env bash
# =============================================================================
# scripts/stop_local.sh — v11.0 / T6111 一键停止本地全离线环境
#
# 做两件事:
#   1. docker compose -f docker-compose.local.yml down (停 + 删容器)
#   2. 询问是否一并删除数据卷 (postgres / redis / ollama / paddleocr)
#      —— 默认保留卷,下次启动直接复用已下载模型与业务数据。
#
# 用法:
#   bash scripts/stop_local.sh             # 停服务, 保留数据卷 (默认)
#   bash scripts/stop_local.sh --purge     # 停服务 + 删除所有数据卷 (清空重来)
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="docker-compose.local.yml"

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m %s\033[0m\n' "$*" >&2; }

PURGE=0
if [ "${1:-}" = "--purge" ]; then
  PURGE=1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  warn "未找到 $COMPOSE_FILE,确认在仓库根目录执行。"
  exit 1
fi

log "停止本地 docker compose ($COMPOSE_FILE) ..."
if [ "$PURGE" -eq 1 ]; then
  # -v 删除命名卷: postgres_data / redis_data / ollama_data / paddleocr_models
  docker compose -f "$COMPOSE_FILE" down -v --remove-orphans
  echo ""
  log "已停止全部服务并删除数据卷 (模型 / 业务数据已清空)。"
  warn "下次启动将重新拉取 Ollama / PaddleOCR 模型。"
else
  docker compose -f "$COMPOSE_FILE" down --remove-orphans
  echo ""
  log "已停止全部服务 (数据卷保留)。"
  warn "重新启动: bash scripts/start_local.sh (模型与数据直接复用)"
fi
