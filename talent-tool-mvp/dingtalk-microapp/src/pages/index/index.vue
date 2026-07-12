<template>
  <view class="home">
    <view class="home__hero" :style="{ background: '#1772F6' }">
      <view class="home__greeting">
        <text class="home__hello">钉钉工作台</text>
        <text class="home__sub">{{ greeting }}</text>
      </view>
      <view class="home__corp" v-if="runtime.isDingTalk">
        <text class="home__corp-label">企业</text>
        <text class="home__corp-id">{{ runtime.appId || '--' }}</text>
      </view>
    </view>

    <view class="home__quick">
      <view
        v-for="q in quickEntries"
        :key="q.url"
        class="home__quick-item"
        @click="go(q.url)"
      >
        <view class="home__quick-icon" :style="{ background: q.color }">
          <text class="home__quick-text">{{ q.label.charAt(0) }}</text>
        </view>
        <text class="home__quick-label">{{ q.label }}</text>
      </view>
    </view>

    <view class="home__kpis">
      <view class="home__kpi">
        <text class="home__kpi-num">{{ kpis.open }}</text>
        <text class="home__kpi-label">待处理工单</text>
      </view>
      <view class="home__kpi">
        <text class="home__kpi-num">{{ kpis.urgent }}</text>
        <text class="home__kpi-label">紧急</text>
      </view>
      <view class="home__kpi">
        <text class="home__kpi-num">{{ kpis.synced }}</text>
        <text class="home__kpi-label">同步用户</text>
      </view>
    </view>

    <view class="home__section">
      <view class="home__section-head">
        <text class="home__section-title">最近工单</text>
        <text class="home__section-extra" @click="go('/pages/tickets/index')">查看全部</text>
      </view>
      <view v-if="!recent.length" class="home__empty">暂无工单</view>
      <view v-else class="home__list">
        <view
          v-for="t in recent"
          :key="t.id"
          class="home__row"
          @click="onAdvance(t)"
        >
          <view class="home__row-left">
            <text class="home__row-title">{{ t.title }}</text>
            <text class="home__row-meta">
              {{ priorityLabel(t.priority) }} · {{ t.updated_at }}
            </text>
          </view>
          <text class="home__row-status" :class="`home__row-status--${t.status}`">
            {{ statusLabel(t.status) }}
          </text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { getRuntime, isDingTalk } from '@/utils/dd';

definePage({ navigationStyle: 'custom' });

interface Ticket {
  id: string;
  title: string;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  status: 'open' | 'in_progress' | 'blocked' | 'closed';
  updated_at: string;
}

const runtime = ref(getRuntime());
const recent = ref<Ticket[]>([]);
const kpis = reactive({ open: 0, urgent: 0, synced: 0 });

const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 6) return '凌晨好';
  if (h < 12) return '上午好';
  if (h < 18) return '下午好';
  return '晚上好';
});

const quickEntries = [
  { label: '工单', url: '/pages/tickets/index', color: '#1772F6' },
  { label: '战略', url: '/pages/strategy/index', color: '#00B42A' },
  { label: '审批', url: '', color: '#FF7D00' },
  { label: '通讯录', url: '', color: '#9B59B6' },
];

function priorityLabel(p: Ticket['priority']): string {
  return ({ low: '低', medium: '中', high: '高', urgent: '紧急' } as const)[p] || p;
}
function statusLabel(s: Ticket['status']): string {
  return ({ open: '待处理', in_progress: '进行中', blocked: '阻塞', closed: '已关闭' } as const)[s] || s;
}

function go(url: string): void {
  if (!url) return;
  uni.navigateTo({ url });
}

function onAdvance(t: Ticket): void {
  const flow: Record<Ticket['status'], Ticket['status']> = {
    open: 'in_progress',
    in_progress: 'closed',
    blocked: 'in_progress',
    closed: 'closed',
  };
  uni.showToast({ title: `已推进到 ${statusLabel(flow[t.status])}`, icon: 'success' });
}

