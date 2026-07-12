<template>
  <view class="tickets">
    <view class="tickets__tabs">
      <view
        v-for="t in tabs"
        :key="t.value"
        class="tickets__tab"
        :class="{ 'tickets__tab--active': active === t.value }"
        @click="active = t.value"
      >
        {{ t.label }}
      </view>
    </view>

    <view v-if="loading" class="tickets__loading">
      <wb-loading text="加载工单..." />
    </view>
    <wb-empty
      v-else-if="!filtered.length"
      title="暂无工单"
      description="有问题可以向 HR 提工单,获得及时跟进"
      action-text="新建工单"
      @action="onCreate"
    />
    <view v-else class="tickets__list">
      <view
        v-for="t in filtered"
        :key="t.id"
        class="tickets__item"
        :class="`tickets__item--${t.priority}`"
        @click="onOpen(t)"
      >
        <view class="tickets__row">
          <text class="tickets__title">{{ t.title }}</text>
          <text class="tickets__status" :class="`tickets__status--${t.status}`">
            {{ statusLabel(t.status) }}
          </text>
        </view>
        <text class="tickets__desc">{{ t.description }}</text>
        <view class="tickets__meta">
          <text>{{ formatDate(t.updated_at, false) }}</text>
          <text class="tickets__priority">{{ priorityLabel(t.priority) }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { listMyTickets, type Ticket } from '@/api';
import { formatDate } from '@/utils/format';

const items = ref<Ticket[]>([]);
const loading = ref(false);
const active = ref<'all' | Ticket['status']>('all');

const tabs = [
  { label: '全部', value: 'all' as const },
  { label: '进行中', value: 'in_progress' as const },
  { label: '已解决', value: 'closed' as const },
];

const filtered = computed(() => {
  if (active.value === 'all') return items.value;
  return items.value.filter((t) => t.status === active.value);
});

function statusLabel(s: Ticket['status']) {
  return { open: '待处理', in_progress: '进行中', blocked: '阻塞', closed: '已关闭' }[s] || s;
}
function priorityLabel(p: Ticket['priority']) {
  return { low: '低', medium: '中', high: '高', urgent: '紧急' }[p] || p;
}

function onCreate() {
  uni.showModal({ title: '提示', content: '请到 Web 端创建工单 (小程序端暂仅支持查看)' });
}
function onOpen(t: Ticket) {
  uni.showActionSheet({
    itemList: ['查看详情', '催办'],
    success: ({ tapIndex }) => {
      if (tapIndex === 0) uni.showToast({ title: t.title, icon: 'none' });
      if (tapIndex === 1) uni.showToast({ title: '已通知 HR', icon: 'success' });
    },
  });
}

onMounted(async () => {
  loading.value = true;
  try {
    const res = await listMyTickets();
    if (res.ok && res.data) items.value = res.data;
  } finally {
    loading.value = false;
  }
});
</script>

<style lang="scss" scoped>
.tickets {
  padding: 32rpx;

  &__tabs {
    display: flex;
    background: #fff;
    border-radius: 16rpx;
    padding: 8rpx;
    margin-bottom: 24rpx;
  }

  &__tab {
    flex: 1;
    text-align: center;
    padding: 16rpx;
    font-size: 28rpx;
    color: #4e5969;
    border-radius: 12rpx;

    &--active {
      background: #3a7afe;
      color: #fff;
    }
  }

  &__loading {
    padding: 64rpx 0;
  }

  &__item {
    background: #fff;
    border-radius: 24rpx;
    padding: 24rpx;
    margin-bottom: 16rpx;
    box-shadow: 0 4rpx 16rpx rgba(31, 35, 41, 0.06);
    border-left: 8rpx solid #c9cdd4;

    &--urgent { border-left-color: #f53f3f; }
    &--high { border-left-color: #ff7d00; }
    &--medium { border-left-color: #3a7afe; }
    &--low { border-left-color: #00b42a; }
  }

  &__row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8rpx;
  }

  &__title {
    font-size: 30rpx;
    font-weight: 600;
    color: #1f2329;
  }

  &__status {
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

  &__desc {
    font-size: 26rpx;
    color: #4e5969;
    line-height: 1.5;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  &__meta {
    display: flex;
    justify-content: space-between;
    margin-top: 16rpx;
    font-size: 22rpx;
    color: #8a8e99;
  }

  &__priority {
    font-weight: 600;
  }
}
</style>