# LiveKit Local Dev

Quick start:

```bash
# 1. 启动 (自动下载镜像 + 启动)
docker compose -f infra/livekit/docker-compose.yml up -d

# 2. 验证
curl http://localhost:7880/
# 应返回 200 + 服务信息

# 3. 配合 backend:
export LIVEKIT_URL=ws://localhost:7880
export LIVEKIT_API_KEY=APIwXkjY8N7qGRtVzmHp9DTr4cKLbn
export LIVEKIT_API_SECRET=secret_2jKp7QvRmH4N8cLsW3yF6tB9xZ1aE5uD
export VIDEO_PROVIDER=livekit
cd backend && uvicorn main:app --reload
```

生产环境:

- 替换 `LIVEKIT_API_KEY/SECRET` 为 secrets manager 注入
- 启用 TLS: 配置 `LIVEKIT_TURN_TLS_PORT` + 反向代理 (nginx/caddy)
- 录制改用 S3/GCS: 配置 `egress.s3` 块
- 多节点: 必须配 Redis (compose 已包含)
- 跨区域: 使用 LiveKit Cloud 转发或自建 SFU mesh

注意:

- API key 必须与 `backend/providers/video_interview/livekit.py` 一致
- 默认端口 7880 (信令), 7881/UDP (RTC), 3478 (TURN)