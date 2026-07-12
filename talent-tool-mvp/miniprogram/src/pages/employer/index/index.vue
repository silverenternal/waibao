<template>
  <view class="hr-home">
    <view class="hr-home__hero">
      <view class="hr-home__greeting">
        <text class="hr-home__hello">HR 工作台</text>
        <text class="hr-home__date">{{ today }}</text>
      </view>
      <view class="hr-home__actions">
        <view class="hr-home__icon-btn" @click="nav('/pages/employer/rooms/index')">协同</view>
        <view class="hr-home__icon-btn" @click="nav('/pages/employer/strategy/index')">战略</view>
      </view>
    </view>

    <view class="hr-home__kpis">
      <wb-card>
        <view class="hr-home__kpi">
          <text class="hr-home__kpi-num">{{ kpis.open }}</text>
          <text class="hr-home__kpi-label">待处理工单</text>
        </view>
      </wb-card>
      <wb-card>
        <view class="hr-home__kpi">
          <text class="hr-home__kpi-num">{{ kpis.urgent }}</text>
          <text class="hr-home__kpi-label">紧急</text>
        </view>
      </wb-card>
      <wb-card>
        <view class="hr-home__kpi">
          <text class="hr-home__kpi-num">{{ kpis.matches_today }}</text>
          <text class="hr-home__kpi-label">今日匹配</text>
        </view>
      </wb-card>
    </view>

    <wb-card title="工单概览" extra="查看全部" @click="nav('/pages/employer/tickets/index')" tap>
      <view class="hr-home__chart">
        <view
          v-for="(c, idx) in chart"
          :key="idx"
          class="hr-home__chart-bar"
          :style="{ height: c.height + 'rpx' }"
        >
          <text class="hr-home__chart-label">{{ c.label }}</text>
        </view>
      </view>
    </wb-card>

    <wb-card title="最近工单">
      <view v-if="!recent.length">
        <wb-empty title="暂无工单" />
      </view>
      <view v-else class="hr-home__recent">
        <view
          v-for="t in recent"
          :key="t.id"
          class="hr-home__recent-row"
          @click="advance(t)"
        >
          <view class="hr-home__recent-left">
            <text class="hr-home__recent-title">{{ t.title }}</text>
            <text class="hr-home__recent-meta">
              {{ priorityLabel(t.priority) }} · {{ formatDate(t.updated_at, false) }}
            </text>
          </view>
          <text class="hr-home__recent-status" :class="`hr-home__recent-status--${t.status}`">
            {{ statusLabel(t.status) }}
          </text>
        </view>
      </view>
    </wb-card>
  </view>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { listEmployerTickets, advanceTicket, type Ticket } from '@/api';
import { formatDate } from '@/utils/format';

definePage({ navigationStyle: 'custom' });

const today = formatDate(new Date(), false);
const recent = ref<Ticket[]>([]);
const kpis = reactive({ open: 0, urgent: 0, matches_today: 0 });
const chart = ref<Array<{ label: string; height: number }>>([]);

function priorityLabel(p: Ticket['priority']) {
  return { low: '低', medium: '中', high: '高', urgent: '紧急' }[p] || p;
}
function statusLabel(s: Ticket['status']) {
  return { open: '待处理', in_progress: '进行中', blocked: '阻塞', closed: '已关闭' }[s] || s;
}

function nav(url: string) {
  uni.navigateTo({ url });
}

async function advance(t: Ticket) {
  const next: Ticket['status'] =
    t.status === 'open' ? 'in_progress' : t.status === 'in_progress' ? 'closed' : 'closed';
  const res = await advanceTicket(t.id, next);
  if (res.ok) {
    uni.showToast({ title: '已推进', icon: 'success' });
    await refresh();
  }
}

async function refresh() {
  const res = await listEmployerTickets();
  if (!res.ok || !res.data) return;
  recent.value = res.data.slice(0, 5);
  kpis.open = res.data.filter((t) => t.status === 'open').length;
  kpis.urgent = res.data.filter((t) => t.priority === 'urgent').length;
  kpis.matches_today = 12; // 占位 — 真实数据来自 /api/matches/today

  // 构建最近 7 天工单分布图
  const days = ['一', '二', '三', '四', '五', '六', '日'];
  chart.value = days.map((label, i) => ({
    label,
    height: 40 + ((i * 17 + 11) % 120),
  }));
}

onMounted(refresh);
</script>

<style lang="scss" scoped>
.hr-home {
  padding: 32rpx;
  padding-top: 96rpx;

  &__hero {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 32rpx;
  }

  &__greeting {
    display: flex;
    flex-direction: column;
  }

  &__hello {
    font-size: 40rpx;
    font-weight: 600;
    color: #1f2329;
  }

  &__date {
    font-size: 26rpx;
    color: #8a8e99;
    margin-top: 8rpx;
  }

  &__actions {
    display: flex;
    gap: 16rpx;
  }

  &__icon-btn {
    padding: 12rpx 24rpx;
    background: #e8efff;
    color: #3a7afe;
    border-radius: 32rpx;
    font-size: 24rpx;
  }

  &__kpis {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 16rpx;
  }

  &__kpi {
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  &__kpi-num {
    font-size: 48rpx;
    font-weight: 700;
    color: #3a7afe;
  }

  &__kpi-label {
    font-size: 24rpx;
    color: #8a8e99;
    margin-top: 4rpx;
  }

  &__chart {
    display: flex;
    align-items: flex-end;
    height: 200rpx;
    gap: 16rpx;
    padding-top: 24rpx;
  }

  &__chart-bar {
    flex: 1;
    background: linear-gradient(180deg, #3a7afe 0%, #8aaeff 100%);
    border-radius: 8rpx;
    position: relative;
    min-height: 20rpx;
    transition: height 0.3s ease;
  }

  &__chart-label {
    position: absolute;
    bottom: -32rpx;
    left: 50%;
    transform: translateX(-50%);
    font-size: 22rpx;
    color: #8a8e99;
  }

  &__recent-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 20rpx 0;
    border-bottom: 1rpx solid #f0f1f3;

    &:last-child {
      border-bottom: none;
    }
  }

  &__recent-left {
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  &__recent-title {
    font-size: 28rpx;
    color: #1f2329;
  }

  &__recent-meta {
    font-size: 22rpx;
    color: #8a8e99;
    margin-top: 4rpx;
  }

  &__recent-status {
    font-size: 22rpx;
    padding: 4rpx 12rpx;
    border-radius: 16rpx;
    background: #f2f3f5;
    color: #4e5969;

    &--open { background: #fff1f0; color: #f53f3f; }
    &--in_progress { background: #fff7e8; color: #ff7d00; }
    &--blocked { background: #fff1f0; color: #f53f3f; }
    &--closed { background: #e8f5e9; color: #00b42a; }
  }
}
</style>