/**
 * T1203 — uni-app API config.
 *
 * The mini-program talks to the waibao v3.0 FastAPI backend.
 *
 * `BASE_URL` resolution order:
 *   1. compile-time env (VITE_API_BASE_URL) — set in CI / build command
 *   2. localStorage cache (set from settings page)
 *   3. hardcoded production fallback
 *
 * `MP-WEIXIN` requires an HTTPS domain whitelisted in the WeChat console —
 * for dev we hit the local backend through a proxy / `enable-dev` flag.
 */

export type AppEnv = 'dev' | 'staging' | 'prod';

export interface ApiConfig {
  baseUrl: string;
  timeoutMs: number;
  env: AppEnv;
}

const FALLBACK_BASE: Record<AppEnv, string> = {
  dev: 'https://dev-api.waibao.example.com',
  staging: 'https://staging-api.waibao.example.com',
  prod: 'https://api.waibao.example.com',
};

export const DEFAULT_CONFIG: ApiConfig = {
  // Compile-time override via `vite define` → `import.meta.env.VITE_API_BASE_URL`.
  baseUrl: (import.meta.env.VITE_API_BASE_URL as string) || FALLBACK_BASE.prod,
  timeoutMs: 15_000,
  env: ((import.meta.env.VITE_APP_ENV as AppEnv) || 'prod'),
};

let _runtime: Partial<ApiConfig> = {};

export function setRuntimeConfig(patch: Partial<ApiConfig>): void {
  _runtime = { ..._runtime, ...patch };
  try {
    uni.setStorageSync('wb_api_config', JSON.stringify({ ...DEFAULT_CONFIG, ..._runtime }));
  } catch {
    // ignore — storage may be unavailable in some test contexts
  }
}

export function getConfig(): ApiConfig {
  if (Object.keys(_runtime).length === 0) {
    try {
      const cached = uni.getStorageSync('wb_api_config') as string | undefined;
      if (cached) {
        _runtime = JSON.parse(cached) as Partial<ApiConfig>;
      }
    } catch {
      // ignore
    }
  }
  return { ...DEFAULT_CONFIG, ..._runtime };
}