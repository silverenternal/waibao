/**
 * T1203 — auth endpoints (wraps the backend `/api/auth/*` routes).
 *
 * Login flow on WeChat mini-program:
 *   1. `uni.login()` → wx code
 *   2. POST /api/auth/wechat-login { code }
 *   3. backend does code2session (or mock), returns JWT + openid
 *   4. mini-program stores JWT in pinia + storage, injects Authorization header
 */
import { request } from './request';

export interface MiniProgramConfig {
  appid: string;
  enable_mock_login: boolean;
}

export interface LoginResponse {
  token: string;
  token_type: string;
  expires_in: number;
  openid: string;
  unionid: string | null;
  user: {
    id: string;
    email: string;
    role: 'talent_partner' | 'client' | 'admin';
  };
  is_new_user: boolean;
}

export interface WechatLoginParams {
  code: string;
  role?: 'talent_partner' | 'client' | 'admin';
  nickname?: string;
  avatar?: string;
}

export async function fetchMiniprogramConfig() {
  return request<MiniProgramConfig>('/api/auth/miniprogram-config', { anonymous: true });
}

export async function wechatLogin(params: WechatLoginParams) {
  return request<LoginResponse>('/api/auth/wechat-login', {
    method: 'POST',
    body: params,
    anonymous: true,
  });
}

export async function phoneLogin(params: { code: string; openid: string }) {
  return request<LoginResponse>('/api/auth/phone-login', {
    method: 'POST',
    body: params,
    anonymous: true,
  });
}

export async function fetchMe() {
  return request<{ id: string; email: string; role: string }>('/api/users/me');
}