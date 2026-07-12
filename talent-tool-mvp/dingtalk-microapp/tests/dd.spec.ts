/**
 * T1204 — DingTalk JSAPI (dd.ts) unit tests.
 *
 * Covers:
 *  - isDingTalk detection (no global dd => false)
 *  - getRuntime returns appId/version when container present
 *  - login / getUserInfo / scan / sendIM reject when no container
 *  - onNetworkChange returns noop unsubscribe when not in container
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  closePage,
  getRuntime,
  isDingTalk,
  login,
  getUserInfo,
  onNetworkChange,
  scan,
  sendIM,
  setTitle,
} from '../src/utils/dd';

declare global {
  // eslint-disable-next-line no-var
  var dd: any;
}

describe('dd.ts — without container', () => {
  beforeEach(() => {
    // @ts-ignore
    global.dd = undefined;
  });

  it('isDingTalk returns false', () => {
    expect(isDingTalk()).toBe(false);
  });

  it('getRuntime returns empty defaults', () => {
    const r = getRuntime();
    expect(r).toEqual({ isDingTalk: false, appId: null, version: null });
  });

  it('login rejects with no container', async () => {
    await expect(login()).rejects.toThrow('not in DingTalk container');
  });

  it('getUserInfo rejects with no container', async () => {
    await expect(getUserInfo()).rejects.toThrow('not in DingTalk container');
  });

  it('scan rejects with no container', async () => {
    await expect(scan()).rejects.toThrow('not in DingTalk container');
  });

  it('sendIM rejects with no container', async () => {
    await expect(sendIM(['u1'], 'hi')).rejects.toThrow('not in DingTalk container');
  });

  it('onNetworkChange returns noop unsubscribe', () => {
    const off = onNetworkChange(() => {});
    expect(typeof off).toBe('function');
    expect(() => off()).not.toThrow();
  });

  it('closePage / setTitle are noop without error', () => {
    expect(() => closePage()).not.toThrow();
    expect(() => setTitle('X')).not.toThrow();
  });
});

describe('dd.ts — inside container', () => {
  let handlers: Record<string, any> = {};

  beforeEach(() => {
    handlers = {};
    global.dd = {
      appId: 'APP-123',
      version: '7.0.0',
      corpId: 'CORP-1',
      runtime: { appId: 'APP-123', version: '7.0.0' },
      biz: {
        user: {
          get: (opts: any) => opts.onSuccess?.({ nickName: 'Alice', userid: 'u1', unionid: 'un1' }),
        },
        navigation: {
          close: (opts: any) => opts.onSuccess?.(),
          setTitle: (opts: any) => handlers['title'] = opts.title,
          openLink: vi.fn(),
        },
        chat: {
          chooseConversationAndSendMsg: (opts: any) => {
            handlers['imUsers'] = opts.users;
            opts.onSuccess?.();
          },
        },
        util: {
          scan: (opts: any) => opts.onSuccess?.({ text: 'scan-result' }),
          openLink: vi.fn(),
        },
      },
      runtime_inner: {
        permission: {
          requestAuthCode: (opts: any) => opts.onSuccess?.({ code: 'auth-code-xyz' }),
        },
      },
      device: {
        notification: {
          network: {
            on: (cb: any) => { handlers['netOn'] = true; },
            off: () => { handlers['netOff'] = true; },
          },
        },
      },
    };
    // 重写 runtime.permission 路径 (dd 实际结构)
    global.dd.runtime = global.dd.runtime || {};
    global.dd.runtime.permission = {
      requestAuthCode: (opts: any) => opts.onSuccess?.({ code: 'auth-code-xyz' }),
    };
  });

  afterEach(() => {
    // @ts-ignore
    global.dd = undefined;
  });

  it('isDingTalk returns true', () => {
    expect(isDingTalk()).toBe(true);
  });

  it('getRuntime returns appId/version', () => {
    const r = getRuntime();
    expect(r.isDingTalk).toBe(true);
    expect(r.appId).toBe('APP-123');
    expect(r.version).toBe('7.0.0');
  });

  it('login resolves with code', async () => {
    const res = await login();
    expect(res.code).toBe('auth-code-xyz');
    expect(res.corpId).toBe('CORP-1');
  });

  it('getUserInfo resolves with nickName', async () => {
    const info = await getUserInfo();
    expect(info.nickName).toBe('Alice');
    expect(info.userid).toBe('u1');
    expect(info.unionid).toBe('un1');
  });

  it('scan resolves with text', async () => {
    const r = await scan();
    expect(r.text).toBe('scan-result');
  });

  it('sendIM passes users to DingTalk', async () => {
    await sendIM(['u1', 'u2'], 'hello', 'TITLE');
    expect(handlers['imUsers']).toEqual(['u1', 'u2']);
  });

  it('setTitle forwards to dd.biz.navigation.setTitle', () => {
    setTitle('Workbench');
    expect(handlers['title']).toBe('Workbench');
  });

  it('onNetworkChange registers handler and returns unsubscriber', () => {
    const off = onNetworkChange(() => {});
    expect(handlers['netOn']).toBe(true);
    off();
    expect(handlers['netOff']).toBe(true);
  });
});