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
            :class="cardCls(t.priority)"
            @click="advance(t)"
          >
            <text class="kanban__card-title">{{ t.title }}</text>
            <text class="kanban__card-desc">{{ t.description }}</text>
            <view class="kanban__card-foot">
              <text>{{ t.priority }}</text>
              <text>{{ t.updated_at }}</text>
            </view>
          </view>
          <view v-if="!grouped[col.status].length" class="kanban__empty">None</view>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

interface Ticket {
  id: string;
  title: string;
  description: string;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  status: 'open' | 'in_progress' | 'blocked' | 'closed';
  updated_at: string;
}

const items = ref<Ticket[]>([]);
const priority = ref<'all' | Ticket['priority']>('all');

const priorityFilters = [
  { label: 'All', value: 'all' as const },
  { label: 'Urgent', value: 'urgent' as const },
  { label: 'High', value: 'high' as const },
  { label: 'Medium', value: 'medium' as const },
  { label: 'Low', value: 'low' as const },
];

const columns = [
  { status: 'open' as const, label: 'Open', color: '#FFF1F0' },
  { status: 'in_progress' as const, label: 'In Progress', color: '#FFF7E8' },
  { status: 'blocked' as const, label: 'Blocked', color: '#FFE7E7' },
  { status: 'closed' as const, label: 'Closed', color: '#E8F5E9' },
];

const filtered = computed(() =>
  priority.value === 'all'
    ? items.value
    : items.value.filter((t) => t.priority === priority.value)
);

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

function cardCls(p: Ticket['priority']): string {
  return 'kanban__card--' + p;
}

function advance(t: Ticket): void {
  const flow: Record<Ticket['status'], Ticket['status']> = {
    open: 'in_progress',
    in_progress: 'closed',
    blocked: 'in_progress',
    closed: 'closed',
  };
  const idx = items.value.findIndex((x) => x.id === t.id);
  if (idx >= 0) {
    items.value[idx].status = flow[t.status];
    items.value[idx].updated_at = new Date().toISOString().slice(0, 10);
  }
  uni.showToast({ title: 'Advanced', icon: 'success' });
}

onMounted(() => {
  items.value = [
    { id: 't1', title: 'Python JD review', description: 'Client K8s required', priority: 'high', status: 'open', updated_at: '2026-07-12' },
    { id: 't2', title: 'Profile audit', description: 'L4 skill gap', priority: 'urgent', status: 'in_progress', updated_at: '2026-07-12' },
    { id: 't3', title: 'Q3 OKR', description: '4 KPIs pending', priority: 'medium', status: 'closed', updated_at: '2026-07-11' },
  ];
});
</script>

<style lang="scss" scoped>
.kanban { padding: 24rpx;
  &__filters { display: flex; gap: 16rpx; margin-bottom: 24rpx; flex-wrap: wrap; }
  &__chip { padding: 12rpx 24rpx; background: #fff; border-radius: 32rpx; font-size: 24rpx; color: #4E5969; }
  &__chip--active { background: #3370FF; color: #fff; }
  &__board { white-space: nowrap; padding-bottom: 24rpx; }
  &__col { display: inline-block; vertical-align: top; width: 320rpx; margin-right: 16rpx; background: #fff; border-radius: 16rpx; overflow: hidden; }
  &__col-head { padding: 16rpx 24rpx; font-size: 26rpx; font-weight: 600; color: #1F2329; }
  &__col-body { padding: 16rpx; min-height: 200rpx; }
  &__card { background: #F7F8FA; border-radius: 12rpx; padding: 16rpx; margin-bottom: 12rpx; border-left: 6rpx solid #C9CDD4; }
  &__card--urgent { border-left-color: #F53F3F; }
  &__card--high { border-left-color: #FF7D00; }
  &__card--medium { border-left-color: #3370FF; }
  &__card--low { border-left-color: #00B42A; }
  &__card-title { display: block; font-size: 26rpx; font-weight: 600; color: #1F2329; margin-bottom: 8rpx; }
  &__card-desc { display: block; font-size: 22rpx; color: #4E5969; line-height: 1.5; margin-bottom: 8rpx; }
  &__card-foot { display: flex; justify-content: space-between; font-size: 22rpx; color: #8A8E99; }
  &__empty { text-align: center; color: #C9CDD4; font-size: 24rpx; padding: 32rpx 0; }
}
</style>