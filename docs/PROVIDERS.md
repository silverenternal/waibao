# Providers & 横切能力清单 (v3.0)

> 本文档汇总 v3.0 全部"供应商 + 横切能力"清单,涵盖 23 个供应商适配器 + 6 大横切能力(i18n / Webhook / 公开 API / 规则引擎 / A/B / OTel)。

---

## 🔌 Provider 适配器清单 (v2.0 + v3.0)

按"能力维度"组织。每个维度都支持"插拔 + 多供应商 fallback"。

### LLM (6 个)
| Provider | 模型 | 用途 | 适配器 |
|---|---|---|---|
| OpenAI | gpt-4o, gpt-4o-mini, o1 | 默认 + 工具调用 | `providers/llm/openai.py` |
| Anthropic | claude-3.5-sonnet, claude-3-opus | 长上下文 + 推理 | `providers/llm/anthropic.py` |
| DeepSeek | deepseek-chat, deepseek-coder | 国内 + 性价比 | `providers/llm/deepseek.py` |
| 智谱 GLM | glm-4, glm-4v | 国内合规 | `providers/llm/zhipu.py` |
| 通义千问 | qwen-max, qwen-long | 国内 + 长文 | `providers/llm/qwen.py` |
| Moonshot Kimi | moonshot-v1-128k | 长上下文 | `providers/llm/kimi.py` |

### Embedding (3 个)
| Provider | 模型 | 维度 | 适配器 |
|---|---|---|---|
| OpenAI | text-embedding-3-small | 1536 | `providers/embedding/openai.py` |
| 智谱 | embedding-2 | 1024 | `providers/embedding/zhipu.py` |
| BGE | bge-large-zh-v1.5 | 1024 | `providers/embedding/bge.py` |

### Vision (2 个)
| Provider | 模型 | 适配器 |
|---|---|---|
| OpenAI | gpt-4o-vision | `providers/vision/openai.py` |
| 智谱 | glm-4v | `providers/vision/zhipu.py` |

### OCR (3 个)
| Provider | 用途 | 适配器 |
|---|---|---|
| 百度 OCR | 简历 / 资质 | `providers/ocr/baidu.py` |
| 腾讯云 OCR | 通用 | `providers/ocr/tencent.py` |
| 阿里云 OCR | 表格识别 | `providers/ocr/aliyun.py` |

### STT / 语音 (2 个)
| Provider | 模型 | 适配器 |
|---|---|---|
| OpenAI Whisper | whisper-1 | `providers/stt/whisper.py` |
| 阿里云语音 | asr-v1 | `providers/stt/aliyun.py` |

### Notify 通知 (5 个通道)
| 通道 | 用途 | 适配器 |
|---|---|---|
| 钉钉 | 企业 IM | `providers/notify/dingtalk.py` |
| 飞书 | 企业 IM | `providers/notify/feishu.py` |
| 企业微信 | 企业 IM | `providers/notify/wecom.py` |
| SMTP 邮件 | 通用 | `providers/notify/smtp.py` |
| Webhook 出口 | 自定义集成 | `providers/notify/webhook.py` |

### Lookup / 工商查询 (2 个)
| Provider | 用途 | 适配器 |
|---|---|---|
| 天眼查 | 企业信用 | `providers/lookup/tianyancha.py` |
| 启信宝 | 企业信用 | `providers/lookup/qixinbao.py` |

**合计:23 个供应商适配器**

### 配置示例

```bash
# .env
LLM_PROVIDER=anthropic              # 切换默认 LLM
LLM_FALLBACK=openai,deepseek        # 失败 fallback 链
EMBED_PROVIDER=openai
OCR_PROVIDER=baidu
NOTIFY_PRIMARY=dingtalk
NOTIFY_FALLBACK=feishu,smtp

# 各供应商密钥
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
DEEPSEEK_API_KEY=sk-xxx
ZHIPU_API_KEY=xxx
QWEN_API_KEY=xxx
KIMI_API_KEY=xxx
BAIDU_OCR_API_KEY=xxx
TENCENT_OCR_SECRET=xxx
ALIYUN_OCR_KEY=xxx
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
SMTP_HOST=smtp.example.com
SMTP_USER=xxx
SMTP_PASS=xxx
TIANYANCHA_API_KEY=xxx
QIXINBAO_API_KEY=xxx
```

