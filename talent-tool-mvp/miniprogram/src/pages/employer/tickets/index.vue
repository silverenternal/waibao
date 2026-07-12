<template>
  <view class="kanban">
    <view class="kanban__filters">
      <view
        v-for="p in priorityFilters"
        :key="p.value"
        class="kanban__chip"
        :class="{ 'kanban__chip--active': priority === p.value }"
        @click="priority = p.value"
      >
        {{ p.label }}
      </view>
    </view>

    <scroll-view scroll-x class="kanban__board">
      <view class="kanban__col" v-for="col in columns" :key="col.status">
        <view class="kanban__col-head" :style="{ background: col.color }">
          {{ col.label }} ({{ grouped[col.status].length }})
        </view>
        <view class="kanban__col-body">
          <view
            v-for="t in grouped[col.status]"
            :key="t.id"
            class="kanban__card"
            :class="`kanban__card--${t.priority}`"
            @click="advance(t)"
          >
            <text class="kanban__card-title">{{ t.title }}</text>
            <text class="kanban__card-desc">{{ t.description }}</text>
            <view class="kanban__card-foot">
              <text>{{ priorityLabel(t.priority) }}</text>
              <text>{{ formatDate(t.updated_at, false) }}</text>
            </view>
          </view>
          <view v-if="!grouped[col.status].length" class="kanban__empty">暂无</view>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { advanceTicket, listEmployerTickets, type Ticket } from '@/api';
import { formatDate } from '@/utils/format';

const items = ref<Ticket[]>([]);
const priority = ref<'all' | Ticket['priority']>('all');

const priorityFilters = [
  { label: '全部', value: 'all' as const },
  { label: '紧急', value: 'urgent' as const },
  { label: '高', value: 'high' as const },
  { label: '中', value: 'medium' as const },
  { label: '低', value: 'low' as const },
];

const columns = [
  { status: 'open' as Ticket['status'], label: '待处理', color: '#fff1f0' },
  { status: 'in_progress' as Ticket['status'], label: '进行中', color: '#fff7e8' },
  { status: 'blocked' as Ticket['status'], label: '阻塞', color: '#ffe7e7' },
  { status: 'closed' as Ticket['status'], label: '已关闭', color: '#e8f5e9' },
];

const filtered = computed(() => {
  if (priority.value === 'all') return items.value;
  return items.value.filter((t) => t.priority === priority.value);
});

const grouped = computed(() => {
  const map: Record<Ticket['status'], Ticket[]> = {
    open: [],
    in_progress: [],
    blocked: [],
    closed: [],
  };
  for (const t of filtered.value) map[t.status].push(t);
  return map;
});

function priorityLabel(p: Ticket['priority']) {
  return { low: '低', medium: '中', high: '高', urgent: '紧急' }[p] || p;
}

async function advance(t: Ticket) {
  const flow: Record<Ticket['status'], Ticket['status']> = {
    open: 'in_progress',
    in_progress: 'closed',
    blocked: 'in_progress',
    closed: 'closed',
  };
  const next = flow[t.status];
  const res = await advanceTicket(t.id, next);
  if (res.ok) {
    uni.showToast({ title: '已推进', icon: 'success' });
    await refresh();
  }
}

async function refresh() {
  const res = await listEmployerTickets();
  if (res.ok && res.data) items.value = res.data;
}

onMounted(refresh);
</script>

<style lang="scss" scoped>
.kanban {
  padding: 24rpx;

  &__filters {
    display: flex;
    gap: 16rpx;
    margin-bottom: 24rpx;
    flex-wrap: wrap;
  }

  &__chip {
    padding: 12rpx 24rpx;
    background: #fff;
    border-radius: 32rpx;
    font-size: 24rpx;
    color: #4e5969;

    &--active {
      background: #3a7afe;
      color: #fff;
    }
  }

  &__board {
    white-space: nowrap;
    padding-bottom: 24rpx;
  }

  &__col {
    display: inline-block;
    vertical-align: top;
    width: 320rpx;
    margin-right: 16rpx;
    background: #fff;
    border-radius: 16rpx;
    box-shadow: 0 2rpx 8rpx rgba(31, 35, 41, 0.04);
    overflow: hidden;
  }

  &__col-head {
    padding: 16rpx 24rpx;
    font-size: 26rpx;
    font-weight: 600;
    color: #1f2329;
  }

  &__col-body {
    padding: 16rpx;
    min-height: 200rpx;
  }

  &__card {
    background: #f7f8fa;
    border-radius: 12rpx;
    padding: 16rpx;
    margin-bottom: 12rpx;
    border-left: 6rpx solid #c9cdd4;

    &--urgent { border-left-color: #f53f3f; }
    &--high { border-left-color: #ff7d00; }
    &--medium { border-left-color: #3a7afe; }
    &--low { border-left-color: #00b42a; }
  }

  &__card-title {
    display: block;
    font-size: 26rpx;
    font-weight: 600;
    color: #1f2329;
    margin-bottom: 8rpx;
  }

  &__card-desc {
    display: block;
    font-size: 24rpx;
    color: #4e5969;
    line-height: 1.5;
    margin-bottom: 8rpx;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  &__card-foot {
    display: flex;
    justify-content: space-between;
    font-size: 22rpx;
    color: #8a8e99;
  }

  &__empty {
    text-align: center;
    color: #c9cdd4;
    font-size: 24rpx;
    padding: 32rpx 0;
  }
}
</style>