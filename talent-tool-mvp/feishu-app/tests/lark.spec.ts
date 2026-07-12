/**
 * T1204 — Feishu/Lark JSAPI unit tests.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import {
  getRuntime,
  getUserInfo,
  isFeishu,
  larkApi,
  login,
  sendMessage,
  setTitle,
} from '../src/utils/lark';

declare global {
  // eslint-disable-next-line no-var
  var tt: any;
}

describe('lark.ts — without container', () => {
  beforeEach(() => {
    // @ts-ignore
    global.tt = undefined;
  });

  it('isFeishu returns false', () => {
    expect(isFeishu()).toBe(false);
  });

  it('getRuntime returns defaults', () => {
    expect(getRuntime()).toEqual({ isFeishu: false, appId: null, version: null });
  });

  it('login rejects', async () => {
    await expect(login()).rejects.toThrow('not in Feishu container');
  });

  it('getUserInfo rejects', async () => {
    await expect(getUserInfo()).rejects.toThrow('not in Feishu container');
  });

  it('sendMessage rejects', async () => {
    await expect(sendMessage('c1', 'hi')).rejects.toThrow('not in Feishu container');
  });

  it('setTitle is noop', () => {
    expect(() => setTitle('X')).not.toThrow();
  });

  it('larkApi exports all functions', () => {
    expect(typeof larkApi.isFeishu).toBe('function');
    expect(typeof larkApi.login).toBe('function');
    expect(typeof larkApi.setTitle).toBe('function');
  });
});

describe('lark.ts — inside Feishu container', () => {
  let handlers: Record<string, any> = {};

  beforeEach(() => {
    handlers = {};
    global.tt = {
      config: { appId: 'CLI-123', version: '1.2.3' },
      SDKVersion: '1.2.3',
      login: (opts: any) => opts.success?.({ code: 'f-code' }),
      getUserInfo: (opts: any) =>
        opts.success?.({ openId: 'ou-x', nickName: 'Bob', avatarUrl: 'https://img' }),
      sendMessageToChat: (opts: any) => {
        handlers['chatId'] = opts.chat_id;
        handlers['msgType'] = opts.msg_type;
        opts.success?.();
      },
      setNavigationBarTitle: (opts: any) => { handlers['title'] = opts.title; },
      openLink: (opts: any) => { handlers['link'] = opts.url; },
    };
  });

  it('isFeishu true', () => {
    expect(isFeishu()).toBe(true);
  });

  it('getRuntime returns app info', () => {
    const r = getRuntime();
    expect(r.isFeishu).toBe(true);
    expect(r.appId).toBe('CLI-123');
    expect(r.version).toBe('1.2.3');
  });

  it('login resolves with code', async () => {
    const r = await login();
    expect(r.code).toBe('f-code');
  });

  it('getUserInfo resolves with profile', async () => {
    const u = await getUserInfo();
    expect(u.openId).toBe('ou-x');
    expect(u.name).toBe('Bob');
  });

  it('sendMessage forwards chat_id', async () => {
    await sendMessage('oc-chat', 'hi');
    expect(handlers['chatId']).toBe('oc-chat');
    expect(handlers['msgType']).toBe('text');
  });

  it('setTitle forwards title', () => {
    setTitle('Workbench');
    expect(handlers['title']).toBe('Workbench');
  });
});