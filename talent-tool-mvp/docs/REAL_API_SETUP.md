# Waibao v4.0 真实 API 申请 & 配置指南 (T1701)

> 12+ 第三方供应商真实接入步骤、限流、配额、安全
>
> 配套文件:
> - 配置模板:  [`backend/config/.env.example`](../talent-tool-mvp/backend/config/.env.example)
> - 测试用例:  `backend/providers/**/tests/test_real_*.py`
> - 一键配置:  [`scripts/setup_real_keys.sh`](../talent-tool-mvp/scripts/setup_real_keys.sh)

---

## 0. 快速开始

```bash
# 1. 复制环境模板
cd talent-tool-mvp
cp backend/config/.env.example backend/.env

# 2. 启动交互式配置脚本
bash scripts/setup_real_keys.sh

# 3. 选择要配置的供应商,粘贴凭证

# 4. 运行真实 API 集成测试 (需先填 key)
cd backend
pytest -m real_api -v

# 5. 切换到真实模式启动服务
PROVIDER_MODE=real LLM_PROVIDER=openai uvicorn main:app
```

---

## 1. LLM (大语言模型)

### 1.1 OpenAI  — `OPENAI_API_KEY`

**申请 URL**:  https://platform.openai.com/api-keys
**审批时长**:  即时 (邮箱 + 手机号注册)
**绑定信用卡**:  必须 ($5 起充值)
**模型选择**:  gpt-4o / gpt-4o-mini / gpt-4-turbo / o1-preview

| Tier | 消费门槛 | RPM | TPM |
|------|----------|-----|-----|
| Free | $0      | 3   | 200 |
| Tier 1 | 充值 $5 | 60 | 10K |
| Tier 2 | 充值 $50 | 500 | 40K |
| Tier 3 | 充值 $100 | 5K | 80K |
| Tier 4 | 充值 $500 | 10K | 300K |

**价格** (per 1M tokens, 2026-07):
- gpt-4o-mini:  $0.15 / $0.60 (in/out)
- gpt-4o:       $2.50 / $10.00
- o1-preview:   $15 / $60

**测试用例**:  `backend/providers/llm/tests/test_openai_real.py`

### 1.2 Anthropic Claude  — `ANTHROPIC_API_KEY`

**申请 URL**:  https://console.anthropic.com/settings/keys
**审批时长**:  即时
**模型**:  claude-3-5-sonnet / claude-3-5-haiku / claude-3-opus

**价格**:
- claude-3-5-sonnet:  $3 / $15
- claude-3-5-haiku:   $0.80 / $4
- claude-3-opus:      $15 / $75

**Tier 限流**:  Tier 1 (40 美元) = 50 RPM;Tier 2 (400 美元) = 1000 RPM

### 1.3 DeepSeek  — `DEEPSEEK_API_KEY`

**申请 URL**:  https://platform.deepseek.com/api_keys
**审批时长**:  即时 (手机号即可)
**充值**:  1 元起
**模型**:  deepseek-chat (V3) / deepseek-reasoner (R1) / deepseek-coder

**价格** (per 1M tokens, 人民币):
- deepseek-chat:      ¥1 (cache miss) / ¥2 (cache hit)
- deepseek-reasoner:  ¥4 / ¥16
- 限时优惠期持续 (2024-2025 大幅降价,2026 维持)

**限流**:  60 RPM / 1K TPM (免费),充值后大幅放宽

### 1.4 智谱 GLM  — `ZHIPU_API_KEY`

**申请 URL**:  https://bigmodel.cn/console/apikey
**审批时长**:  实名认证后即时 (1 ~ 5 分钟)
**新人福利**:  2000 万 GLM-4-Flash tokens 免费
**模型**:  glm-4-flash / glm-4-air / glm-4-plus / glm-4-long

**价格** (per 1M tokens):
- glm-4-flash:  ¥0.1
- glm-4-air:    ¥0.7
- glm-4-plus:   ¥50

**限流**:  flash 200 RPM;plus 60 RPM

---

## 2. Embedding (文本向量化)

### 2.1 OpenAI text-embedding-3  — 复用 `OPENAI_API_KEY`

**模型**:  text-embedding-3-small (1536 dim) / 3-large (3072 dim)
**价格**:  small $0.02/M;large $0.13/M
**测试**:  `backend/providers/embedding/tests/test_openai_real.py`

### 2.2 智谱 embedding-2  — 复用 `ZHIPU_API_KEY`

**模型**:  embedding-2 (1024 dim)
**价格**:  ¥0.5/M tokens
**测试**:  `backend/providers/embedding/tests/test_zhipu_real.py`

