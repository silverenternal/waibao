/**
 * T1204 — 钉钉 JSAPI 封装.
 *
 * 钉钉小程序容器内 `dd` 是全局对象,H5/其他平台通过 uni.requireNativePlugin 注入.
 * 这里统一封装常用方法 + 自动降级到 mock (H5 测试).
 */

export interface DdUserInfo {
  nickName: string;
  avatarUrl: string;
  corpId: string;
  userid: string;
  unionid?: string;
  department?: string[];
}

export interface DdRuntime {
  isDingTalk: boolean;
  appId: string | null;
  version: string | null;
}

declare global {
  // eslint-disable-next-line no-var
  var dd: any;
}

function getDd(): any | null {
  if (typeof uni !== 'undefined' && (uni as any).requireNativePlugin) {
    // 钉钉小程序原生环境
    return (uni as any).requireNativePlugin('DingTalk') || (typeof dd !== 'undefined' ? dd : null);
  }
  return typeof dd !== 'undefined' ? dd : null;
}

/** 是否在钉钉容器内运行. */
export function isDingTalk(): boolean {
  return getDd() !== null;
}

/** 获取 runtime 信息. */
export function getRuntime(): DdRuntime {
  const d = getDd();
  if (!d) return { isDingTalk: false, appId: null, version: null };
  try {
    return {
      isDingTalk: true,
      appId: d.appId || d.runtime?.appId || null,
      version: d.version || d.runtime?.version || null,
    };
  } catch {
    return { isDingTalk: true, appId: null, version: null };
  }
}

/** 钉钉免登 — 获取 userid + corpId. */
export function login(): Promise<{ code: string; corpId?: string }> {
  const d = getDd();
  if (!d) return Promise.reject(new Error('not in DingTalk container'));
  return new Promise((resolve, reject) => {
    d.runtime.permission.requestAuthCode({
      corpId: d.corpId || '',
      onSuccess: (res: any) => resolve({ code: res.code, corpId: d.corpId }),
      onFail: (err: any) => reject(err),
    });
  });
}

/** 获取用户信息 (需要授权). */
export function getUserInfo(): Promise<DdUserInfo> {
  const d = getDd();
  if (!d) return Promise.reject(new Error('not in DingTalk container'));
  return new Promise((resolve, reject) => {
    d.biz.user.get({
      onSuccess: (res: any) => {
        resolve({
          nickName: res.nickName || '',
          avatarUrl: res.avatarUrl || '',
          corpId: d.corpId || '',
          userid: res.userid || '',
          unionid: res.unionid,
          department: res.department,
        });
      },
      onFail: (err: any) => reject(err),
    });
  });
}

/** 关闭当前钉钉页面. */
export function closePage(): void {
  const d = getDd();
  d?.biz.navigation.close?.({
    onSuccess: () => {},
    onFail: () => {},
  });
}

/** 打开审批流详情. */
export function openApprovalDetail(processInstanceId: string): void {
  const d = getDd();
  d?.biz.util.openLink?.({
    url: `dingtalk://dingtalkclient/page/approval?procInsId=${processInstanceId}`,
    onSuccess: () => {},
    onFail: () => {},
  });
}

/** 发起钉钉 IM 通知. */
export function sendIM(
  userIds: string[],
  content: string,
  title = '通知',
): Promise<void> {
  const d = getDd();
  if (!d) return Promise.reject(new Error('not in DingTalk container'));
  return new Promise((resolve, reject) => {
    d.biz.chat.chooseConversationAndSendMsg?.({
      users: userIds,
      content: { msgtype: 'text', text: { content: `${title}\n${content}` } },
      onSuccess: () => resolve(),
      onFail: (err: any) => reject(err),
    });
  });
}

/** 唤起扫一扫. */
export function scan(): Promise<{ text: string }> {
  const d = getDd();
  if (!d) return Promise.reject(new Error('not in DingTalk container'));
  return new Promise((resolve, reject) => {
    d.biz.util.scan?.({
      onSuccess: (res: any) => resolve({ text: res.text }),
      onFail: (err: any) => reject(err),
    });
  });
}

/** 设置右上角菜单. */
export function setTitle(title: string): void {
  const d = getDd();
  d?.biz.navigation.setTitle?.({ title });
}

/** 监听网络状态变化. */
export function onNetworkChange(cb: (online: boolean) => void): () => void {
  const d = getDd();
  if (!d?.device?.notification?.network) return () => {};
  const handler = (res: any) => cb(!!res.networkType && res.networkType !== 'none');
  d.device.notification.network.on(handler);
  return () => d.device.notification.network.off(handler);
}

export const ddApi = {
  closePage,
  getRuntime,
  getUserInfo,
  isDingTalk,
  login,
  onNetworkChange,
  openApprovalDetail,
  scan,
  sendIM,
  setTitle,
};

export default ddApi;