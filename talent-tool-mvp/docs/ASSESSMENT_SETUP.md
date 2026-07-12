# ASSESSMENT_SETUP — 北森 (Beisen) 测评 真实接入 (T1805)

> 适用: v3.0+. 国内主流选择: 北森; 海外后续考虑 HackerRank / Codility.

测评 provider 配置: `ASSESSMENT_PROVIDER=beisen|mock`

缺省 `mock` 时系统使用业务 mock provider; 不会触发外部调用.

---

## 1. 申请步骤

1. 申请 [北森开放平台](https://open.beisen.com) 企业开发者账号
2. 进入 **控制台 → 我的应用 → 创建应用**
3. 选择应用类型: **HR SaaS / 测评**
4. 拿到:
   - AppId → `BEISEN_APP_ID`
   - AppSecret → `BEISEN_APP_SECRET`
5. 在 **企业配置** 关联租户: `BEISEN_TENANT_ID`
6. 在 **能力配置** 启用: 测评调用 + 报告查询
7. (可选) 配置 OAuth2 redirect URI 用于 agent 回调: `BEISEN_REDIRECT_URI`

### 1.1 测评 ID 准备

在 [北森一体化人才测评云](https://exam.beisen.com/) 创建一份测评,
记录其 assessmentId, 用于测试 / 生产调用:

```bash
export BEISEN_ASSESSMENT_ID="asm_xxxxxx"
```

---

## 2. 环境变量

```bash
export ASSESSMENT_PROVIDER=beisen
export BEISEN_APP_ID="..."
export BEISEN_APP_SECRET="..."
export BEISEN_TENANT_ID="..."
# 可选: 自托管网关
export BEISEN_BASE_URL="https://open.beisen.com"
# 可选: OAuth2 redirect (agent 场景)
export BEISEN_REDIRECT_URI="https://your-app/api/agents/callback/beisen"
```

---

## 3. 调用流程

### 3.1 OAuth 流程

```
provider._get_token()
  ↓ POST /v1/interfaces/oauth2/token
  body: { appId, appSecret, tenantId, grantType: "client_credentials" }
  ↓ accessToken (默认 2h 有效)
cache: provider._token + _token_expires_at
  ↓ reuse within TTL
```

### 3.2 邀请候选人测评

```python
inv = await provider.send_invitation(
    candidate_id="cand_001",
    assessment_id="asm_xxxxxx",
    candidate_email="alice@example.com",
    candidate_name="Alice",
    expires_in_hours=48,           # 邀请有效期
    metadata={"role_id": "role_001", "step": "2"},
)
# inv.invite_url  → 给候选人点击的测评链接
# inv.invitation_id → 拉结果用
```

### 3.3 拉结果 (轮询)

```python
result = await provider.get_results(inv.invitation_id)
# result.status ∈ { pending, submitted, scored, expired }
# result.overall_score → 0-100
# result.percentile → 0-100
# result.scores → 各维度 Score 对象
```

业务上建议:
- **短轮询**: 候选人点击后用 60s interval + 30min timeout
- **Webhook**: 北森支持调用方配置回调 URL; v3.2 升级项
- **Worker/Cron**: 每 5 分钟扫一次 `pending` 邀请

---

## 4. 测评分数 → 匹配权重

匹配打分 `matching/scorer.py` 已经接好:

```python
WEIGHT_ASSESSMENT = 0.15   # T1306 / T1805
```

当 `candidates.assessment_score` 有值时, 总分重新按以下权重归一:

| 因子 | 无 assessment | 有 assessment |
| ---- | ---- | ---- |
| 技能重合 | 0.40 | 0.40 × 0.85 = 0.34 |
| 语义相似 | 0.35 | 0.35 × 0.85 = 0.2975 |
| 经验拟合 | 0.25 | 0.25 × 0.85 = 0.2125 |
| 测评分数 |  0   | **0.15** |
| 总和 | 1.00 | 1.00 |

这个归一保证总分不会有 5% 的整体偏移, 不会改变相对排名的大盘.

---

## 5. 集成测试

```bash
export BEISEN_APP_ID=...
export BEISEN_APP_SECRET=...
export BEISEN_TENANT_ID=...
export BEISEN_ASSESSMENT_ID=asm_xxxxxx
pytest -m real_api backend/providers/assessment/tests/test_beisen_real.py -v
```

覆盖:
- 凭证注入
- OAuth2 token 获取 + 缓存
- **真实邀请 + 拿到 invite_url**
- **邀请后立刻拉结果 (pending 或 scored)**
- 未知 invitation_id 不抛异常 → 返回 pending placeholder
- Token 401 自动刷新

---

## 6. 一次性集成 demo

```bash
python scripts/full_hire_workflow.py \
  --assessment-provider beisen \
  --candidate-email alice@example.com
```

会打印:
1. 邀请 ID + 邀请 URL
2. 测评结果 (轮询 3 次, 6 秒)
3. **重算 match score**: 接入测评后总分变化 + 测评权重 0.15

---

## 7. 业务侧集成

| 接入点 | 说明 |
| --- | --- |
| `services/assessment_service.py` | 上层业务封装,负责落库 + 写入 `candidates.assessment_score` |
| `matching/engine.py` | 读取 `candidates.assessment_score` 传入 scorer |
| `hr_service_agent.py` | 推荐: 候选人投递后 24h 内自动发起测评 (T1801 任务范畴) |

---

## 8. FAQ

**Q: `errorCode=30001 / 应用未授权`**
A: 在北森控制台 → 我的应用 → 关联企业 (租户) → 启用能力.

**Q: `errorCode=40004 / AssessmentId invalid`**
A: 测评 ID 要从北森一体化测评云控制台 → 测评管理获取, 不是开放平台创建.

**Q: 测评分数在 75 分以上但 confidence 还是 possible?**
A: confidence 跟 overall_score (= 测评 + 三因子 加权) 挂钩, 不是单看测评分.

**Q: 候选人未开始时拉结果是报错?**
A: v3.0 优化后, 业务未开始时返回 `status=pending` placeholder 不抛异常. 业务用轮询.

---

## 9. 相关任务

- T1306 — Assessment Provider 抽象层 (beisen / mock)
- T1306 — 测评分数进 matching (0.15 权重)
- T1805 (本文档) — 真实邀请 + 拉结果验证
