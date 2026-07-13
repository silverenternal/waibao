# v9.0 Cross-End Consistency

> Single source of truth for design tokens across all five client surfaces.

## Surfaces

| Surface    | Path                                 | Renderer          | Tokens Source                |
|------------|--------------------------------------|-------------------|------------------------------|
| Web        | `talent-tool-mvp/frontend`           | Next.js 16 / R19  | `frontend/styles/tokens.ts`  |
| 小程序       | `talent-tool-mvp/miniprogram`        | WeChat WXML       | `miniprogram/src/styles/`    |
| 钉钉微应用    | `talent-tool-mvp/dingtalk-microapp`  | H5 (microapp)     | `dingtalk-microapp/src/styles/` |
| 飞书应用     | `talent-tool-mvp/feishu-app`         | H5 (microapp)     | `feishu-app/src/styles/`     |
| PWA        | `talent-tool-mvp/frontend`           | Service Worker    | Same as Web                  |

## Token Mapping

The Web `styles/tokens.ts` is the canonical definition. Each non-Web surface mirrors the
exact same RGB / spacing / typography values; only the syntax differs.

```ts
// Canonical — frontend/styles/tokens.ts
export const tokens = {
  color: { brand: { 50: "#ecfdf8", 500: "#00d4aa", 600: "#00a888", 950: "#042f2b" } },
  spacing: { xs: "0.25rem", sm: "0.5rem", md: "1rem", lg: "1.5rem", xl: "2rem" },
  typography: { size: { xs: "0.75rem", sm: "0.875rem", base: "1rem", lg: "1.125rem" } },
  radius: { sm: "0.5rem", md: "0.75rem", lg: "1rem" },
} as const;
```

| Token key        | Web (Tailwind class) | 小程序 (wxss var) | 钉钉 (CSS var)   | 飞书 (CSS var)   |
|------------------|----------------------|------------------|------------------|------------------|
| `color.brand.500`| `bg-brand-500`       | `--brand-500`    | `--brand-500`    | `--brand-500`    |
| `color.semantic.danger` | `text-red-500` | `--danger`       | `--danger`       | `--danger`       |
| `spacing.md`     | `p-4`                | `padding: 16rpx` | `padding: 1rem`  | `padding: 1rem`  |
| `radius.md`      | `rounded-lg`         | `border-radius: 12rpx` | `border-radius: 0.75rem` | `border-radius: 0.75rem` |
| `typography.size.base` | `text-base`    | `font-size: 16rpx` | `font-size: 1rem` | `font-size: 1rem` |

## Shared Components

| Component        | Web (TSX)        | 小程序 (WXML) | 钉钉 | 飞书 |
|------------------|------------------|---------------|------|------|
| PageHeader       | components/shared | ⏳ planned   | ⏳   | ⏳   |
| StatCard         | components/shared | ⏳           | ⏳   | ⏳   |
| DataTable        | components/shared | n/a          | ⏳   | ⏳   |
| EmptyState       | components/shared | ⏳           | ⏳   | ⏳   |
| LoadingState     | components/shared | ⏳           | ⏳   | ⏳   |
| ErrorState       | components/shared | ⏳           | ⏳   | ⏳   |

Web ships the full library now; the non-Web surfaces port a curated subset (the
markup is small — `<view class="stat-card">` etc.) so the visual stays identical.

## Verification

- The lint job (`frontend/AGENTS.md` + `eslint-config-next`) fails CI if a Web
  surface imports from anywhere except `styles/tokens.ts` for colors / spacing.
- Visual regression: `tests/visual/` snapshots are diffed at PR time; cross-end
  parity is verified manually against the Storybook reference pages.