onMounted(() => {
  // 占位数据 — 真实环境通过 uni.request 拉 /api/tickets
  recent.value = [
    { id: 't1', title: '高级 Python 工程师 JD 复核', priority: 'high', status: 'open', updated_at: '2026-07-12 10:21' },
    { id: 't2', title: '候选人画像校对', priority: 'urgent', status: 'in_progress', updated_at: '2026-07-12 09:55' },
    { id: 't3', title: '战略地图 Q3 OKR 确认', priority: 'medium', status: 'closed', updated_at: '2026-07-11 18:30' },
  ];
  kpis.open = 2;
  kpis.urgent = 1;
  kpis.synced = isDingTalk() ? 128 : 0;
});
</script>

<style lang="scss" scoped>
.home {
  padding: 0 24rpx 32rpx;
  background-color: #F7F8FA;
  min-height: 100vh;

  &__hero {
    margin: 0 -24rpx 32rpx;
    padding: 96rpx 32rpx 48rpx;
    color: #fff;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }

  &__hello {
    font-size: 44rpx;
    font-weight: 700;
    display: block;
  }
  &__sub {
    font-size: 26rpx;
    opacity: 0.85;
    margin-top: 8rpx;
    display: block;
  }

  &__corp {
    text-align: right;
  }
  &__corp-label {
    font-size: 22rpx;
    opacity: 0.7;
    display: block;
  }
  &__corp-id {
    font-size: 26rpx;
    display: block;
  }

  &__quick {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16rpx;
    background: #fff;
    border-radius: 24rpx;
    padding: 32rpx 16rpx;
    margin-bottom: 32rpx;
    box-shadow: 0 4rpx 16rpx rgba(31, 35, 41, 0.06);
  }
  &__quick-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12rpx;
  }
  &__quick-icon {
    width: 80rpx;
    height: 80rpx;
    border-radius: 24rpx;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-size: 32rpx;
    font-weight: 600;
  }
  &__quick-text {
    color: #fff;
  }
  &__quick-label {
    font-size: 24rpx;
    color: #4E5969;
  }

  &__kpis {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 16rpx;
    margin-bottom: 32rpx;
  }
  &__kpi {
    background: #fff;
    border-radius: 16rpx;
    padding: 32rpx 16rpx;
    text-align: center;
    box-shadow: 0 4rpx 16rpx rgba(31, 35, 41, 0.06);
  }
  &__kpi-num {
    font-size: 48rpx;
    font-weight: 700;
    color: #1772F6;
    display: block;
  }
  &__kpi-label {
    font-size: 22rpx;
    color: #8A8E99;
    margin-top: 4rpx;
    display: block;
  }

  &__section {
    background: #fff;
    border-radius: 16rpx;
    padding: 24rpx;
    box-shadow: 0 4rpx 16rpx rgba(31, 35, 41, 0.06);
  }
  &__section-head {
    display: flex;
    justify-content: space-between;
    margin-bottom: 16rpx;
  }
  &__section-title {
    font-size: 30rpx;
    font-weight: 600;
    color: #1F2329;
  }
  &__section-extra {
    font-size: 24rpx;
    color: #1772F6;
  }
  &__empty {
    text-align: center;
    color: #C9CDD4;
    padding: 48rpx 0;
    font-size: 24rpx;
  }
  &__list {
    display: flex;
    flex-direction: column;
  }
  &__row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 20rpx 0;
    border-bottom: 1rpx solid #F0F1F3;

    &:last-child {
      border-bottom: none;
    }
  }
  &__row-left {
    flex: 1;
    display: flex;
    flex-direction: column;
  }
  &__row-title {
    font-size: 28rpx;
    color: #1F2329;
  }
  &__row-meta {
    font-size: 22rpx;
    color: #8A8E99;
    margin-top: 4rpx;
  }
  &__row-status {
    font-size: 22rpx;
    padding: 4rpx 12rpx;
    border-radius: 16rpx;
    background: #F2F3F5;
    color: #4E5969;

    &--open { background: #FFF1F0; color: #F53F3F; }
    &--in_progress { background: #FFF7E8; color: #FF7D00; }
    &--blocked { background: #FFE7E7; color: #F53F3F; }
    &--closed { background: #E8F5E9; color: #00B42A; }
  }
}
</style>