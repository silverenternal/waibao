<script setup lang="ts">
import { onLaunch, onShow, onHide } from '@dcloudio/uni-app';
import { useUserStore } from '@/store/user';

onLaunch(() => {
  console.log('[waibao] App Launch');
  // Auto re-login if we have a cached token but the session is stale.
  const userStore = useUserStore();
  userStore.bootstrap();
});

onShow(() => {
  console.log('[waibao] App Show');
});

onHide(() => {
  console.log('[waibao] App Hide');
});
</script>

<style lang="scss">
/* Global reset & design tokens */
page {
  background-color: #F7F8FA;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Helvetica Neue',
    Helvetica, 'Microsoft YaHei', Arial, sans-serif;
  font-size: 28rpx;
  color: #1F2329;
  line-height: 1.5;
}

view, text, button, input, textarea, image, navigator, scroll-view {
  box-sizing: border-box;
}

/* Design tokens */
:root {
  --wb-color-primary: #3A7AFE;
  --wb-color-primary-soft: #E8EFFF;
  --wb-color-success: #00B42A;
  --wb-color-warning: #FF7D00;
  --wb-color-danger: #F53F3F;
  --wb-color-text: #1F2329;
  --wb-color-text-muted: #8A8E99;
  --wb-color-border: #E5E6EB;
  --wb-color-bg: #F7F8FA;
  --wb-color-card: #FFFFFF;
  --wb-radius-sm: 8rpx;
  --wb-radius-md: 16rpx;
  --wb-radius-lg: 24rpx;
  --wb-shadow-card: 0 4rpx 16rpx rgba(31, 35, 41, 0.06);
}
</style>