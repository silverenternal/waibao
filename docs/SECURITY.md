# Security Policy (T1005)

> **v10.0 update (T5014–T5019):** security fail-fast startup, PII/KMS encryption hardening, three-jurisdiction privacy (GDPR/PIPL/CCPA), three-tier rate limiting + Webhook SSRF + CSRF defences, LLM prompt-injection governance, SSO/JIT governance, and container/CI hardening + dependency lock. See [COMPLIANCE.md](COMPLIANCE.md) for the privacy mapping and [SOC2_EVIDENCE.md](SOC2_EVIDENCE.md) for the control-to-implementation trace.

## Threat Model

Waibao 是一款 B2B SaaS 招聘平台,涉及大量候选人 PII (姓名/邮箱/电话/简历)。
主要威胁类别:

| 威胁 | 风险等级 | 已实施防护 |
|------|---------|----------|
| SQL 注入 | 高 | Supabase PostgREST 强制参数化查询;所有 Supabase 调用走 `.eq()/.select()` SDK;无字符串拼接 SQL |
| XSS | 中 | 前端 React 默认转义;Markdown 输出走白名单渲染;`Content-Security-Policy` 由 Next.js 默认提供 |
| SSRF | 中 | 所有 provider 调用走白名单 host (`providers/base.py` + registry 配置);非白名单 host 拒绝连接 |
| 路径遍历 | 中 | 文件下载路径由服务端 UUID 索引,不接受用户传入路径;`/api/uploads` 校验 MIME + size |
| 暴力破解 | 高 | JWT 由 Supabase 颁发 (HS256, 服务端校验);登录失败有 rate limit;API key 走 SHA-256 hash 比对 |
| 数据泄露 | 高 | RLS (行级安全) 默认所有 PII 表开启;字段级加密 (AES-GCM 256) 在 `services/crypto.py` |
| 越权访问 | 高 | admin / talent_partner / client 三层 RBAC;`require_role()` 装饰器;RLS 双保险 |
| 中间人 | 中 | 全站 HTTPS (由反向代理终结);JWT 不放 URL;Cookie 走 SameSite=Lax |
| 拒绝服务 | 中 | token bucket (provider 维度);circuit breaker;`/metrics` 端点只允许内网 |
| 密钥泄露 | 中 | detect-secrets CI 扫描;`.env` 在 `.gitignore`;Secrets 走 GitHub Actions secrets |

## 已实施防护

### 1. RLS (Row Level Security)
- 所有 PII 表 (candidates / roles / journal / tickets / messages) 均 `enable row level security`
- `auth.uid()` + `auth.role()` 双重判定
- Admin 角色可读全部;client 只能读自己 organisation 关联数据

### 2. 字段级加密 (Encryption at Rest)
- `services/crypto.py`: AES-GCM 256-bit
- PII 字段 (email / phone / national_insurance_number) 在写入前加密
- 密钥来自 `ENCRYPTION_KEY` 环境变量 (KMS / Doppler 注入)

### 3. 限流 (Rate Limiting)
- `providers/base.py` `TokenBucket`: provider 维度默认 10 req/s,burst 20
- `circuit breaker`: 5 次失败开 60s
- retry: 指数退避,3 次

### 4. GDPR / 个保法
- `GET /api/gdpr/export`: 数据可携权
- `DELETE /api/gdpr/all-data`: 被遗忘权 (服务端 `forget_user` RPC)
- `GET /api/gdpr/privacy`: 隐私政策
- 数据保留 730 天,到期自动归档 (后台 job)

### 5. 审计 (Audit Log)
- `audit_log` 表 append-only
- 所有 PII 访问通过 `@audit` 装饰器自动记录
- 仅 admin 可读 (`/api/admin/audit`)
- CSV 导出供监管报送

### 6. 可观测性 + 告警
- OpenTelemetry 全链路追踪 (T1001)
- Prometheus 指标 + Grafana (T1002)
- Sentry 错误追踪 + trace_id 关联 (T1003)

### 7. SAST + 依赖扫描
- Bandit (Python SAST) — CI 高危 0 / 中危需 review
- Safety (依赖漏洞) — 每 PR 检查
- pnpm audit (前端依赖)
- detect-secrets (密钥扫描)
- sqlmap (可选集成测试)

## 已知风险 (Known Risks)

| 风险 | 说明 | 缓解 |
|------|------|------|
| OpenAI / Anthropic API 凭证外泄 | 模型调用走 env var | 密钥每月轮换;detect-secrets CI |
| 上传文件大小 DoS | 简历 PDF 可能很大 | 单文件 10MB 上限;走异步 OCR |
| 第三方 webhook 重放 | 缺少 idempotency-key | webhook payload 加 nonce + 时间戳校验 |
| Admin 误操作 | admin 权限过大 | admin 操作需 MFA (v3.1 待办) |
| LLM 提示注入 | 用户输入可能含 prompt injection | 关键决策走 `out_of_band` 校验;LLM 输出不直接执行 |

## 报告漏洞 (Responsible Disclosure)

请通过以下渠道负责任地披露:

- **Email**: security@waibao.example
- **PGP key**: 见 https://waibao.example/.well-known/security.txt
- **响应 SLA**: 24h 内确认,72h 内评估,90d 内修复

我们承诺:
- 不会对善意研究者采取法律行动
- 漏洞修复后署名致谢 (除非要求匿名)
- 公开致谢列表: https://waibao.example/security/credits

## Compliance

- **GDPR** (欧盟通用数据保护条例): ✅ 已合规 (Art. 15/17/20/30/33, T5016)
- **PIPL** (个人信息保护法): ✅ 已合规 (跨境声明 + 敏感信息单独同意, T5016)
- **CCPA / CPRA** (加州): ✅ 已合规 (Do-Not-Sell/Share + GPC, T5016)
- **SOC 2 Type II**: 进行中 — v10.0 证据矩阵就绪 (`SOC2_EVIDENCE.md`, 56 controls, T5019)
- **ISO 27001**: 路线图

> v10.0 完整隐私映射见 [COMPLIANCE.md](COMPLIANCE.md)。

## v10.0 新增安全控制 (T5014–T5019)

| 控制 | 任务 | 说明 |
|---|---|---|
| Fail-fast 启动 | T5014 | 密钥缺失 / 配置错误时启动即终止,不静默降级 |
| PII 字段加密 + KMS | T5015 | email/phone/身份号 AES-GCM 加密;密钥走 KMS/Doppler |
| 三级 Rate Limit | T5017 | 全局 / 租户 / 用户三层限流;Webhook SSRF 防护;CSRF 双提交 Cookie |
| LLM Prompt Injection | T5018 | 输入消毒 + out-of-band 校验;Agent Gateway 守卫 |
| SSO / JIT 治理 | T5018 | SAML/OIDC Just-In-Time 账户供给受控 |
| 容器 / CI 加固 | T5019 | 最小权限镜像;依赖锁定 (`requirements.txt` lock);detect-secrets CI |
| SOC2 证据 | T5019 | 5 大 TSC 族 × 56 控制矩阵,审计可在 2 分钟内追溯 |