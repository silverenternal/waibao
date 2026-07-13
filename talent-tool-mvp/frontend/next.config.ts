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

// T1205 — PWA headers (manifest, service worker, icons).
// 实际 SW 缓存策略由 public/sw.js 处理 (避免 next-pwa 依赖,Next 16 兼容).
const PWA_HEADERS: Array<{ source: string; headers: Array<{ key: string; value: string }> }> = [
  {
    source: "/sw.js",
    headers: [
      { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
      { key: "Service-Worker-Allowed", value: "/" },
      { key: "Content-Type", value: "application/javascript" },
    ],
  },
  {
    source: "/manifest.json",
    headers: [
      { key: "Cache-Control", value: "public, max-age=3600" },
      { key: "Content-Type", value: "application/manifest+json" },
    ],
  },
  {
    source: "/icons/(.*)",
    headers: [
      { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
    ],
  },
];

// v9.0 — Performance defaults aligned with Lighthouse ≥90.
//   * `compress: true`          → gzip / br on every response
//   * `poweredByHeader: false`  → drop X-Powered-By (best-practices)
//   * `productionBrowserSourceMaps: false` → smaller bundles
//   * `images.formats`          → AVIF first, WebP fallback
//   * `output: 'standalone'` is NOT enabled here — Next 16 + Turbopack
//     already trims chunks via the React Server Components default. We
//     keep the regular `pages`/`app` runtime so deployments remain
//     compatible with the GitHub Pages + Edge hybrid in use today.
const nextConfig: NextConfig = {
  compress: true,
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
  images: {
    formats: ["image/avif", "image/webp"],
    remotePatterns: [
      { protocol: "https", hostname: "**" },
    ],
  },
  experimental: {
    // Tree-shake i18n messages per route — keeps the initial JS payload
    // under the 200 KB gzipped target Lighthouse recommends.
    optimizePackageImports: [
      "@tremor/react",
      "lucide-react",
      "recharts",
      "date-fns",
    ],
  },
  async headers() {
    return [
      ...PWA_HEADERS,
      // Long-cache hashed assets emitted under /_next/static.
      {
        source: "/_next/static/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=31536000, immutable",
          },
        ],
      },
    ];
  },
};

export default withSentryIfAvailable(withNextIntl(nextConfig));