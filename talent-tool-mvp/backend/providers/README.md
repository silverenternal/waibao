# Providers 抽象层

> **目的**: 把"调用哪家供应商"从业务代码里彻底剥离。改一行环境变量即可切换 LLM / Embedding / Vision / OCR / STT / Notify / CompanyLookup 的供应商,**业务代码零修改**。

---

## 📐 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│  Business layer (agents / pipelines / services)                 │
│                                                                 │
│   runtime.LLMClient  ───┐                                       │
│   resume_parser.py ─────┤                                       │
│   notify_dispatcher.py ─┼──> registry.get_xxx_provider()        │
│   compliance_service.py ─┘   (单例 + 懒加载 + 按 env 路由)         │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Provider abstraction (providers/registry.py)                   │
│                                                                 │
│  get_llm_provider()       get_embedding_provider()              │
│  get_vision_provider()    get_ocr_provider()                    │
│  get_stt_provider()       get_notify_provider(channel)          │
│  get_lookup_provider()                                         │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Shared infrastructure (providers/base.py)                      │
│                                                                 │
│   @with_resilience(                                           │
│       provider=..., method=...,                                │
│       rate_per_sec=10, burst=20,                               │
│       cost_calculator=..., tenant_arg="tenant_id",             │
│   )                                                            │
│   └── RetryPolicy (指数退避 + jitter)                            │
│   └── CircuitBreaker (closed/open/half_open)                   │
│   └── TokenBucket (per-provider 限流)                          │
│   └── CostTracker (per-tenant 日预算)                           │
│   └── ProviderMetrics (Prometheus)                              │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Concrete providers (providers/<capability>/<vendor>_provider.py)│
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速上手

### 业务代码中使用

```python
from providers.registry import get_llm_provider, get_embedding_provider, get_notify_provider

# 1. LLM
llm = get_llm_provider()
resp = await llm.chat(
    messages=[{"role": "user", "content": "你好"}],
    model="gpt-4o-mini",
    temperature=0.7,
)

# 2. Embedding
embedder = get_embedding_provider()
vec = await embedder.embed(["招聘候选人画像"])

# 3. 通知
notifier = get_notify_provider("dingtalk")
await notifier.send(
    recipient="group_xxx",
    subject="情绪告警",
    body="用户表达出严重焦虑,请关注",
)
```

### 切换供应商 (零代码改动)

```bash
# .env
LLM_PROVIDER=anthropic          # 之前是 openai
EMBEDDING_PROVIDER=zhipu        # 之前是 openai
NOTIFY_DINGTALK_ENABLED=true    # 启用钉钉通道
OCR_PROVIDER=tencent            # 之前是 mock
```

重启后,所有调用自动走新供应商。

---

## 📦 支持的供应商

### LLM (6 家)

| Provider        | ENV 标识       | API 风格 | 备注 |
|-----------------|----------------|----------|------|
| OpenAI          | `openai`       | OpenAI 原生 | GPT-4o / GPT-4o-mini / o1 |
| Anthropic       | `anthropic`    | Anthropic Messages | Claude 3.5 / 3.7 |
| DeepSeek        | `deepseek`     | OpenAI 兼容 | deepseek-chat / deepseek-coder |
| 智谱 GLM        | `zhipu`        | OpenAI 兼容 | GLM-4 / GLM-4-Plus |
| 通义千问         | `tongyi`       | OpenAI 兼容 (DashScope) | qwen-plus / qwen-max |
| 月之暗面 Kimi   | `moonshot`     | OpenAI 兼容 | moonshot-v1-8k/32k/128k |

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1   # 可选,兼容代理

LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxx

LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

LLM_PROVIDER=zhipu
ZHIPU_API_KEY=xxx
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4

LLM_PROVIDER=tongyi
DASHSCOPE_API_KEY=sk-xxx
TONGYI_API_KEY=sk-xxx        # 兼容别名
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