---

## 3. OCR (光学字符识别)

### 3.1 腾讯云 OCR  — `TENCENT_SECRET_ID` / `TENCENT_SECRET_KEY`

**步骤**:
1. 实名认证:  https://console.cloud.tencent.com/developer  (1 工作日)
2. 开通 OCR:  https://console.cloud.tencent.com/ocr
3. 创建 API 密钥:  https://console.cloud.tencent.com/cam/capi
4. 复制 SecretId + SecretKey

**接口**:  GeneralBasicOCR / GeneralAccurateOCR / SealOCR / IDCardOCR
**价格**:  GeneralBasicOCR ¥0.15/次;Accurate ¥0.3/次;新用户 1000 次免费
**限流**:  100 QPS 默认
**测试**:  `backend/providers/ocr/tests/test_tencent_real.py`

### 3.2 百度 OCR  — `BAIDU_OCR_API_KEY` / `BAIDU_OCR_SECRET_KEY`

**步骤**:
1. 注册百度智能云:  https://cloud.baidu.com/
2. 进入文字识别:  https://console.bce.baidu.com/ai/#/ai/ocr/app/list
3. 创建应用 → 选 "文字识别 OCR" → 拿到 API Key + Secret Key

**接口**:  accurate_basic / general_basic / handwriting
**价格**:  ¥0.005/次;千次包 ¥4.5;日免费 1000 次
**限流**:  10 QPS 默认
**测试**:  `backend/providers/ocr/tests/test_baidu_real.py`

---

## 4. STT (语音转文字)

### 4.1 OpenAI Whisper  — 复用 `OPENAI_API_KEY`

**模型**:  whisper-1
**价格**:  $0.006/分钟 (≈ ¥0.04/分钟)
**限制**:  单文件 ≤ 25 MB
**支持语种**:  99 种 (zh/en/ja/ko/ru 等)
**测试**:  `backend/providers/stt/tests/test_whisper_real.py`

**降级链路**:  Whisper 失败 → 自动 fallback 到阿里云一句话识别 (配置 `ALIYUN_*`)

---

## 5. Notify — SendGrid SMTP

### 5.1 SendGrid  — `SMTP_HOST=smtp.sendgrid.net` + `SMTP_PASSWORD=<api_key>`

**步骤**:
1. 注册:  https://signup.sendgrid.com/
2. 创建 API Key:  https://app.sendgrid.com/settings/api_keys  → "Create API Key"
3. 验证发件人:  https://app.sendgrid.com/settings/senders  → 单一发件人或域认证

**配置**:
```
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=<your-api-key>
SMTP_FROM=noreply@yourdomain.com  # 必须已验证
```

**限流**:  免费 100/day;Essentials $20/月 50K;Pro $90/月 100K
**测试**:  `backend/providers/notify/tests/test_sendgrid_real.py`

---

## 6. Lookup — 天眼查

### 6.1 天眼查 OpenAPI  — `TIANYANCHA_API_KEY`

**步骤**:
1. 注册企业账号:  https://www.tianyancha.com/
2. 申请 OpenAPI:  https://open.tianyancha.com/console  → 我的应用 → 创建应用
3. 提交营业执照 → 审核 1-3 工作日
4. 充值 → 拿 api_key (作为 Authorization header)

**接口**:
- `/ic/baseinfo/2.0`  — 企业基本信息 (¥0.05/次)
- `/ic/search/2.0`    — 关键字搜索 (¥0.5/次)
- `/ic/holder/2.0`    — 股东信息 (¥0.3/次)

**套餐**:  试用 ¥200 起 1000 次;标准 ¥2000/年 20000 次
**测试**:  `backend/providers/lookup/tests/test_tianyancha_real.py`

---

## 7. JobMarket — Boss直聘

### 7.1 Boss直聘 OpenAPI  — `JOB_MARKET_BOSS_APP_KEY`

**步骤**:
1. 注册 Boss 企业版:  https://www.zhipin.com/
2. 申请 OpenAPI:  https://www.zhipin.com/api/  → 找客服开通
3. 提供企业资质 → 签合同 → 拿到 AppKey
4. 沙箱测试 → 切换生产

**限制**:
- 仅企业账号
- 沙箱数据有限 (无真实岗位)
- 计费按调用量,通常 ¥5K ~ ¥50K/年

**接口**:  `/job/list` (岗位列表) / `/job/{id}/detail` (详情) / `/job/salary/trend`
**鉴权**:  Header `X-App-Key: <app_key>`

**测试**:  `backend/providers/job_market/tests/test_boss_zhipin_real.py`

---

