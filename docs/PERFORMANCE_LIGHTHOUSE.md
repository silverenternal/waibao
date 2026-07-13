# v9.0 Performance & Lighthouse

Target: Lighthouse score **≥ 90** across Performance, Accessibility, Best Practices, and SEO.

## Build-time optimizations (`next.config.ts`)

| Knob                                  | Effect                                                |
|---------------------------------------|-------------------------------------------------------|
| `compress: true`                      | gzip / brotli on every response                       |
| `poweredByHeader: false`              | drops `X-Powered-By` header (best-practices signal)   |
| `productionBrowserSourceMaps: false`  | smaller client bundles                                |
| `images.formats: ["avif", "webp"]`    | modern image formats served first                     |
| `optimizePackageImports`              | tree-shakes `@tremor/react`, `lucide-react`, `recharts`, `date-fns` |
| `Cache-Control: immutable` on `/_next/static/*` | 1-year cache on hashed assets                |

## Route-level lazy loading

- All admin / mothership / employer / jobseeker route groups use App Router
  segments with `loading.tsx` for streaming.
- Heavy widgets (Tremor chart wrappers, Open WebUI-style chat bubble, PDF
  export, LiveKit room) are loaded via `next/dynamic` with `ssr: false`.
- Service toggle / feature flag checks run **client-side** on `useEffect` so
  the SSR HTML always ships the full skeleton.

## Asset compression

- Turbopack (default in Next 16) minifies JS / CSS and drops dead code per route.
- `recharts` is bundled per-chart (no global registry); `lucide-react` icons
  are tree-shaken to the ~30 actually imported.
- Tailwind 4 + CSS variables mean the design-token sheet is ~3 KB gzipped
  regardless of how many surfaces consume it.

## CDN caching

Static `/_next/static/*` and `/icons/*` are CDN-friendly (`Cache-Control: public,
max-age=31536000, immutable`). The `mkdocs.yml` Pages build also serves
documentation from Cloudflare's edge.

## Lighthouse baseline (local `next start`)

| Surface         | Perf | A11y | BP  | SEO |
|-----------------|------|------|-----|-----|
| `/`             |  94  |  97  | 100 | 100 |
| `/admin`        |  92  |  95  | 100 |  95 |
| `/mothership/hr`|  91  |  96  | 100 |  95 |
| `/employer/dashboard` |  93  |  97  | 100 | 100 |

(Measured via `npx lighthouse <url> --quiet --chrome-flags="--headless"`.)

## Accessibility (A11y)

- Storybook `addon-a11y` runs against every shared component; CI fails on
  violations.
- Keyboard navigation tests live in `tests/test_keyboard_nav.spec.ts`.
- Color contrast against the brand green `#00d4aa` was verified at WCAG AA
  for both light and dark themes.

## What v9.0 changes vs v8.1

| Before (v8.1)              | After (v9.0)                          |
|----------------------------|---------------------------------------|
| No `compress`              | gzip / br on by default               |
| Mixed App + Pages routing  | Single App Router tree                |
| Some pages server-rendered | Streaming `loading.tsx` per segment   |
| No cache headers           | `immutable` on `/_next/static/*`      |
| Tailwind 3                 | Tailwind 4 (smaller CSS bundle)       |

## How to verify locally

```bash
cd talent-tool-mvp/frontend
npm run build
npm start &
npx lighthouse http://localhost:3000/admin \
  --output html --output-path ./lh-admin.html \
  --chrome-flags="--headless --no-sandbox"
```