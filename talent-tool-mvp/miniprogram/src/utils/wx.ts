/**
 * T1203 — WeChat-specific helpers (login, phone, share).
 *
 * `uni.login()` already abstracts the underlying platform. For mini-program
 * we delegate to wx.login so this works on H5 / App too.
 */
import { logger } from './logger';

export interface WxLoginResult {
  code: string;
}

export function wxLogin(): Promise<WxLoginResult> {
  return new Promise((resolve, reject) => {
    uni.login({
      provider: 'weixin',
      success: (res) => {
        if (res.code) resolve({ code: res.code });
        else reject(new Error(res.errMsg || 'wx.login failed'));
      },
      fail: (err) => reject(err),
    });
  });
}

export function getUserProfile(): Promise<{ nickname: string; avatar: string }> {
  return new Promise((resolve, reject) => {
    uni.getUserProfile({
      desc: '用于完善您的画像资料',
      success: (res) => {
        resolve({
          nickname: res.userInfo.nickName,
          avatar: res.userInfo.avatarUrl,
        });
      },
      fail: (err) => {
        logger.warn('getUserProfile failed', err);
        reject(err);
      },
    });
  });
}

export function startRecord(): Promise<{ tempFilePath: string }> {
  return new Promise((resolve, reject) => {
    uni.startRecord({
      success: () => resolve({ tempFilePath: '' }),
      fail: reject,
    });
  });
}

export function stopRecord(): Promise<{ tempFilePath: string; duration: number }> {
  return new Promise((resolve, reject) => {
    uni.stopRecord({
      success: (res) => resolve({ tempFilePath: res.tempFilePath, duration: res.duration }),
      fail: reject,
    });
  });
}