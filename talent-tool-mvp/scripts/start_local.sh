#!/usr/bin/env bash
# =============================================================================
# scripts/start_local.sh — v11.0 / T6111 一键启动本地全离线环境
#
# 6 服务全量起: backend + frontend + postgres + redis + ollama + paddleocr
# 做五件事:
#   1. 检查 Docker / docker compose 是否就绪
#   2. docker compose -f docker-compose.local.yml up -d (单文件自包含)
#   3. 等 postgres / redis / ollama healthy
#   4. 拉取默认 LLM 模型 qwen2.5:7b-instruct (调用 setup_ollama.sh)
#   5. 预下载 PaddleOCR 中英文模型 (调用 setup_paddleocr.sh)
#   6. 健康探测 backend / frontend, 打印访问 URL
#
# 数据全程不出甲方环境 —— LLM_PROVIDER=ollama + OCR_PROVIDER=paddle,
# 无任何外部 LLM / OCR API。
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="docker-compose.local.yml"
DEFAULT_MODEL="${OLLAMA_MODEL:-qwen2.5:7b-instruct}"

# -------------------------------------------------------------------- helpers
log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m OK\033[0m\n'; }
warn() { printf '\033[1;33m %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m[ERROR] %s\033[0m\n' "$*" >&2; exit 1; }

wait_healthy() {
  local name="$1" label="$2"
  printf '    等待 %s 就绪' "$label"
  local tries=0
  until docker ps --format '{{.Names}} {{.Status}}' | grep "$name" | grep -q healthy; do
    printf '.'
    sleep 3
    tries=$((tries + 1))
    if [ "$tries" -gt 60 ]; then
      echo
      die "$label 健康检查超时 (180s)。查看日志: docker logs $name"
    fi
  done
  ok
}

wait_http() {
  local url="$1" label="$2" tries=0
  printf '    探测 %s' "$label"
  until curl -fsS -o /dev/null "$url" 2>/dev/null; do
    printf '.'
    sleep 3
    tries=$((tries + 1))
    if [ "$tries" -gt 40 ]; then
      echo
      warn "$label 未在 120s 内响应 (可能仍在启动,稍后重试: $url)"
      return 0
    fi
  done
  ok
}

# ------------------------------------------------------------- [1/6] 前置检查
log "[1/6] 检查 Docker ..."
command -v docker >/dev/null 2>&1 || die "未安装 Docker。请先安装 Docker Desktop / Docker Engine。"
docker info >/dev/null 2>&1    || die "Docker 守护进程未运行。请先启动 Docker。"
if ! docker compose version >/dev/null 2>&1; then
  die "未找到 'docker compose' 子命令 (需 Docker Compose v2)。"
fi
ok

# ------------------------------------------------------- [2/6] 启动 compose
log "[2/6] 启动本地 docker compose ($COMPOSE_FILE) ..."
# 用 --build 保证代码/依赖变更后镜像重建;首次启动会构建 backend/frontend/paddleocr。
docker compose -f "$COMPOSE_FILE" up -d --build
ok

# --------------------------------------------- [3/6] 等待核心依赖 healthy
log "[3/6] 等待依赖服务就绪 ..."
wait_healthy waibao-postgres "PostgreSQL"
wait_healthy waibao-redis    "Redis"
wait_healthy waibao-ollama   "Ollama"

# --------------------------------------------------------- [4/6] 拉 LLM 模型
log "[4/6] 拉取默认 LLM 模型: $DEFAULT_MODEL ..."
bash scripts/setup_ollama.sh "$DEFAULT_MODEL"

# ---------------------------------------------------- [5/6] 预下载 OCR 模型
log "[5/6] 预下载 PaddleOCR 中英文模型 ..."
bash scripts/setup_paddleocr.sh ch en || \
  warn "paddleocr 模型预下载跳过 — 容器内首次识别时会自动拉取"

# ----------------------------------------- [6/6] 探测 backend / frontend
log "[6/6] 探测应用服务 ..."
wait_http "http://localhost:8000/api/health" "backend (:8000)"
wait_http "http://localhost:3000/"           "frontend (:3000)"

echo ""
log "本地全离线环境就绪。"
cat <<EOF

    前端 (求职者/HR/老板/部门):  http://localhost:3000
    后端 API + Swagger 文档:     http://localhost:8000/docs
    后端健康检查:                http://localhost:8000/api/health
    Ollama 本地模型:             http://localhost:11434  (数据不出网)
    PaddleOCR 本地 OCR:          http://localhost:8500/health (数据不出网)
    PostgreSQL:                  localhost:5432  (用户/库/密码见 .env.local)
    Redis:                       localhost:6379

    当前 LLM 模型: $DEFAULT_MODEL
    切换模型: OLLAMA_MODEL=glm4:9b bash scripts/start_local.sh
    查看日志: docker compose -f $COMPOSE_FILE logs -f
    停止环境: bash scripts/stop_local.sh
    导入测试数据: python scripts/seed_test_data.py
EOF
