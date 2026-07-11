import type { NextConfig } from "next";
import path from "node:path";
import { createRequire } from "node:module";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n.ts");

// T1003: 可选接入 @sentry/nextjs. 没装则降级到原始 config.
function withSentryIfAvailable<T>(config: T): T {
  try {
    const require = createRequire(__filename);
    const { withSentryConfig } = require("@sentry/nextjs") as {
      withSentryConfig: <U>(cfg: U, opts: Record<string, unknown>) => U;
    };
    return withSentryConfig(config, {
      silent: true,
      hideSourceMaps: true,
      disableLogger: true,
      widenClientFileUpload: true,
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
    }) as T;
  } catch {
    return config;
  }
}

// Turbopack 对 tsconfig paths 的 "../" 通配解析有边界情况,显式声明 alias 保证构建。
// 详见: node_modules/next/dist/docs/01-app/02-guides/upgrading/version-16.md (resolveAlias)
const contractsCanonical = path.resolve(__dirname, "../contracts/canonical.ts");

const nextConfig: NextConfig = {
  /* config options here */
};

export default withSentryIfAvailable(withNextIntl(nextConfig));