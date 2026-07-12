# LiveKit 自托管设置 (T2204)

本指南说明如何在本地 / 单机 / 生产环境部署自托管 LiveKit SFU,集成到 RecruitTech 平台.

---

## 1. 快速开始 (本地开发)

### 1.1 启动 LiveKit

```bash
cd talent-tool-mvp
docker compose -f infra/livekit/docker-compose.yml up -d
```

启动后会有两个容器:

| 容器                | 端口                  | 用途               |
| ------------------- | --------------------- | ------------------ |
| `livekit-server`    | 7880 (HTTP/WS)        | 信令 + HTTP API    |
| `livekit-server`    | 7881/UDP              | RTC (媒体流)       |
| `livekit-server`    | 7882 (TLS)            | TLS (生产)         |
| `livekit-redis`     | (内部)                | 内部状态 (多节点)  |

### 1.2 验证

```bash
# 健康检查
curl http://localhost:7880/
# → 200 OK with service info

# 看录制目录
docker exec livekit-server ls /recordings
```

### 1.3 配置 backend

`backend/.env`:

```bash
VIDEO_PROVIDER=livekit
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_HTTP_URL=http://localhost:7880
LIVEKIT_API_KEY=APIwXkjY8N7qGRtVzmHp9DTr4cKLbn
LIVEKIT_API_SECRET=secret_2jKp7QvRmH4N8cLsW3yF6tB9xZ1aE5uD
LIVEKIT_RECORDINGS_DIR=/recordings
```

### 1.4 测试

```bash
cd backend
python -m pytest tests/test_livekit.py -v
# 27 passed, 1 skipped

# 真实 LiveKit 集成测试 (需要 LiveKit 运行)
LIVEKIT_RUN_INTEGRATION=1 python -m pytest tests/test_livekit.py::TestLiveKitIntegration -v
```

---

## 2. API

所有 API 都挂在 `/api/livekit` 前缀下:

| 方法   | 路径                          | 说明                              |
| ------ | ----------------------------- | --------------------------------- |
| POST   | `/api/livekit/rooms`          | 创建房间 (host 模式)              |
| POST   | `/api/livekit/token`          | 为参与者签发 token                |
| GET    | `/api/livekit/rooms/{name}`   | 查询房间元数据                    |
| GET    | `/api/livekit/recordings/{room_id}` | 查询房间录制               |
| POST   | `/api/livekit/webhook`        | LiveKit → backend 事件回调 (免登录) |

### 创建房间

```bash
curl -X POST http://localhost:8000/api/livekit/rooms \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "AI Interview - Backend",
    "duration_min": 45,
    "participants": [{"email": "alice@example.com", "role": "attendee"}]
  }'
```

返回:

```json
{
  "room_name": "int_1700000000_abc12345",
  "livekit_url": "ws://localhost:7880",
  "host_token": "eyJhbGc...",
  "host_url": "ws://localhost:7880/host?...",
  "join_url": "ws://localhost:7880/join?...",
  "expires_at": 1700003600
}
```

### 签发 token

```bash
curl -X POST http://localhost:8000/api/livekit/token \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "room_name": "int_xxx",
    "identity": "bob",
    "ttl_seconds": 1800
  }'
```

---

## 3. 前端集成

### 安装

```bash
cd frontend
npm install livekit-client @livekit/components-react @livekit/components-styles
```

### 使用

```tsx
import LiveKitRoom from "@/components/livekit/Room";

<LiveKitRoom
  roomName={startResp.livekit.room_name}
  identity={userEmail}
  authToken={sbToken}
  onLeave={() => router.back()}
/>
```

### 改造 AI 面试 UI

原 mock 视频替换为:

```tsx
import LiveKitVideoStage from "@/components/interview/LiveKitVideoStage";

<LiveKitVideoStage
  interviewId={interviewId}
  livekit={startResp.livekit}  // start interview 接口已包含
  onLeave={() => router.push("/dashboard")}
/>
```

---

## 4. Webhook 事件

LiveKit 会向 `POST /api/livekit/webhook` 推送以下事件 (Header `Authorization: Bearer <server_token>`):

| 事件                  | 触发条件                        | 业务影响                  |
| --------------------- | ------------------------------- | ------------------------- |
| `room_started`        | 第一个参与者加入                 | 记录房间开始              |
| `room_finished`       | 所有参与者离开                   | 清理资源                  |
| `participant_joined`  | 参与者加入                       | 推送 `video.participant_joined` |
| `participant_left`    | 参与者离开                       | 推送 `video.participant_left`   |
| `track_published`     | 音视频 track 发布                | (占位)                    |
| `track_unpublished`   | track 取消发布                   | (占位)                    |
| `recording_finished`  | 录制完成                         | 触发转写 + 评分           |
| `egress_finished`     | egress 任务结束                  | 清理                      |

Webhook 由 LiveKit JWT 校验 (LIVEKIT_API_KEY + SECRET),backend 在 `verify_webhook()` 中严格校验,失败返回 401.

---

## 5. 生产部署清单

### 5.1 必备配置

- [x] 替换 dev API key/secret 为强随机 (32 字节 hex)
- [x] 通过 secrets manager 注入 (不要写进 git)
- [x] 启用 TLS (`LIVEKIT_TURN_TLS_PORT=5349` + nginx/caddy 反代)
- [x] 配置录制存储到 S3 / GCS (而不是本地磁盘)

### 5.2 可选优化

- [ ] 多节点 Redis (多 SFU 节点时必需,本 compose 已包含)
- [ ] Ingress controller: 使用 LiveKit Cloud 中继 (跨区域)
- [ ] 录制 + 转写: 启用 egress + S3,接 `video.recording_finished` webhook 触发转写
- [ ] 监控: Prometheus exporter (LiveKit 暴露 `:6789/metrics`)

### 5.3 录制 → S3

```yaml
# infra/livekit/livekit.yaml
egress:
  enabled: true
  s3:
    bucket: "recruittech-livekit-recordings"
    region: "us-west-2"
    access_key: "${AWS_ACCESS_KEY_ID}"
    secret_key: "${AWS_SECRET_ACCESS_KEY}"
```

---

## 6. 故障排查

| 问题                              | 解决                                              |
| --------------------------------- | ------------------------------------------------- |
| `livekit-server` 启动失败         | 检查 `LIVEKIT_API_KEY` 是否包含非法字符 (e.g. 空格) |
| 客户端连接 1006                   | 检查 7881/UDP 是否开放 (NAT 穿透)                 |
| Webhook 401                       | 检查 Authorization 头是否以 `Bearer ` 开头         |
| Token 签发失败                    | 检查 `LIVEKIT_API_KEY/SECRET` env                 |
| 录制找不到                        | 检查 `egress.enabled=true` 且 S3 配置正确         |

---

## 7. 与现有系统的关系

```
           ┌─────────────────┐
           │  Frontend       │
           │  (Next.js)      │
           └────────┬────────┘
                    │ /api/livekit/rooms
                    │ /api/livekit/token
                    ▼
           ┌─────────────────┐         ┌──────────────────┐
           │  Backend        │ ──────▶ │  LiveKit SFU     │
           │  (FastAPI)      │ ◀────── │  (self-hosted)   │
           └────────┬────────┘  Webhook└────────┬─────────┘
                    │                            │
                    ▼                            ▼
              ┌──────────┐              ┌─────────────────┐
              │ Supabase │              │ Redis / S3      │
              │ (data)   │              │ (state / media) │
              └──────────┘              └─────────────────┘
```

LiveKit 与既有 Zoom / 腾讯会议 provider 并存,统一通过 `VIDEO_PROVIDER` env 切换.