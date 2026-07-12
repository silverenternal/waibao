# 第三方 Provider 真实 API 集成测试流程 (T1101/T1102/T1103)

> 本文档说明如何对 waibao v4.0 的所有第三方 Provider 跑 **真实 API 集成测试**。所有真实测试默认 skip,只在设置了对应 env 变量后才会执行 — 保证 CI / 默认 `pytest` 永远不会因真实凭证缺失而失败。

## 1. 测试分层

| 层级 | 标记 | 触发条件 | 覆盖 |
| --- | --- | --- | --- |
| 单元测试 | (无) | 默认运行 | mock / protocol / 数据契约 |
| 集成测试(httpx mock) | (无) | 默认运行 | retry / rate-limit / auth-fail 分支 |
| **真实 API 测试** | `@pytest.mark.real_api` | 需要真实 env 变量 | 真实 HTTP 端到端 + 字段映射 + 缓存 |

## 2. 全部真实测试文件清单

```
backend/providers/job_market/tests/
├── test_boss_zhipin_real.py        # Boss直聘 OpenAPI
├── test_lagou_real.py              # 拉勾 OAuth2 + OpenAPI
└── test_adzuna_real.py             # Adzuna 全球职位聚合

backend/providers/stt/tests/
└── test_whisper_real.py            # OpenAI Whisper + aliyun_stt fallback

backend/providers/notify/tests/
├── test_dingtalk_real.py           # 钉钉群机器人 webhook
└── test_feishu_real.py             # 飞书群机器人 webhook
```

每个 `*_real.py` 文件顶部都有:

```python
pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(not os.getenv("XYZ_API_KEY"), reason="..."),
]
```

未设置 env 变量 → 整个文件被 skip,不影响其他测试。

## 3. 申请凭证

详细申请步骤见各专项文档:
- [REAL_API_SETUP.md](REAL_API_SETUP.md) — Boss直聘 / 拉勾 / Adzuna
- [WHISPER_INTEGRATION.md](WHISPER_INTEGRATION.md) — OpenAI Whisper
- [WEBHOOK_INTEGRATION.md](WEBHOOK_INTEGRATION.md) — 钉钉 / 飞书

## 4. 执行步骤

### 4.1 单独运行真实测试

```bash
# 全部 real_api 标记
cd backend
pytest -m real_api -v

# 单一 provider
pytest -m real_api providers/job_market/tests/test_boss_zhipin_real.py -v
```

### 4.2 配置 env

```bash
# 方式 1: 直接 export
export JOB_MARKET_BOSS_APP_KEY="..."
export JOB_MARKET_LAGOU_CLIENT_ID="..."
export JOB_MARKET_LAGOU_CLIENT_SECRET="..."
export JOB_MARKET_ADZUNA_APP_ID="..."
export JOB_MARKET_ADZUNA_APP_KEY="..."
export OPENAI_API_KEY="sk-..."
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=..."
export DINGTALK_SECRET="SEC..."
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/..."
export FEISHU_SECRET="..."

# 方式 2: env 文件(更安全)
cp backend/providers/config.example.env backend/.env.real
# 编辑填入真实凭证
set -a; source backend/.env.real; set +a
pytest -m real_api -v
```

### 4.3 完整 CI 流水线示例

```yaml
# .github/workflows/real-api-tests.yml
name: Real API Integration Tests
on:
  workflow_dispatch:  # 手动触发, 避免 CI 烧配额
jobs:
  real-api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r backend/requirements.txt
      - name: Run real_api tests
        env:
          JOB_MARKET_BOSS_APP_KEY: ${{ secrets.BOSS_APP_KEY }}
          JOB_MARKET_LAGOU_CLIENT_ID: ${{ secrets.LAGOU_CLIENT_ID }}
          JOB_MARKET_LAGOU_CLIENT_SECRET: ${{ secrets.LAGOU_CLIENT_SECRET }}
          JOB_MARKET_ADZUNA_APP_ID: ${{ secrets.ADZUNA_APP_ID }}
          JOB_MARKET_ADZUNA_APP_KEY: ${{ secrets.ADZUNA_APP_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          DINGTALK_WEBHOOK: ${{ secrets.DINGTALK_WEBHOOK }}
          DINGTALK_SECRET: ${{ secrets.DINGTALK_SECRET }}
          FEISHU_WEBHOOK: ${{ secrets.FEISHU_WEBHOOK }}
          FEISHU_SECRET: ${{ secrets.FEISHU_SECRET }}
        run: |
          cd backend
          pytest -m real_api -v --tb=short
```

## 5. 验证清单

每个 `*_real.py` 都覆盖以下维度,可在 PR 模板里勾选:

- [ ] **搜索/转写/推送主路径** — 真实 HTTP 调用至少 1 次成功
- [ ] **字段映射** — 验证返回数据能被解析为标准 dataclass (JobPosting / STTResult / NotifyResult)
- [ ] **缓存命中** — 同 keyword 二次调用应快于首次 (命中率指标)
- [ ] **签名校验** — 钉钉 / 飞书应正确生成 HMAC-SHA256 + base64
- [ ] **重试链路** — 5xx 应触发 with_resilience 中间件 ≥ 2 次重试
- [ ] **fallback 兜底** — 缺失凭证时,provider 自动回退到 mock,不抛错
- [ ] **凭证校验** — 缺失关键 env 时构造抛 InvalidRequestError

## 6. 配额与限流

| Provider | 免费层 | 默认限流 | retry 策略 |
| --- | --- | --- | --- |
| Boss直聘 | 仅企业账号,无免费 | 5 req/s | max_retries=2 |
| 拉勾 | 仅企业账号 | 5 req/s | max_retries=2 |
| Adzuna | 250 calls/month | 2 req/s | max_retries=2 |
| OpenAI Whisper | 按 token 计费 | 5 req/s (Tier 1) | max_retries=2 |
| 钉钉 webhook | 6000/min/群 | 10 req/s | max_retries=2 |
| 飞书 webhook | 100/min/群 | 10 req/s | max_retries=2 |

**重要**: `real_api` 测试应只在本地或 weekly CI 跑,避免浪费配额。

## 7. 故障排查

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| `SKIPPED [1] DINGTALK_WEBHOOK 未设置` | env 变量缺失 | export 后重跑 |
| `AuthError: 401` | API key 失效 | 检查 `providers/config.example.env` 重新生成 |
| `QuotaExceededError: 402` | 配额耗尽 | 切换 mock,或换账号 |
| 测试用例均 `passed but slow` | DNS / TLS 阻塞 | 增加 `httpx.Timeout(timeout=15.0)` |
| 缓存命中断言失败 | 缓存被 monkeypatch 清空 | 不要在 `real_api` 测试里 `monkeypatch.setattr(p, "_cache", ...)` |