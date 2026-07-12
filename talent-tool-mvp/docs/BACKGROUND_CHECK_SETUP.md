# BACKGROUND_CHECK_SETUP — Checkr 背调 真实接入 (T1805)

> 适用: v3.0+. 美国市场主流: Checkr. 国内后续可加 iCIMS / HireRight / 中华背调.

背调 provider 配置: `BG_CHECK_PROVIDER=checkr|mock`

缺省 `mock` 时系统使用业务 mock provider; 不会触发外部调用 / 真实扣费.

---

## 1. 申请 Checkr 账号

1. 注册 [Checkr Dashboard](https://dashboard.checkr.com/) 企业账号
2. 完成 KYC + 支付方式配置
3. (可选) 申请 sandbox 环境 (`api.checkr-staging.com`) — 用于开发测试

### 1.1 拿到 API Key

控制台 → **Developers → API Keys**, 复制:
- Standard 或 Live Key → `CHECKR_API_KEY=acct_...`

### 1.2 创建 Webhook 端点

控制台 → **Developers → Webhooks**, 添加:
- URL: `https://<your-domain>/api/background-checks/webhook`
- Events:
  - `report.created`
  - `report.updated`
  - `report.completed`
- 拿到 webhook secret → `CHECKR_WEBHOOK_SECRET`

---

## 2. 环境变量

```bash
export BG_CHECK_PROVIDER=checkr
export CHECKR_API_KEY="acct_..."
# 可选: 测试桩地址
export CHECKR_BASE_URL="https://api.checkr.com/v1"
# 可选: Checkr 默认报告包
export CHECKR_PACKAGE="tasker_standard"
# Webhook 验签 (HMAC-SHA256)
export CHECKR_WEBHOOK_SECRET="whsec_..."
export CHECKR_WEBHOOK_TOLERANCE_SEC=300
```

### 2.1 API 包 (package) 选择

| slug | 内容 | 速度 | 成本 |
| ---- | ---- | ---- | ---- |
| `tasker_standard` | criminal + employment | 1-3 天 | $ |
| `tasker_pro` | + education + reference | 3-5 天 | $$ |
| `driver_pro` | + MVR (驾照记录) | 5-7 天 | $$$ |

可分别设置 `CHECKR_PACKAGE` 全局默认值, 也可在代码里覆盖.

---

## 3. 调用流程

### 3.1 发起背景调查

```python
from providers.background_check.types import CheckType

check = await provider.initiate_check(
    candidate_id="cand_001",
    check_types=[
        CheckType(code="criminal", required=True),
        CheckType(code="employment", required=True),
        CheckType(code="education", required=False),
    ],
    candidate_email="alice@example.com",
    candidate_name="Alice Demo",
    metadata={
        "offer_id": "offer_xxx",  # 关联到我们系统内的 Offer
        "job_id": "role_001",
    },
)
# check.check_id  → Checkr report id (用于后续 status 查询)
# check.report_url → 候选人授权链接 (收邮件提醒点进去授权)
```

### 3.2 拉报告状态

```python
status = await provider.get_status(check.check_id)
# status.status ∈ { pending, in_progress, consider, clear, suspended }
# status.progress_pct  → 0-100
# status.findings      → List[Finding]
```

### 3.3 Webhook 签名校验 + 解析

```python
from providers.background_check.checkr import (
    CheckrWebhookVerifier, parse_webhook_event, handle_webhook_event,
)

verifier = CheckrWebhookVerifier()  # 默认读 CHECKR_WEBHOOK_SECRET
ok, reason = verifier.verify(
    raw_body=request.body,
    signature=request.headers["signature"],
    timestamp=request.headers["timestamp"],
)
if ok:
    evt = parse_webhook_event(request.body)
    out = handle_webhook_event(evt, on_status_update=my_db_callback)
    # out["check_id"], out["status"], out["action"]
```

签名协议:
- Checkr 用 HMAC-SHA256
- `signature` 是 HMAC(secret, `timestamp + "." + raw_body`) 的 hex
- `timestamp` 必须落在 ±`tolerance_sec` 秒内

---

## 4. Offer 前自动背调 (T1307)

`hr_service_agent.py` 中内置钩子:

```
触发条件: stage = 'recruiting' AND (text 中含 '发offer' / '录用' / '背调')
         OR ctx["trigger_bg_check"] = true
         ↓
BackgroundCheckService.trigger_pre_offer(...)
  ↓
  若已有 running check (same candidate_id) → skipped
  否则 → 发起真 check
  ↓
  返回 { check_id, status='pending'/'skipped', provider='checkr' }
```

业务 API:
```
POST /api/background-checks/trigger-pre-offer
{
  "candidate_id": "...",
  "candidate_email": "...",
  "candidate_name": "...",
  "offer_id": "...",      # 关键: 给候选人授权链接
  "job_id": "..."
}
```

---

## 5. 集成测试

```bash
export CHECKR_API_KEY=acct_...
export CHECKR_WEBHOOK_SECRET=whsec_test
pytest -m real_api backend/providers/background_check/tests/test_checkr_real.py -v
```

覆盖:
- Basic auth 编码格式
- 真实创建候选人 + 创建 report → 拿到 check_id
- 真实查 status (起步时通常 pending / in_progress)
- Webhook verifier 单元测试:
  - 有效签名 → ok
  - 错误签名 → signature-mismatch
  - 过期 timestamp → timestamp-out-of-window
  - dev mode (无 secret) → 跳过校验
- `parse_webhook_event` / `handle_webhook_event` 字段归一化

⚠️ **注意**: Checkr 每个真实 report 都会 **扣费** . 测试请用 sandbox 或严格控制频率.

---

## 6. 一次性集成 demo

```bash
python scripts/full_hire_workflow.py \
  --bg-check-provider checkr \
  --candidate-email alice@example.com
```

会打印:
1. check_id + report_url
2. 当前 status + progress_pct + findings 数量
3. **demo Step 6** 显示 HR agent 自动触发的逻辑

---

## 7. 业务侧流程图

```
候选人在 HR portal 点 "准备发 Offer"
  ↓ (前端)
POST /api/offers/{offer_id}/send  (v3.1)
  ↓ (后端)
  调 BackgroundCheckService.trigger_pre_offer(candidate_id, ...)
    ↓
    Checkr.create_candidate + create_report
    ↓ 立刻返回 pending
  候选人收到 Checkr 邮件 → 点授权链接
    ↓
    Checkr 完成调查 → push webhook
    ↓
    /api/background-checks/webhook → CheckrWebhookVerifier.verify
      ↓
      校验通过 → handle_webhook_event → 更新 background_checks.status
    ↓
    triggered_by = 't1805-prior-offer-check' 自动呈现给 Offer 详情页
```

---

## 8. 安全 / 合规

- **APAC 限制**: Checkr 仅服务美国市场; 国内候选人需走 HireRight / iCIMS / 中华背调
- **PII 加密**: `candidates.ssn` / 生日等敏感字段在落库前 AES-GCM 加密 (T1502 范畴)
- **公平信用报告法 (FCRA)**: Checkr 自动套用 — 触发"不利行动"前必须人工审核, 不可自动拒 Offer
- **数据保留**: 报告 PDF 默认 7 年 (Checkr 永久), 业务侧应定期归档

---

## 9. FAQ

**Q: `401 unauthorized` for `acct_...`**
A: 确认 key 类型 (live vs test); key 失效时 Checkr 会邮件提醒 — 控制台 → 重新生成.

**Q: `package 'xxx' not found`**
A: 不同 Checkr tier 可用的 package 不一样, 在控制台 → Account Settings → Packages 查可用 slug.

**Q: Webhook 一直 401**
A: webhook 端点必须返回 200; 失败 Checkr 会 exponential retry; 调试时设置 `CHECKR_WEBHOOK_TOLERANCE_SEC` 增大.

**Q: 候选人多次发起会被去重吗?**
A: `BackgroundCheckService.trigger_pre_offer` 检查 24h 内 running 任务, 已存在 → 短路返回 skipped.
要重复发起可手动 DELETE `background_checks` 行.

---

## 10. 相关任务

- T1307 — BackgroundCheck 抽象层 (checkr / mock)
- T1307 — Offer 前自动背调 (HR service agent)
- T1802 — Offer 真实业务上线
- T1805 (本文档) — Checkr webhook verifier + 真实发起 + 单元测试
