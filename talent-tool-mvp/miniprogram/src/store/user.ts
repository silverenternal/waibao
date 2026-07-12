/**
 * T1203 — user session store (Pinia).
 *
 * Persists token + openid + user to localStorage so a relaunch keeps the
 * user signed in for the 7-day JWT lifetime.
 */
import { defineStore } from 'pinia';
import { fetchMe, wechatLogin } from '@/api/auth';

interface SessionUser {
  id: string;
  email: string;
  role: 'talent_partner' | 'client' | 'admin';
}

interface State {
  token: string;
  openid: string;
  unionid: string | null;
  user: SessionUser | null;
  hydrated: boolean;
}

const STORAGE_KEY = 'wb_session_v1';

function readStorage(): Partial<State> {
  try {
    const raw = uni.getStorageSync(STORAGE_KEY) as string | undefined;
    if (!raw) return {};
    return JSON.parse(raw) as Partial<State>;
  } catch {
    return {};
  }
}

function writeStorage(patch: Partial<State>) {
  try {
    const current = readStorage();
    uni.setStorageSync(STORAGE_KEY, JSON.stringify({ ...current, ...patch }));
  } catch {
    // ignore
  }
}

export const useUserStore = defineStore('user', {
  state: (): State => ({
    token: '',
    openid: '',
    unionid: null,
    user: null,
    hydrated: false,
  }),
  getters: {
    isLoggedIn: (s) => !!s.token && !!s.user,
    isEmployer: (s) => s.user?.role === 'client' || s.user?.role === 'admin',
    isAdmin: (s) => s.user?.role === 'admin',
  },
  actions: {
    async bootstrap() {
      if (this.hydrated) return;
      const cached = readStorage();
      if (cached.token) {
        this.token = cached.token;
        this.openid = cached.openid || '';
        this.unionid = cached.unionid ?? null;
        this.user = cached.user || null;
        // Fire-and-forget refresh — silently drop if expired.
        try {
          const res = await fetchMe();
          if (res.ok) {
            this.user = { ...(this.user as SessionUser), ...res.data };
            writeStorage({ user: this.user });
          } else {
            this.clearSession();
          }
        } catch {
          // network down — keep cached session
        }
      }
      this.hydrated = true;
    },

    async loginWithWechat(params: { code: string; nickname?: string; avatar?: string }) {
      const res = await wechatLogin(params);
      if (!res.ok) {
        throw new Error(res.message || '微信登录失败');
      }
      this.token = res.data.token;
      this.openid = res.data.openid;
      this.unionid = res.data.unionid;
      this.user = {
        id: res.data.user.id,
        email: res.data.user.email,
        role: res.data.user.role,
      };
      writeStorage({
        token: this.token,
        openid: this.openid,
        unionid: this.unionid,
        user: this.user,
      });
      return res.data;
    },

    setRole(role: SessionUser['role']) {
      if (!this.user) return;
      this.user = { ...this.user, role };
      writeStorage({ user: this.user });
    },

    clearSession() {
      this.token = '';
      this.openid = '';
      this.unionid = null;
      this.user = null;
      try {
        uni.removeStorageSync(STORAGE_KEY);
      } catch {
        // ignore
      }
    },
  },
});