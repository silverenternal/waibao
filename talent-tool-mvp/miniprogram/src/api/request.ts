/**
 * T1203 — universal HTTP client.
 *
 * Wraps uni.request with:
 *   - automatic Authorization header from the user store
 *   - JSON encoding/decoding
 *   - 401 → re-login dispatch
 *   - 5xx → exponential backoff retry (max 2)
 *   - unified error envelope
 *
 * NOTE: uni-app compiles away platform-specific calls — `uni.request` works
 * for mp-weixin, h5 and app alike.
 */
import { useUserStore } from '@/store/user';
import { getConfig } from './config';

export interface ApiOk<T> {
  ok: true;
  status: number;
  data: T;
}

export interface ApiErr {
  ok: false;
  status: number;
  code: string;
  message: string;
  raw?: unknown;
}

export type ApiResult<T> = ApiOk<T> | ApiErr;

export class ApiError extends Error {
  status: number;
  code: string;
  raw?: unknown;
  constructor(opts: { status: number; code: string; message: string; raw?: unknown }) {
    super(opts.message);
    this.status = opts.status;
    this.code = opts.code;
    this.raw = opts.raw;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  headers?: Record<string, string>;
  /** Skip auth header injection (used by login itself). */
  anonymous?: boolean;
  /** Disable auto retry on 5xx. */
  noRetry?: boolean;
  /** Override timeout (ms). */
  timeoutMs?: number;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const cfg = getConfig();
  const base = cfg.baseUrl.replace(/\/+$/, '');
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  if (!query) return `${base}${cleanPath}`;
  const qs = Object.entries(query)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  return qs ? `${base}${cleanPath}?${qs}` : `${base}${cleanPath}`;
}

async function rawRequest<T>(path: string, opts: RequestOptions): Promise<UniApp.RequestSuccessCallbackResult> {
  const cfg = getConfig();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    ...(opts.headers || {}),
  };
  if (!opts.anonymous) {
    const user = useUserStore();
    if (user.token) headers['Authorization'] = `Bearer ${user.token}`;
  }
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl(path, opts.query),
      method: opts.method || 'GET',
      data: opts.body === undefined ? undefined : (typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body)),
      header: headers,
      timeout: opts.timeoutMs ?? cfg.timeoutMs,
      success: (res) => resolve(res),
      fail: (err) => reject(err),
    });
  });
}

async function requestWithRetry<T>(path: string, opts: RequestOptions, attempt = 0): Promise<ApiResult<T>> {
  try {
    const res = await rawRequest<T>(path, opts);
    const status = res.statusCode;
    if (status >= 200 && status < 300) {
      return { ok: true, status, data: res.data as T };
    }
    // 401 → clear auth, dispatch re-login
    if (status === 401 && !opts.anonymous) {
      const user = useUserStore();
      user.clearSession();
      uni.showToast({ title: '登录已过期,请重新登录', icon: 'none' });
      setTimeout(() => {
        uni.reLaunch({ url: '/pages/login/index' });
      }, 800);
      return {
        ok: false,
        status,
        code: 'unauthorized',
        message: '登录已过期',
        raw: res.data,
      };
    }
    // Retry on 5xx (idempotent only — caller controls with noRetry)
    if (status >= 500 && !opts.noRetry && attempt < 2) {
      const delay = 250 * Math.pow(2, attempt);
      await new Promise((r) => setTimeout(r, delay));
      return requestWithRetry(path, opts, attempt + 1);
    }
    const detail = (res.data as { detail?: string; message?: string }) || {};
    return {
      ok: false,
      status,
      code: `http_${status}`,
      message: detail.detail || detail.message || `请求失败 (${status})`,
      raw: res.data,
    };
  } catch (err) {
    if (attempt < 2 && !opts.noRetry) {
      const delay = 250 * Math.pow(2, attempt);
      await new Promise((r) => setTimeout(r, delay));
      return requestWithRetry(path, opts, attempt + 1);
    }
    return {
      ok: false,
      status: 0,
      code: 'network_error',
      message: '网络异常,请检查网络连接',
      raw: err,
    };
  }
}

export async function request<T = unknown>(path: string, opts: RequestOptions = {}): Promise<ApiResult<T>> {
  return requestWithRetry<T>(path, opts);
}

/** Throws ApiError on non-2xx. Use when you want try/catch style. */
export async function requestOrThrow<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await request<T>(path, opts);
  if (!res.ok) throw new ApiError(res);
  return res.data;
}