## 8. Video — Zoom

### 8.1 Zoom Server-to-Server OAuth  — `ZOOM_ACCOUNT_ID` / `ZOOM_CLIENT_ID` / `ZOOM_CLIENT_SECRET`

**步骤**:
1. 注册 Zoom 开发者:  https://marketplace.zoom.us/develop/create
2. 创建 Server-to-Server OAuth 应用
3. 配置 scopes:
   - `meeting:write:meeting:admin` (创建/删除会议)
   - `meeting:read:meeting:admin` (查询)
   - `recording:read:recording:admin` (录制)
   - `user:read:user:admin` (用户信息)
4. 激活应用 → 拿到 Account ID / Client ID / Client Secret
5. Zoom 账号必须有 Pro 许可证 ($15/月起)

**限流**:  Light 100 RPD;Medium 2.5K RPD;Large 7.5K RPD
**接口**:  `POST /users/me/meetings` / `DELETE /meetings/{id}` / `GET /meetings/{id}/recordings`

**测试**:  `backend/providers/video_interview/tests/test_zoom_real.py`

---

## 9. Billing — Stripe

### 9.1 Stripe  — `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET`

**步骤**:
1. 注册:  https://dashboard.stripe.com/register
2. 启用账户 (营业执照 + 银行账号,海外业务)
3. 测试模式拿 key:  https://dashboard.stripe.com/test/apikeys
   - `sk_test_...`  秘密 key
   - `pk_test_...`  公开 key
4. 生产:  https://dashboard.stripe.com/apikeys  → `sk_live_...`
5. 配置 webhook:  https://dashboard.stripe.com/webhooks
   - 监听 `checkout.session.completed` / `invoice.paid` / `customer.subscription.deleted`
   - 拿到 `whsec_...`

**费率**:  2.9% + $0.3/笔 (美国信用卡);无月费
**限流**:  100 RPS 默认;Stripe 自动调整
**支持币种**:  135+

**测试**:  `backend/providers/payment/tests/test_stripe_real.py`

---

## 10. Webhook — 钉钉群机器人

### 10.1 钉钉自定义机器人  — `DINGTALK_WEBHOOK` (+ 可选 `DINGTALK_SECRET`)

**步骤**:
1. PC 钉钉 → 目标群 → 群设置 → 智能群助手
2. 添加机器人 → 自定义
3. **安全设置三选一** (强烈建议全开):
   - 自定义关键词: 消息含 "Waibao"
   - 加签 (HMAC-SHA256): 拿到 secret
   - IP 白名单: 后端出口 IP
4. 复制 webhook URL (含 `access_token=...`)

**限流**:  默认 20 RPM;启用加签后 600 RPM
**配额**:  无月度上限

**测试**:  `backend/providers/notify/tests/test_dingtalk_real.py`

---

## 11. Webhook — 飞书群机器人

### 11.1 飞书自定义机器人  — `FEISHU_WEBHOOK` + `FEISHU_SECRET`

**步骤**:
1. PC 飞书 → 目标群 → 设置 → 群机器人
2. 添加机器人 → 自定义机器人
3. **必须开启签名校验** → 拿到 secret
4. 复制 webhook URL

**限流**:  100 RPM (单机器人);5 条/秒
**配额**:  无月度上限
**消息类型**:  text / post / interactive (消息卡片) / share_chat

**测试**:  `backend/providers/notify/tests/test_feishu_real.py`

---

## 12. Webhook — 企业微信 / 自定义

### 12.1 企业微信群机器人  — `WECOM_WEBHOOK` (备选)

**申请**:  https://work.weixin.qq.com/api/doc/90000/90136/91770
**步骤**:  群 → 群机器人 → 添加 → 复制 webhook
**限流**:  20 RPM/群

### 12.2 自定义 Webhook

```bash
WEBHOOK_URL=https://your-endpoint.com/hook
WEBHOOK_METHOD=POST
WEBHOOK_HEADERS=Authorization: Bearer xxx
```

---

## 13. 切换供应商

修改 `.env` 后,**无需改代码**,重启即可:

```bash
# 切换到 OpenAI
LLM_PROVIDER=openai LLM_DEFAULT_MODEL=gpt-4o-mini uvicorn main:app

# 切换到智谱
LLM_PROVIDER=zhipu LLM_DEFAULT_MODEL=glm-4-flash uvicorn main:app

# 切换到 DeepSeek
LLM_PROVIDER=deepseek LLM_DEFAULT_MODEL=deepseek-chat uvicorn main:app
```

降级链路: 主供应商失败时自动 fallback 到 `LLM_FALLBACK` (默认 `mock`)。