LLM_PROVIDER=moonshot
MOONSHOT_API_KEY=sk-xxx
MOONSHOT_BASE_URL=https://api.moonshot.cn/v1
```

### Embedding (3 家)

| Provider  | ENV 标识   | 模型 |
|-----------|------------|------|
| OpenAI    | `openai`   | text-embedding-3-small / large |
| 智谱       | `zhipu`    | embedding-2 |
| 通义       | `tongyi`   | text-embedding-v3 |

```bash
EMBEDDING_PROVIDER=openai   # 复用 OPENAI_API_KEY
EMBEDDING_PROVIDER=zhipu    # 复用 ZHIPU_API_KEY
EMBEDDING_PROVIDER=tongyi   # 复用 DASHSCOPE_API_KEY
```

### Vision (2 家)

| Provider  | ENV 标识   | 模型 |
|-----------|------------|------|
| GPT-4V    | `gpt4v`    | gpt-4o |
| 通义千问 VL | `qwen_vl` | qwen-vl-plus / qwen-vl-max |

```bash
VISION_PROVIDER=gpt4v       # 复用 OPENAI_API_KEY
VISION_PROVIDER=qwen_vl     # 复用 DASHSCOPE_API_KEY
```

### OCR (3 家 + 复用 Vision)

| Provider   | ENV 标识    | 备注 |
|------------|-------------|------|
| 腾讯云     | `tencent`   | GeneralBasicOCR |
| 百度       | `baidu`     | 通用文字识别 |
| 阿里云读光 | `aliyun`    | 阿里云 OCR |
| GPT-4V     | `gpt4v`     | 复用 VISION_PROVIDER 作为 OCR 兜底 |

```bash
OCR_PROVIDER=tencent
TENCENT_SECRET_ID=xxx
TENCENT_SECRET_KEY=xxx
TENCENT_OCR_REGION=ap-guangzhou

OCR_PROVIDER=baidu
BAIDU_OCR_API_KEY=xxx
BAIDU_OCR_SECRET_KEY=xxx

OCR_PROVIDER=aliyun
ALIYUN_ACCESS_KEY_ID=xxx
ALIYUN_ACCESS_KEY_SECRET=xxx
```

### STT (2 家)

| Provider   | ENV 标识    | 模型 |
|------------|-------------|------|
| OpenAI Whisper | `whisper` | whisper-1 |
| 阿里云一句话识别 | `aliyun` | 阿里云 ASR |

```bash
STT_PROVIDER=whisper         # 复用 OPENAI_API_KEY
STT_PROVIDER=aliyun
ALIYUN_ASR_APP_KEY=xxx
ALIYUN_ASR_APP_KEY_SECRET=xxx   # 部分 region 需要
ALIYUN_ASR_TOKEN=xxx            # 或走临时 token
```

### Notify (5 通道)

| 通道         | ENV 标识       | 启用 ENV |
|--------------|----------------|----------|
| SMTP / SendGrid | `smtp`     | `NOTIFY_SMTP_ENABLED=true` |
| 钉钉机器人    | `dingtalk`     | `NOTIFY_DINGTALK_ENABLED=true` |
| 飞书 (Lark) 机器人 | `feishu` | `NOTIFY_FEISHU_ENABLED=true` |
| 企业微信机器人 | `wecom`     | `NOTIFY_WECOM_ENABLED=true` |
| 通用 Webhook | `webhook`      | `NOTIFY_WEBHOOK_ENABLED=true` |

```bash
NOTIFY_SMTP_ENABLED=true
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=SG.xxx
SMTP_FROM=noreply@example.com

NOTIFY_DINGTALK_ENABLED=true
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
DINGTALK_SECRET=SECxxx        # 加签密钥 (可选)

NOTIFY_FEISHU_ENABLED=true
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
FEISHU_SECRET=xxx

NOTIFY_WECOM_ENABLED=true
WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx

NOTIFY_WEBHOOK_ENABLED=true
WEBHOOK_URL=https://hooks.example.com/notify
WEBHOOK_METHOD=POST
WEBHOOK_TEMPLATE=json
WEBHOOK_HEADERS="X-Token: xxx\nX-Env: prod"
```

### CompanyLookup (2 家)

| Provider  | ENV 标识       | 备注 |
|-----------|----------------|------|
| 天眼查     | `tianyancha`   | open.ic.baseinfo |
| 启信宝     | `qichacha`     | GetBasicDetailsByName |

```bash
LOOKUP_PROVIDER=tianyancha
TIANYANCHA_API_KEY=xxx
TIANYANCHA_BASE_URL=https://open.tianyancha.com/services/open/ic/baseinfo/2.0

