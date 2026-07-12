# VIDEO_INTERVIEW_SETUP — Zoom / 腾讯会议 真实接入 (T1805)

> 适用: v3.0 起, v3.1+ 推荐优先走 Zoom S2S OAuth; 中国大陆团队可切换腾讯会议.

视频面试 provider 配置: `VIDEO_PROVIDER=zoom|tencent_meeting|mock`

缺省 `mock` 时系统使用业务 mock provider (返回模拟 join_url), 不会触发任何外部调用.

---

## 1. Zoom Server-to-Server OAuth

### 1.1 申请步骤

1. 登录 [Zoom App Marketplace](https://marketplace.zoom.us/)
2. 选择 **Develop → Build App → Server-to-Server OAuth**
3. 填好基本信息, 在 **Scopes** 至少勾选:
   - `meeting:write:meeting:admin` (创建/编辑会议)
   - `meeting:read:meeting:admin` (查询会议)
   - `meeting:read:list_meetings:admin` (列出历史会议)
   - `recording:read:recording:admin` (录制,可选)
4. 在 **Activation** 页记录:
   - Account ID → `ZOOM_ACCOUNT_ID`
   - Client ID → `ZOOM_CLIENT_ID`
   - Client Secret → `ZOOM_CLIENT_SECRET`
5. 把账号 (master account 或拥有会议权限的 user) 加入连接的应用.

### 1.2 环境变量

```bash
export VIDEO_PROVIDER=zoom
export ZOOM_ACCOUNT_ID="..."
export ZOOM_CLIENT_ID="..."
export ZOOM_CLIENT_SECRET="..."
# 可选: 主机的 Zoom user id (默认 "me")
export ZOOM_HOST_USER_ID="me"
# 可选: 走测试桩
export ZOOM_API_BASE="https://api.zoom.us/v2"
```

`config.example.env` 已包含这些变量名, 复制到 `.env` 后填写即可.

### 1.3 OAuth2 流程 (代码侧已封装)

```
provider._get_token()
  ↓ grant_type=account_credentials + Basic auth(client_id:secret)
POST https://zoom.us/oauth/token
  ↓ access_token (1h)
cache: provider._token + provider._token_expires_at
  ↓ reuse within TTL (refresh 60s before expiry)
后续 Bearer token 调用 /v2/users/me/meetings
  ↓ 401 → 自动 refresh once
```

### 1.4 Panel Round (5 个会议)

```python
provider = ZoomProvider()
start = datetime.now(tz=timezone.utc) + timedelta(hours=4)
meetings = await provider.create_panel_round(
    candidate_id="alice@example.com",
    topic="Senior 后端面试",
    panelist_emails=[
        "tech_lead@example.com",
        "behaviour@example.com",
        "case@example.com",
        "system_design@example.com",
        "cto@example.com",
    ],
    start_time=start,
    duration_min=45,
    rounds=5,                       # T1805: 默认 5 轮
    host_email="hr@waibao.com",
)
# 每个会议独立 meeting_id; 错开 30 分钟; 全部 5 个一次性到位
```

### 1.5 集成测试

```bash
export ZOOM_ACCOUNT_ID=...
export ZOOM_CLIENT_ID=...
export ZOOM_CLIENT_SECRET=...
pytest -m real_api backend/providers/video_interview/tests/test_zoom_real.py -v
```

覆盖:
- 凭证注入
- OAuth token 获取 + 缓存复用
- 单会议创建 + 清理
- **Panel round — 5 个会议 + 时间错开校验**
- Token 401 自动刷新
- 录制查询 (未开始 → processing)

---

## 2. 腾讯会议 (Tencent Meeting) client_credentials

### 2.1 申请步骤

1. 注册 [腾讯会议开放平台](https://cloud.tencent.com/product/tem) 企业账号
2. 创建应用 → **REST API 应用**
3. 在 **我的应用 → 能力配置** 勾选:
   - `MEETING_MANAGE` (会议管理)
   - `MEETING_READ` (会议查询)
4. 拿到:
   - AppId (SdkId) → `TENCENT_MEETING_APP_ID`
   - AppSecret → `TENCENT_MEETING_APP_SECRET`
   - 应用管理员 userid → `TENCENT_MEETING_USERID`

### 2.2 环境变量

```bash
export VIDEO_PROVIDER=tencent_meeting
export TENCENT_MEETING_APP_ID="..."
export TENCENT_MEETING_APP_SECRET="..."
export TENCENT_MEETING_USERID="admin_userid"
# 国内 SaaS 默认
export TENCENT_MEETING_BASE_URL="https://api.meeting.qq.com"
```

### 2.3 Panel Round (3 个会议)

```python
provider = TencentMeetingProvider()
meetings = await provider.create_panel_round(
    candidate_id="alice@example.com",
    topic="Senior 后端面试",
    panelist_userids=[
        "tech_lead_uid",
        "hr_partner_uid",
        "cto_uid",
    ],
    start_time=start,
    duration_min=45,
    rounds=3,            # T1805: 国内常用 3 轮 (技术 + HR + 总监)
)
```

### 2.4 集成测试

```bash
export TENCENT_MEETING_APP_ID=...
export TENCENT_MEETING_APP_SECRET=...
pytest -m real_api backend/providers/video_interview/tests/test_tencent_meeting_real.py -v
```

---

## 3. 容错 / 回退

`providers/video_interview/registry.py` 中的 fallback 顺序:

```
configured provider == OK   →  真实 Zoom / TM
configured provider 缺凭证  →  InvalidRequestError → 自动 fallback mock
真实 provider 上游报错       →  with_resilience 重试 → 超时后上层 catch → fallback mock
```

业务侧可以信赖: 即使真实供应商宕机, 流程不会崩, 只是返回的数据是 mock 行为.

---

## 4. 一次性集成 demo

```bash
python scripts/full_hire_workflow.py \
  --video-provider zoom \
  --candidate-email alice@example.com
```

会创建 5 个会议 + 打印每个 join_url + 密码.

---

## 5. 常见问题 (FAQ)

**Q: `error 401: invalid client_id or client_secret`**
A: 检查 `ZOOM_CLIENT_ID/ZOOM_CLIENT_SECRET`; 注意不要把 Client ID 复制到 Secret.

**Q: `User not found / me`**
A: 默认 `ZOOM_HOST_USER_ID=me`, 即用 master account. 创建会议时报 user not found,
说明应用没有挂载到该账号. 在 marketplace 应用管理 → 重新授权账号.

**Q: 腾讯会议 `error_code=14 / appid invalid`**
A: `TENCENT_MEETING_APP_ID` 不正确. 注意腾讯有 `SdkId` 与 `AppId` 两个概念, oauth 接口用 `SdkId`.

**Q: 想用本地测试桩**
A: 把 `ZOOM_API_BASE` 改成 ngrok 指向本地 mock, 或继续用 `VIDEO_PROVIDER=mock`.

**Q: 5 个会议能否批量取消?**
A: 业务侧需要保留 `meeting_id` 列表, 调用 `provider.cancel_meeting(meeting_id)` 逐个取消.

---

## 6. 相关任务

- T1305 — VideoInterview Provider 抽象层 (zoom / tencent_meeting / mock)
- T1701 — 真实 API 接入 & 12+ 测试
- T1805 (本文档) — Panel round + Zoom OAuth + 5 个会议真实化
