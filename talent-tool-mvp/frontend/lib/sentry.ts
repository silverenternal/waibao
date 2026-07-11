// T1003 - Sentry 客户端初始化. 仅在生产环境启用,beforeSend 过滤 PII.
//
// 通过动态 import 避免在开发模式下加载 Sentry SDK.
// 如果未安装 @sentry/nextjs,本模块的所有导出都是 no-op.

type SentryLike = {
  init: (options: Record<string, unknown>) => void;
  captureException: (err: unknown) => void;
  captureMessage: (msg: string, level?: string) => void;
};

let sentryInstance: SentryLike | null = null;
let initialized = false;

const PII_KEYS = new Set([
  "password",
  "token",
  "authorization",
  "cookie",
  "email",
  "phone",
  "ssn",
  "national_insurance_number",
]);

function stripPII(input: unknown): unknown {
  if (input === null || input === undefined) return input;
  if (Array.isArray(input)) return input.map(stripPII);
  if (typeof input !== "object") return input;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(input as Record<string, unknown>)) {
    if (PII_KEYS.has(k.toLowerCase())) {
      out[k] = "[REDACTED]";
    } else {
      out[k] = stripPII(v);
    }
  }
  return out;
}

export async function initSentry(): Promise<void> {
  if (initialized) return;
  initialized = true;

  // 仅生产环境启用
  const env = process.env.NEXT_PUBLIC_APP_ENV || process.env.NODE_ENV || "development";
  if (env !== "production") {
    return;
  }
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) {
    return;
  }
  try {
    // 动态 import 避免在开发模式加载 Sentry
    // @ts-expect-error - 可选依赖,可能未安装
    const mod = (await import("@sentry/nextjs").catch(() => null)) as
      | { default?: SentryLike }
      | null;
    if (!mod || !mod.default) {
      // 没有装 @sentry/nextjs,使用 stub
      sentryInstance = {
        init: () => {},
        captureException: () => {},
        captureMessage: () => {},
      };
      return;
    }
    const Sentry = mod.default;
    Sentry.init({
      dsn,
      environment: env,
      tracesSampleRate: 0.1,
      profilesSampleRate: 0.1,
      sendDefaultPii: false,
      beforeSend(event: { user?: Record<string, unknown>; extra?: unknown; contexts?: unknown; request?: { cookies?: unknown } }) {
        // 过滤 PII
        if (event.user) {
          const u = { ...(event.user as Record<string, unknown>) };
          for (const k of Object.keys(u)) {
            if (PII_KEYS.has(k.toLowerCase())) u[k] = "[REDACTED]";
          }
          event.user = u as never;
        }
        if (event.extra) event.extra = stripPII(event.extra) as never;
        if (event.contexts) event.contexts = stripPII(event.contexts) as never;
        if (event.request && event.request.cookies) {
          event.request.cookies = {};
        }
        return event;
      },
    });
    sentryInstance = Sentry;
  } catch {
    // 静默失败 — Sentry 是辅助能力,不应阻塞应用启动
    sentryInstance = null;
  }
}

export function captureException(err: unknown): void {
  if (!sentryInstance) return;
  try {
    sentryInstance.captureException(err);
  } catch {
    /* noop */
  }
}

export function captureMessage(msg: string, level: string = "info"): void {
  if (!sentryInstance) return;
  try {
    sentryInstance.captureMessage(msg, level);
  } catch {
    /* noop */
  }
}