LOOKUP_PROVIDER=qichacha
QICHACHA_APP_KEY=xxx
QICHACHA_APP_SECRET=xxx
QICHACHA_BASE_URL=https://api.qichacha.com/ECIV4/GetBasicDetailsByName
```

---

## 🛡️ 共享中间件 (`base.py`)

每个 Provider 的对外方法都被 `@with_resilience` 装饰,自动获得:

### 1. 指数退避重试 (RetryPolicy)
```python
@dataclass(slots=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: float = 0.2
```

### 2. 三态熔断器 (CircuitBreaker)
- `closed`: 正常请求
- `open`: 连续 5 次失败 → 拒绝所有请求 60s
- `half_open`: 探测一个请求,成功则回到 closed

### 3. 令牌桶限流 (TokenBucket)
```python
with_resilience(rate_per_sec=10, burst=20)  # 每秒 10 个,允许短时突发 20 个
```

### 4. 成本追踪 (CostTracker)
```python
with_resilience(
    cost_calculator=lambda resp: resp.usage.total_tokens * 0.000002,  # USD
    tenant_arg="tenant_id",
)
# 单租户日预算:
DAILY_BUDGET_USD=50
TENANT_DAILY_BUDGET_USD_acme=200
```

### 5. Prometheus 指标
自动暴露:
- `provider_calls_total{provider,method,status}`
- `provider_latency_seconds{provider,method}` (Histogram)

---

## 🧪 单元测试

每个 capability 维度都有 mock provider + 真实 provider 的双层测试:

```bash
# 仅跑 provider 测试
cd backend && python -m pytest providers/tests/ -v

# 跑全部
cd backend && python -m pytest -v
```

测试覆盖:
- `tests/test_registry.py` — registry 单例 + env 路由
- `tests/test_base.py` — 重试/熔断/限流/成本
- `tests/test_llm_providers.py` — 6 家 LLM provider 的 chat/stream/error
- `tests/test_notify_dispatcher.py` — 5 通道 dispatch
- `tests/test_notify_templates.py` — 模板渲染
- `tests/test_credit_code_validator.py` + `tests/test_compliance_service.py` — OCR+lookup 编排

---

## 🆕 如何新增一个 Provider

1. **创建文件**: `providers/<capability>/<vendor>_provider.py`
2. **继承基类**: `LLMProvider` / `EmbeddingProvider` / ...
3. **加装饰器**: 在每个对外方法上加 `@with_resilience(provider="<vendor>", method="<method>")`
4. **注册**: 在 `providers/registry.py::mapping` 中加入新条目
5. **更新 env 示例**: 在 `providers/config.example.env` 注释新变量
6. **测试**: 在 `providers/tests/` 加至少 3 个用例
7. **更新文档**: 本 README + `docs/ARCHITECTURE.md`

---

## ⚠️ 错误约定

所有 Provider 抛出的异常均继承 `providers.exceptions.ProviderError`:

```python
from providers.exceptions import (
    AuthError,              # 鉴权失败 (401/403) — 不重试
    RateLimitError,         # 限流 (429) — 重试
    QuotaExceededError,     # 配额耗尽 (402) — 不重试
    TimeoutError,           # 超时 — 重试
    UpstreamUnavailableError,  # 5xx — 重试
    CircuitOpenError,       # 熔断打开 — 不重试 (直接返回)
    BudgetExceeded,         # 单租户日预算耗尽
    InvalidRequestError,    # 参数错误 (4xx) — 不重试
)
```

业务代码用 `try/except ProviderError` 统一兜底即可。

---

## 📚 相关文档

- [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) — Provider 在整体架构中的位置
- [`docs/AGENTS.md`](../../../docs/AGENTS.md) — 各 Agent 现在走哪个 Provider
- [`providers/config.example.env`](./config.example.env) — 完整 ENV 变量清单