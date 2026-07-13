# T3001 — LoRA Fine-tuning (LLaMA-Factory)

为 3 类招聘任务微调专属 LoRA adapter, 让开源 7B 模型在特定任务上逼近甚至超过通用大模型, 同时把推理成本压到自托管水平。

## 选型 (Phase 1)

| 组件 | 选择 | 理由 |
|------|------|------|
| 训练框架 | **LLaMA-Factory** (45k+ ⭐) | YAML 驱动, 统一 SFT/LoRA/QLoRA, 支持 Qwen2.5 / Llama-3 全家桶 |
| 微调方法 | **QLoRA** (4bit, rank=8/alpha=16) | 单卡 24GB 可训 7B, 显存友好 |
| 基座 | Qwen2.5-7B-Instruct / Llama-3-8B | 中文强 / 英文强, 二选一 |
| 推理 | **vLLM** (`--enable-lora`) | OpenAI 兼容, 多 adapter 热挂载 |

## 3 个 LoRA

| model_id | 任务 | 训练数据来源 |
|----------|------|-------------|
| `resume_scoring-v1` | 简历评分 | HR 历史评分 + 候选人特征 |
| `bias_review-v1` | 偏见审查 | 审查历史结果 + 原始文本 |
| `hrbp_summary-v1` | HRBP 摘要 | 工单 + 人工撰写摘要 |

## 端到端流程

数据准备 → 训练 (QLoRA) → 评估 (金标准 + Agenta evaluator) → 部署 (vLLM) → 注册 (registry)

由 `backend/services/training/pipeline.py::run_pipeline` 编排。无 GPU 时自动 `dry_run`, 产物骨架 + 启发式评估让 pipeline 端到端可跑 (CI 友好)。

## 用法

```bash
# 1. 准备数据集 (落到 lora_datasets volume)
cd backend && python -c "from services.training import prepare_dataset, TaskKind; \
  print(prepare_dataset(TaskKind.RESUME_SCORING, out_dir='../infra/training/data')[0])"

# 2. 训练 (GPU)
docker compose -f infra/training/docker-compose.yml --profile train run --rm trainer \
  llamafactory-cli train /workspace/config/resume_scoring.yaml

# 3. 起推理服务 (vLLM, 多 LoRA)
BASE_MODEL=Qwen/Qwen2.5-7B-Instruct docker compose -f infra/training/docker-compose.yml up -d vllm

# 4. 业务侧走 custom_lora provider (LLM_PROVIDER=custom_lora)
#    provider 从 registry 解析 task -> active adapter, 请求 vLLM /v1/chat/completions
```

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `BASE_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | 基座模型 |
| `VLLM_PORT` | `8001` | vLLM 对外端口 |
| `VLLM_BASE_URL` | `http://vllm:8000` | 后端连 vLLM 地址 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | 国内 HF 镜像 |

需 NVIDIA Container Toolkit (nvidia-docker2)。
