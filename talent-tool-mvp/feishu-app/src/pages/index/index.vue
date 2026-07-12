<template>
  <view class="home">
    <view class="home__hero">
      <view class="home__greeting">
        <text class="home__hello">Feishu Workbench</text>
        <text class="home__sub">{{ greeting }}</text>
      </view>
      <view class="home__corp" v-if="runtime.isFeishu">
        <text class="home__corp-label">Tenant</text>
        <text class="home__corp-id">{{ runtime.appId || '--' }}</text>
      </view>
    </view>

    <view class="home__quick">
      <view v-for="q in quickEntries" :key="q.url" class="home__quick-item" @click="go(q.url)">
        <view class="home__quick-icon" :style="{ background: q.color }">
          <text class="home__quick-text">{{ q.label.charAt(0) }}</text>
        </view>
        <text class="home__quick-label">{{ q.label }}</text>
      </view>
    </view>

    <view class="home__kpis">
      <view class="home__kpi">
        <text class="home__kpi-num">{{ kpis.open }}</text>
        <text class="home__kpi-label">Open</text>
      </view>
      <view class="home__kpi">
        <text class="home__kpi-num">{{ kpis.urgent }}</text>
        <text class="home__kpi-label">Urgent</text>
      </view>
      <view class="home__kpi">
        <text class="home__kpi-num">{{ kpis.synced }}</text>
        <text class="home__kpi-label">Synced</text>
      </view>
    </view>

    <view class="home__section">
      <view class="home__section-head">
        <text class="home__section-title">Recent</text>
        <text class="home__section-extra" @click="go('/pages/tickets/index')">All</text>
      </view>
      <view v-if="!recent.length" class="home__empty">No tickets</view>
      <view v-else>
        <view v-for="t in recent" :key="t.id" class="home__row" @click="onAdvance(t)">
          <view class="home__row-left">
            <text class="home__row-title">{{ t.title }}</text>
            <text class="home__row-meta">{{ t.priority }} · {{ t.updated_at }}</text>
          </view>
          <text class="home__row-status">{{ t.status }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { getRuntime, isFeishu } from '@/utils/lark';

definePage({ navigationStyle: 'custom' });

const runtime = ref(getRuntime());
const recent = ref<Array<{ id: string; title: string; priority: string; status: string; updated_at: string }>>([]);
const kpis = reactive({ open: 0, urgent: 0, synced: 0 });

const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 6) return 'Good night';
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
});

const quickEntries = [
  { label: 'Tickets', url: '/pages/tickets/index', color: '#3370FF' },
  { label: 'Strategy', url: '/pages/strategy/index', color: '#00B42A' },
  { label: 'Approval', url: '', color: '#FF7D00' },
  { label: 'Contacts', url: '', color: '#9B59B6' },
];

function go(url: string): void {
  if (!url) return;
  uni.navigateTo({ url });
}

function onAdvance(t: any): void {
  uni.showToast({ title: 'Updated: ' + t.title, icon: 'success' });
}

onMounted(() => {
  recent.value = [
    { id: 't1', title: 'Python JD review', priority: 'high', status: 'open', updated_at: '2026-07-12' },
    { id: 't2', title: 'Profile audit', priority: 'urgent', status: 'in_progress', updated_at: '2026-07-12' },
    { id: 't3', title: 'Q3 OKR', priority: 'medium', status: 'closed', updated_at: '2026-07-11' },
  ];
  kpis.open = 2;
  kpis.urgent = 1;
  kpis.synced = isFeishu() ? 95 : 0;
});
</script>

<style lang="scss" scoped>
.home { padding: 0 24rpx 32rpx; background: #F7F8FA; min-height: 100vh;
  &__hero { margin: 0 -24rpx 32rpx; padding: 96rpx 32rpx 48rpx; background: #3370FF; color: #fff; display: flex; justify-content: space-between; align-items: flex-end; }
  &__hello { font-size: 44rpx; font-weight: 700; display: block; }
  &__sub { font-size: 26rpx; opacity: 0.85; margin-top: 8rpx; display: block; }
  &__corp { text-align: right; }
  &__corp-label { font-size: 22rpx; opacity: 0.7; display: block; }
  &__corp-id { font-size: 26rpx; display: block; }
  &__quick { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16rpx; background: #fff; border-radius: 24rpx; padding: 32rpx 16rpx; margin-bottom: 32rpx; }
  &__quick-item { display: flex; flex-direction: column; align-items: center; gap: 12rpx; }
  &__quick-icon { width: 80rpx; height: 80rpx; border-radius: 24rpx; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 32rpx; font-weight: 600; }
  &__quick-label { font-size: 24rpx; color: #4E5969; }
  &__kpis { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16rpx; margin-bottom: 32rpx; }
  &__kpi { background: #fff; border-radius: 16rpx; padding: 32rpx 16rpx; text-align: center; }
  &__kpi-num { font-size: 48rpx; font-weight: 700; color: #3370FF; display: block; }
  &__kpi-label { font-size: 22rpx; color: #8A8E99; margin-top: 4rpx; display: block; }
  &__section { background: #fff; border-radius: 16rpx; padding: 24rpx; }
  &__section-head { display: flex; justify-content: space-between; margin-bottom: 16rpx; }
  &__section-title { font-size: 30rpx; font-weight: 600; color: #1F2329; }
  &__section-extra { font-size: 24rpx; color: #3370FF; }
  &__empty { text-align: center; color: #C9CDD4; padding: 48rpx 0; font-size: 24rpx; }
  &__row { display: flex; align-items: center; justify-content: space-between; padding: 20rpx 0; border-bottom: 1rpx solid #F0F1F3; }
  &__row:last-child { border-bottom: none; }
  &__row-left { flex: 1; display: flex; flex-direction: column; }
  &__row-title { font-size: 28rpx; color: #1F2329; }
  &__row-meta { font-size: 22rpx; color: #8A8E99; margin-top: 4rpx; }
  &__row-status { font-size: 22rpx; padding: 4rpx 12rpx; border-radius: 16rpx; background: #F2F3F5; color: #4E5969; }
}
</style>