/**
 * T1204 — Feishu/Lark JSAPI 封装.
 */
declare global {
  // eslint-disable-next-line no-var
  var tt: any;
}

function getLark(): any | null {
  if (typeof uni !== 'undefined' && (uni as any).requireNativePlugin) {
    return (uni as any).requireNativePlugin('Lark') || (typeof tt !== 'undefined' ? tt : null);
  }
  return typeof tt !== 'undefined' ? tt : null;
}

export function isFeishu(): boolean {
  return getLark() !== null;
}

export interface LarkRuntime {
  isFeishu: boolean;
  appId: string | null;
  version: string | null;
}

export function getRuntime(): LarkRuntime {
  const l = getLark();
  if (!l) return { isFeishu: false, appId: null, version: null };
  try {
    return {
      isFeishu: true,
      appId: l.config?.appId || null,
      version: l.config?.version || l.SDKVersion || null,
    };
  } catch {
    return { isFeishu: true, appId: null, version: null };
  }
}

/** 飞书免登. */
export function login(): Promise<{ code: string }> {
  const l = getLark();
  if (!l) return Promise.reject(new Error('not in Feishu container'));
  return new Promise((resolve, reject) => {
    l.login?.({
      success: (res: any) => resolve({ code: res.code }),
      fail: (err: any) => reject(err),
    });
  });
}

/** 获取用户信息. */
export function getUserInfo(): Promise<{ openId: string; name: string; avatar: string }> {
  const l = getLark();
  if (!l) return Promise.reject(new Error('not in Feishu container'));
  return new Promise((resolve, reject) => {
    l.getUserInfo?.({
      success: (res: any) => resolve({
        openId: res.openId || '',
        name: res.nickName || '',
        avatar: res.avatarUrl || '',
      }),
      fail: (err: any) => reject(err),
    });
  });
}

/** 唤起审批详情. */
export function openApprovalDetail(instanceId: string): void {
  const l = getLark();
  l?.openLink?.({ url: `feishu://approval/detail/${instanceId}` });
}

/** 发送群消息. */
export function sendMessage(chatId: string, content: string): Promise<void> {
  const l = getLark();
  if (!l) return Promise.reject(new Error('not in Feishu container'));
  return new Promise((resolve, reject) => {
    l.sendMessageToChat?.({
      chat_id: chatId,
      msg_type: 'text',
      content: { text: content },
      success: () => resolve(),
      fail: (err: any) => reject(err),
    });
  });
}

/** 设置导航栏标题. */
export function setTitle(title: string): void {
  const l = getLark();
  l?.setNavigationBarTitle?.({ title });
}

export const larkApi = {
  getRuntime,
  getUserInfo,
  isFeishu,
  login,
  openApprovalDetail,
  sendMessage,
  setTitle,
};

export default larkApi;