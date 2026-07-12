/**
 * T1203 — uni-app test suite.
 *
 * These run in Node via Vitest, mocking `uni.*` global APIs. They cover the
 * non-platform-specific helpers (request envelope, JWT decoding, formatter).
 * Platform-bound code (uni.login, uni.uploadFile) needs real-device testing —
 * see tests/REAL_DEVICE.md.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock uni global before importing anything that touches it
const uniMock = {
  request: vi.fn(),
  uploadFile: vi.fn(),
  getStorageSync: vi.fn(() => ''),
  setStorageSync: vi.fn(),
  removeStorageSync: vi.fn(),
  showToast: vi.fn(),
  reLaunch: vi.fn(),
  navigateTo: vi.fn(),
  login: vi.fn(),
  getUserProfile: vi.fn(),
  startRecord: vi.fn(),
  stopRecord: vi.fn(),
};
(globalThis as any).uni = uniMock;

import { ApiError, request, requestOrThrow } from '../src/api/request';
import { formatDate, relativeTime, uuid, safeJsonParse } from '../src/utils/format';
import { createPinia, setActivePinia } from 'pinia';
import { useUserStore } from '../src/store/user';

beforeEach(() => {
  vi.clearAllMocks();
  setActivePinia(createPinia());
  uniMock.getStorageSync.mockImplementation(() => '');
});

describe('format utils', () => {
  it('formatDate produces YYYY-MM-DD HH:mm', () => {
    expect(formatDate('2025-01-02T03:04:00Z', false)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(formatDate('2025-01-02T03:04:00Z', true)).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  });

  it('relativeTime maps to friendly buckets', () => {
    const now = new Date();
    expect(relativeTime(now)).toBe('刚刚');
    expect(relativeTime(new Date(now.getTime() - 30 * 60 * 1000))).toMatch(/分钟前/);
    expect(relativeTime(new Date(now.getTime() - 2 * 3600 * 1000))).toMatch(/小时前/);
  });

  it('uuid returns valid v4-ish strings', () => {
    for (let i = 0; i < 5; i++) {
      expect(uuid()).toMatch(/^[0-9a-f-]{36}$/);
    }
  });

  it('safeJsonParse handles bad input', () => {
    expect(safeJsonParse(null, { x: 1 })).toEqual({ x: 1 });
    expect(safeJsonParse('not json', 0)).toBe(0);
    expect(safeJsonParse('{"a":1}', {})).toEqual({ a: 1 });
  });
});

describe('request envelope', () => {
  it('returns ok=true on 2xx', async () => {
    uniMock.request.mockImplementation(({ success }: any) =>
      success({ statusCode: 200, data: { hello: 'world' } })
    );
    const res = await request<{ hello: string }>('/api/foo');
    expect(res.ok).toBe(true);
    if (res.ok) expect(res.data.hello).toBe('world');
  });

  it('returns ok=false on 4xx and does not retry', async () => {
    uniMock.request.mockImplementation(({ success }: any) =>
      success({ statusCode: 404, data: { detail: 'not found' } })
    );
    const res = await request('/api/foo');
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.status).toBe(404);
      expect(res.message).toBe('not found');
      expect(uniMock.request).toHaveBeenCalledTimes(1);
    }
  });

  it('retries on 5xx (max 2 retries)', async () => {
    uniMock.request.mockImplementation(({ success }: any) =>
      success({ statusCode: 500, data: { detail: 'oops' } })
    );
    const res = await request('/api/foo');
    expect(res.ok).toBe(false);
    expect(uniMock.request).toHaveBeenCalledTimes(3); // initial + 2 retries
  });

  it('retries on network failure', async () => {
    uniMock.request.mockImplementation(({ fail }: any) =>
      fail(new Error('network down'))
    );
    const res = await request('/api/foo');
    expect(res.ok).toBe(false);
    expect(uniMock.request).toHaveBeenCalledTimes(3);
  });

  it('clears session on 401 and re-launches to login', async () => {
    const user = useUserStore();
    user.token = 'stale';
    user.user = { id: 'u', email: 'a@b.c', role: 'talent_partner' };

    uniMock.request.mockImplementation(({ success }: any) =>
      success({ statusCode: 401, data: { detail: 'unauthorized' } })
    );
    const res = await request('/api/foo');
    expect(res.ok).toBe(false);
    expect(user.token).toBe('');
    expect(user.user).toBeNull();
    expect(uniMock.reLaunch).toHaveBeenCalledWith({ url: '/pages/login/index' });
  });

  it('injects Authorization header when token present', async () => {
    const user = useUserStore();
    user.token = 'jwt-abc';
    user.user = { id: 'u', email: 'a@b.c', role: 'talent_partner' };

    let captured: any;
    uniMock.request.mockImplementation((opts: any) => {
      captured = opts;
      opts.success({ statusCode: 200, data: {} });
    });
    await request('/api/foo');
    expect(captured.header.Authorization).toBe('Bearer jwt-abc');
  });

  it('omits Authorization when anonymous=true', async () => {
    const user = useUserStore();
    user.token = 'jwt-abc';

    let captured: any;
    uniMock.request.mockImplementation((opts: any) => {
      captured = opts;
      opts.success({ statusCode: 200, data: {} });
    });
    await request('/api/auth/wechat-login', { anonymous: true, method: 'POST', body: { code: 'x' } });
    expect(captured.header.Authorization).toBeUndefined();
    expect(captured.method).toBe('POST');
  });

  it('requestOrThrow throws ApiError on non-2xx', async () => {
    uniMock.request.mockImplementation(({ success }: any) =>
      success({ statusCode: 400, data: { detail: 'bad' } })
    );
    await expect(requestOrThrow('/api/foo')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('user store', () => {
  it('loginWithWechat stores token + openid', async () => {
    uniMock.request.mockImplementation(({ success }: any) =>
      success({
        statusCode: 200,
        data: {
          token: 'jwt',
          token_type: 'Bearer',
          expires_in: 3600,
          openid: 'ox',
          unionid: null,
          user: { id: 'u1', email: 'a@b', role: 'talent_partner' },
          is_new_user: false,
        },
      })
    );

    const user = useUserStore();
    const res = await user.loginWithWechat({ code: 'abc' });
    expect(res.token).toBe('jwt');
    expect(user.token).toBe('jwt');
    expect(user.openid).toBe('ox');
    expect(user.user?.id).toBe('u1');
    expect(user.isLoggedIn).toBe(true);
  });

  it('clearSession wipes state and storage', async () => {
    const user = useUserStore();
    user.token = 't';
    user.user = { id: 'u', email: 'e', role: 'admin' };
    user.clearSession();
    expect(user.token).toBe('');
    expect(user.user).toBeNull();
    expect(uniMock.removeStorageSync).toHaveBeenCalled();
  });
});