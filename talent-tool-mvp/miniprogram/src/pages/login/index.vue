<template>
  <view class="login">
    <view class="login__hero">
      <view class="login__brand">waibao</view>
      <view class="login__subtitle">让 AI 成为你的求职合伙人</view>
    </view>

    <view class="login__panel">
      <view class="login__title">微信一键登录</view>
      <view class="login__hint">登录后即可与智能体对话、记录工作日记、查看职业规划</view>

      <button
        class="login__primary"
        :loading="loading"
        :disabled="loading"
        open-type="getUserInfo"
        @click="onWechatLogin"
      >
        微信登录
      </button>

      <button
        class="login__secondary"
        open-type="getPhoneNumber"
        @getphonenumber="onPhoneLogin"
      >
        手机号快捷登录
      </button>

      <view class="login__agreement">
        登录即表示已阅读并同意
        <text class="login__link" @click="openAgreement('user')">《用户协议》</text>
        和
        <text class="login__link" @click="openAgreement('privacy')">《隐私政策》</text>
      </view>
    </view>

    <view class="login__footer">v1.0.0 · {{ env }}</view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useUserStore } from '@/store/user';
import { wxLogin, getUserProfile } from '@/utils/wx';
import { logger } from '@/utils/logger';

const loading = ref(false);
const env = ref(import.meta.env.VITE_APP_ENV || 'prod');
const userStore = useUserStore();

async function onWechatLogin() {
  if (loading.value) return;
  loading.value = true;
  try {
    const { code } = await wxLogin();
    let nickname: string | undefined;
    let avatar: string | undefined;
    try {
      const profile = await getUserProfile();
      nickname = profile.nickname;
      avatar = profile.avatar;
    } catch {
      // 用户拒绝授权头像昵称 — 不阻塞登录
    }
    const res = await userStore.loginWithWechat({ code, nickname, avatar });
    logger.info('login ok, is_new_user=', res.is_new_user);
    uni.showToast({ title: '登录成功', icon: 'success' });
    setTimeout(() => routeAfterLogin(), 600);
  } catch (err) {
    logger.error('wechat login failed', err);
    uni.showToast({ title: (err as Error).message || '登录失败', icon: 'none' });
  } finally {
    loading.value = false;
  }
}

async function onPhoneLogin(e: {
  detail: { encryptedData?: string; iv?: string; code?: string; errMsg?: string };
}) {
  if (!e.detail.code) {
    uni.showToast({ title: '需要您授权手机号', icon: 'none' });
    return;
  }
  loading.value = true;
  try {
    // We piggyback on the wechat login first to get an openid; the encrypted
    // phone number is then verified by the backend `/api/auth/phone-login`.
    const { code: wxcode } = await wxLogin();
    const loginRes = await userStore.loginWithWechat({ code: wxcode });
    const phoneRes = await import('@/api/auth').then((m) =>
      m.phoneLogin({ code: e.detail.code as string, openid: loginRes.openid })
    );
    if (!phoneRes.ok) throw new Error(phoneRes.message || '手机号登录失败');
    userStore.token = phoneRes.data.token;
    uni.setStorageSync('wb_session_v1', JSON.stringify({ ...userStore.$state }));
    routeAfterLogin();
  } catch (err) {
    logger.error('phone login failed', err);
    uni.showToast({ title: (err as Error).message || '登录失败', icon: 'none' });
  } finally {
    loading.value = false;
  }
}

function routeAfterLogin() {
  // 求职者和 HR 走不同入口
  const isEmployer = userStore.isEmployer;
  const target = isEmployer
    ? '/pages/employer/index/index'
    : '/pages/jobseeker/index/index';
  uni.reLaunch({ url: target });
}

function openAgreement(kind: 'user' | 'privacy') {
  const path = kind === 'privacy' ? '/pages/employer/strategy/index' : '/pages/jobseeker/plan/index';
  // 占位 — 真实部署时换成 webview 指向合规托管页面
  uni.navigateTo({ url: `${path}?agreement=${kind}` });
}
</script>

<style lang="scss" scoped>
.login {
  min-height: 100vh;
  background: linear-gradient(180deg, #e8efff 0%, #f7f8fa 60%);
  padding: 96rpx 48rpx 48rpx;
  display: flex;
  flex-direction: column;

  &__hero {
    margin-bottom: 64rpx;
  }

  &__brand {
    font-size: 64rpx;
    font-weight: 700;
    color: #3a7afe;
    letter-spacing: 4rpx;
  }

  &__subtitle {
    margin-top: 16rpx;
    font-size: 30rpx;
    color: #4e5969;
  }

  &__panel {
    background: #fff;
    border-radius: 32rpx;
    padding: 56rpx 40rpx;
    box-shadow: 0 8rpx 32rpx rgba(58, 122, 254, 0.12);
  }

  &__title {
    font-size: 40rpx;
    font-weight: 600;
    color: #1f2329;
    margin-bottom: 16rpx;
  }

  &__hint {
    font-size: 26rpx;
    color: #8a8e99;
    line-height: 1.6;
    margin-bottom: 48rpx;
  }

  &__primary {
    height: 88rpx;
    line-height: 88rpx;
    border-radius: 44rpx;
    background: #07c160;
    color: #fff;
    font-size: 32rpx;
    border: none;
    margin-bottom: 24rpx;
  }

  &__secondary {
    height: 88rpx;
    line-height: 88rpx;
    border-radius: 44rpx;
    background: #f2f3f5;
    color: #1f2329;
    font-size: 32rpx;
    border: none;
    margin-bottom: 32rpx;
  }

  &__agreement {
    font-size: 24rpx;
    color: #8a8e99;
    text-align: center;
    line-height: 1.7;
  }

  &__link {
    color: #3a7afe;
  }

  &__footer {
    margin-top: auto;
    text-align: center;
    font-size: 22rpx;
    color: #c9cdd4;
  }
}
</style>