# syntax=docker/dockerfile:1.7
# =============================================================================
# frontend/Dockerfile — v11.0 / T6111 一键本地部署用前端镜像
#
# 多阶段构建 (不依赖 output: 'standalone'; Next 16 + Turbopack 用 next start):
#   1. deps    —— 仅装依赖, 利用层缓存
#   2. builder —— next build, 产出 .next 构建产物
#   3. runtime —— 最小非 root 镜像, 跑 `next start`
#
# 本地 docker-compose.local.yml 直接 build 这个 Dockerfile,
# 甲方环境无需本机装 Node 也能跑起前端 (:3000)。
# =============================================================================
FROM node:20-alpine AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then \
        npm ci --no-audit --no-fund; \
    else \
        npm install --no-audit --no-fund; \
    fi

# ===========================================================================
# Stage 2 — builder
# ===========================================================================
FROM node:20-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ .
# 浏览器端通过 NEXT_PUBLIC_API_URL 访问宿主暴露的后端。
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# ===========================================================================
# Stage 3 — runtime (minimal, non-root)
# ===========================================================================
FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup --system --gid 10001 nodejs \
 && adduser  --system --uid 10001 nextjs
# 拷贝构建产物 + 运行时所需文件 (非 root 属主)
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nodejs /app/package.json ./package.json
COPY --from=builder --chown=nextjs:nodejs /app/next.config.ts ./next.config.ts
COPY --from=builder --chown=nextjs:nodejs /app/i18n.ts ./i18n.ts
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/ >/dev/null 2>&1 || exit 1
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
