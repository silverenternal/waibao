#!/usr/bin/env bash
# =============================================================================
# scripts/setup_paddleocr.sh — v11.0 / T6102 预下载 PaddleOCR 中英文模型
#
# 用法:
#   bash scripts/setup_paddleocr.sh           # 预下载默认中文(ch)+ 英文模型
#   bash scripts/setup_paddleocr.sh ch en     # 指定语言
#
# 模型在甲方内网下载一次后持久化到 paddleocr_models volume / 本地缓存目录,
# 之后离线环境也能直接复用 —— 简历/资质识别全程不出网。
# =============================================================================
set -euo pipefail

if [ "$#" -gt 0 ]; then
  LANGS=("$@")
else
  LANGS=("ch" "en")
fi

MODELS_DIR="${PADDLE_OCR_MODEL_DIR:-./models/paddle}"
mkdir -p "$MODELS_DIR"
echo "==> PaddleOCR 模型目标目录: $MODELS_DIR"
echo "==> 语言: ${LANGS[*]}"

# 内联 python 预加载逻辑 (在容器或本地复用)
read -r -d '' PY <<'PYEOF' || true
import sys
from paddleocr import PaddleOCR
langs = sys.argv[1:] or ["ch", "en"]
for lang in set(langs):
    print(f"==> 预加载 PaddleOCR lang={lang}")
    PaddleOCR(lang=lang, use_angle_cls=True, use_gpu=False, show_log=True)
print("==> 模型预下载完成")
PYEOF

if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q waibao-paddleocr; then
  echo "==> 在容器 waibao-paddleocr 内预下载模型..."
  docker exec -i -e PADDLE_OCR_MODEL_DIR=/models/paddle waibao-paddleocr python - "${LANGS[@]}" <<<"$PY"
else
  echo "==> 用本地 python 预下载模型 (需要 pip install paddleocr paddlepaddle)..."
  python - "${LANGS[@]}" <<<"$PY"
fi

cat <<EOF

==> PaddleOCR 模型就绪。
==> 验证 (容器场景):
    docker exec waibao-paddleocr curl -s http://localhost:8500/health
==> 提示:
    - 简历 / 资质 OCR 默认走本地 (OCR_PROVIDER=paddle),数据不出甲方环境。
    - 切回纯本地 mock (开发/测试): OCR_PROVIDER=mock
    - 中文模型 (ch) 同时识别中英文;纯英文用 en。
EOF
