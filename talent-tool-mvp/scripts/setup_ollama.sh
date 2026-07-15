#!/usr/bin/env bash
# =============================================================================
# scripts/setup_ollama.sh — v11.0 一键拉取本地 Ollama 模型
#
# 用法:
#   bash scripts/setup_ollama.sh                 # 拉默认 qwen2.5:7b-instruct
#   bash scripts/setup_ollama.sh glm4:9b          # 拉指定模型
#
# 模型全程在甲方内网下载/运行,推理数据绝不出网。
# =============================================================================
set -euo pipefail

DEFAULT_MODEL="qwen2.5:7b-instruct"
MODEL="${1:-${OLLAMA_MODEL:-$DEFAULT_MODEL}}"

# 优先在容器内执行 (docker compose 场景);否则用本地 ollama CLI。
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q waibao-ollama; then
  echo "==> 在容器 waibao-ollama 内拉取模型: $MODEL"
  docker exec -i waibao-ollama ollama pull "$MODEL"
elif command -v ollama >/dev/null 2>&1; then
  echo "==> 用本地 ollama CLI 拉取模型: $MODEL"
  ollama pull "$MODEL"
else
  cat >&2 <<'EOF'
[ERROR] 未找到运行中的 waibao-ollama 容器,也未安装本地 ollama CLI。
请先启动本地环境: bash scripts/start_local.sh
EOF
  exit 1
fi

echo ""
echo "==> 模型就绪: $MODEL"
echo "==> 备选中文/通用模型:"
echo "    qwen2.5:7b-instruct  (中文最好, 默认)"
echo "    glm4:9b               (智谱 GLM, 中英均衡)"
echo "    llama3.1:8b           (Meta Llama, 英文强)"
echo ""
echo "验证: curl -s http://localhost:11434/v1/models"