---

## 14. 测试矩阵

| 测试文件 | 触发条件 | 覆盖 |
|----------|----------|------|
| `test_openai_real.py` | `OPENAI_API_KEY` | gpt-4o-mini chat + streaming + tool_use |
| `test_anthropic_real.py` | `ANTHROPIC_API_KEY` | claude-3-5-sonnet chat + tool_use |
| `test_deepseek_real.py` | `DEEPSEEK_API_KEY` | deepseek-chat + reasoner |
| `test_zhipu_real.py` | `ZHIPU_API_KEY` | glm-4-flash + glm-4-plus |
| `test_openai_embedding_real.py` | `OPENAI_API_KEY` | text-embedding-3-small/large |
| `test_zhipu_embedding_real.py` | `ZHIPU_API_KEY` | embedding-2 |
| `test_tencent_real.py` | `TENCENT_SECRET_ID+KEY` | GeneralBasicOCR |
| `test_baidu_real.py` | `BAIDU_OCR_*` | accurate_basic |
| `test_whisper_real.py` | `OPENAI_API_KEY` | whisper-1 多语种 |
| `test_sendgrid_real.py` | `SMTP_PASSWORD` | smtp.sendgrid.net 邮件 |
| `test_tianyancha_real.py` | `TIANYANCHA_API_KEY` | 企业基本信息查询 |
| `test_boss_zhipin_real.py` | `JOB_MARKET_BOSS_APP_KEY` | 真实岗位检索 |
| `test_zoom_real.py` | `ZOOM_*` (3 个) | Server-to-Server OAuth + 创建会议 |
| `test_stripe_real.py` | `STRIPE_SECRET_KEY` | checkout.session.create |
| `test_dingtalk_real.py` | `DINGTALK_WEBHOOK` | 文本 + markdown + 加签 |
| `test_feishu_real.py` | `FEISHU_WEBHOOK+SECRET` | 交互式卡片 + 签名 |

**运行方式**:
```bash
cd talent-tool-mvp/backend

# 单个供应商
pytest -m real_api providers/llm/tests/test_openai_real.py -v

# 全部 (需所有 key)
pytest -m real_api -v

# 跳过 expensive 的
pytest -m "real_api and not slow" -v
```

---

## 15. 安全 & 成本控制

### 15.1 .env 不入库
```
backend/.env                  # git ignored
backend/config/.env.example   # committed (模板)
```

### 15.2 预算熔断
```bash
DAILY_BUDGET_USD=50               # 单租户默认
TENANT_DAILY_BUDGET_USD_acme=200  # 特定租户
```

超出后自动 fallback 到 mock + 触发告警 (`PROMETHEUS_ENABLED=true`)。

### 15.3 key 轮换
```bash
# 旧 key 设过期 → 监控无 401 → 切到新 key
# 详细 SOP: docs/KEY_ROTATION_SOP.md (待写)
```

### 15.4 最小成本跑通
| 供应商 | 充值额度 | 测试用量 |
|--------|----------|----------|
| OpenAI | $5 | ~ 50 次 gpt-4o-mini |
| Anthropic | $5 | ~ 100 次 haiku |
| DeepSeek | ¥1 | ~ 1000 次 deepseek-chat |
| 智谱 | ¥0 | 新人 2000 万 tokens 够用 |

合计 **¥30 内** 可完成 16 个真实 API 集成测试。

---

## 16. 常见问题

**Q: key 申请多久能用?**
A: 即时类 (OpenAI / Anthropic / DeepSeek / SendGrid) 邮箱注册即可;腾讯云/百度 OCR 实名 1 工作日;Boss 直聘需企业资质 1-3 天。

**Q: 如何调试 webhook?**
A: 钉钉/飞书都提供"测试消息"功能,先用真实 webhook URL 接收一条 hello,再切到 SDK 调用。

**Q: 真实 key 跑测试会扣费吗?**
A: 会。CI 默认 skip,本地手动 `pytest -m real_api` 时按用量计费。建议使用 `ENABLE_REAL_API_TESTS=false` 默认关闭。

**Q: 测试失败如何定位?**
A: 设 `LOG_LEVEL=DEBUG` 看完整请求/响应;providers/* 都有 `with_resilience` 包装,会自动打印错误原因。

**Q: 如何贡献新供应商?**
A: 参考 `backend/providers/registry.py`,实现 `LLMProvider` 接口 + 注册到 registry + 写 test_real_*.py。

---

> 文档版本:  v4.0 (2026-07)
> 维护者:  Waibao Platform Team
> 反馈:    Slack #waibao-platform