### 故障转移策略

`with_resilience` 装饰器统一处理:
- **重试**:指数退避,最多 3 次
- **降级**:同能力内 fallback 到下一个 provider
- **熔断**:连续失败 5 次,熔断 60s
- **监控**:每次调用 emit span + metric,失败入 `provider_health` 表

---

## 🌍 i18n 三语 (zh-CN / en-US / ja-JP)

### 翻译文件位置

```
frontend/messages/
├── zh-CN.json    # 简体中文 (主语言)
├── en-US.json    # English
└── ja-JP.json    # 日本語
```

### Key 命名规范

```json
{
  "common": {
    "save": "保存",
    "cancel": "取消",
    "loading": "加载中..."
  },
  "jobseeker": {
    "home": {
      "title": "找工作",
      "greeting": "你好,{{name}}"
    },
    "emotion": {
      "label": {
        "joy": "开心",
        "sadness": "沮丧",
        "anger": "愤怒",
        "fear": "焦虑"
      }
    }
  },
  "employer": {
    "strategy": {
      "title": "战略地图"
    }
  }
}
```

### 新增 Key 的流程

1. 在 `zh-CN.json` 加 key + 中文
2. 跑 `npm run i18n:check` — 强制要求三语都存在
3. 用 LLM 生成初版英文 + 日文翻译
4. 人工 review(尤其日语敬语)
5. 提交 PR,CI 自动校对

### 后端 i18n

Agent 的 prompt 模板接受 `locale` 参数:

```python
PLANNER_PROMPT = {
    "zh-CN": "你是一个职业规划师...",
    "en-US": "You are a career planner...",
    "ja-JP": "あなたはキャリアプランナーです...",
}
```

LLM 生成解释 / 反馈时,根据用户 locale 自动选择 prompt 模板。

### 守门

```bash
# 前端 CI
npm run i18n:check    # 失败立即 fail,不允许三语不一致
```

---

## 📡 Webhook DSL (T804 衍生)

### 事件类型

| 事件 | 触发条件 | Payload 示例 |
|---|---|---|
| `match.created` | 新匹配生成 | `{match_id, candidate_id, role_id, score}` |
| `match.shortlisted` | 候选人被 shortlist | `{match_id, actor_id}` |
| `ticket.created` | 工单创建 | `{ticket_id, category, priority}` |
| `ticket.escalated` | 工单升级 | `{ticket_id, from, to, reason}` |
| `rule.triggered` | 规则触发 | `{rule_id, action, context}` |
| `bias.detected` | 检测到偏见 | `{brief_id, category, severity}` |
| `audit.recorded` | 审计事件 | `{action, actor_id, resource}` |

### 订阅配置

```json
{
  "url": "https://customer.example.com/webhooks/waibao",
  "events": ["match.created", "ticket.escalated"],
  "secret": "whsec_xxx",   // HMAC 密钥
  "active": true,
  "retry_policy": {
    "max_attempts": 5,
    "backoff": "exponential"
  }
}
```

### 签名验证

接收方验证:

```python
import hmac, hashlib
def verify(signature: str, body: bytes, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

Header: `X-Waibao-Signature: sha256=abc123...`

---

## ⚙️ 规则 DSL (T804)

### Schema (JSON 形式)

```json
{
  "id": "auto-escalate-high-priority",
  "name": "高优先级工单 30min 内未响应则升级",
  "trigger": "ticket.created",
  "when": {
    "all": [
      {"field": "priority", "op": "==", "value": "high"},
      {"field": "minutes_since_created", "op": ">", "value": 30}
    ]
  },
  "then": [
    {"action": "escalate", "args": ["to:hrbp", "reason:SLA breach"]},
    {"action": "notify", "args": ["dingtalk", "HRBP on duty"]}
  ],
  "cooldown_seconds": 600,
  "enabled": true
}
```

### 字段运算符 (op)

| op | 含义 | 示例 |
|---|---|---|
| `==` | 等于 | `priority == high` |
| `!=` | 不等于 | `status != closed` |
| `>` `>=` `<` `<=` | 数值比较 | `score >= 80` |
| `in` | 包含 | `severity in [high, critical]` |
| `contains` | 字符串包含 | `title contains 紧急` |
| `matches` | 正则 | `phone matches ^1[3-9]\\d{9}$` |
| `exists` | 字段存在 | `metadata.reason exists` |

### 组合逻辑

```json
{
  "all": [c1, c2, c3],   // AND
  "any": [c1, c2, c3],   // OR
  "not": c1              // NOT
}
```

### 内置触发器 (12+)

| Trigger | 触发时机 |
|---|---|
| `resume.uploaded` | 简历上传完成 |
| `match.created` | 匹配生成 |
| `ticket.created` | 工单创建 |
| `ticket.sla_warning` | SLA 即将逾期 |
| `bias.detected` | 偏见检测命中 |
| `policy.updated` | 政策更新 |
| `rule.scheduled` | 定时调度 |
| `webhook.received` | 收到外部 webhook |
| `audit.anomaly` | 审计异常 |
| `cost.spike` | 成本突增 |
| `auth.failed` | 认证失败 N 次 |
| `data.export` | 数据导出请求 |

### Action 类型

| Action | Args | 效果 |
|---|---|---|
| `create_ticket` | `[category, priority, ...]` | 自动建工单 |
| `notify` | `[channel, message]` | 触发通知 |
| `webhook` | `[subscription_id, event]` | 触发外部 webhook |
| `adjust_weight` | `[role, dimension, factor]` | 微调匹配权重 |
| `archive` | `[resource_type, id]` | 归档 |
| `log_audit` | `[action, metadata]` | 强制写审计 |

---

## 🔑 公开 API Key

### Scope 列表

| Scope | 允许的端点 |
|---|---|
| `read:roles` | GET /api/public/roles, /api/public/roles/{id} |
| `read:candidates` | GET /api/public/candidates (脱敏) |
| `read:matches` | GET /api/public/matches |
| `write:notes` | POST /api/public/notes |
| `admin:*` | 所有 admin 端点(慎发) |

### Rate Limit

- 默认 60 req/min/key
- `429 Too Many Requests` + `Retry-After` header
- Burstable 到 120 req/min(短时)

### 用法

```bash
curl -H "Authorization: Bearer wk_live_xxx" \
     https://api.waibao.example.com/api/public/roles
```

---

## 🧪 A/B 实验

### 创建实验

```json
{
  "key": "match-ui-v2",
  "description": "新匹配解释器 UI",
  "variants": [
    {"name": "control", "weight": 50},
    {"name": "treatment", "weight": 50}
  ],
  "metrics": ["match_click_rate", "interview_request_rate"],
  "stop_conditions": {
    "min_sample_size": 1000,
    "min_runtime_days": 7
  }
}
```

### 显著性检验

内置 Welch's t-test。Admin 在 `/admin/ab/{key}/results` 看:
- 各变体均值 + 95% CI
- p-value + 显著性
- 推荐决策(继续 / 停止 / 延长)

---

## 📊 OpenTelemetry

### 埋点助手

```python
from services.telemetry import span, init_telemetry

init_telemetry(service_name="waibao-backend", otlp_endpoint="http://otel-collector:4317")

with span("llm_call", provider="anthropic", model="claude-3"):
    response = await llm.complete(messages)
```

### Span 属性约定

- `provider`:供应商名
- `model`:模型
- `agent`:Agent 名(可选)
- `user_id`:用户 ID(脱敏)
- `tenant_id`:租户 ID

### 导出

- 生产:OTLP gRPC → OTel Collector → Jaeger/Tempo
- 开发:Console exporter(默认)

### Prometheus 指标

`/metrics` 端点暴露:
- `waibao_llm_call_total{provider,model,status}`
- `waibao_llm_call_duration_seconds{provider,model}`
- `waibao_agent_runs_total{agent,status}`
- `waibao_tickets_open{priority,category}`

---

## 📜 Changelog

- **v3.0 (2026-07)**: i18n / Webhook / 公开 API / 规则引擎 / A/B / OTel
- **v2.0 (2026-06)**: 23 个供应商适配器
- **v1.0 (2026-04)**: 16 个智能体 + 30+ API
