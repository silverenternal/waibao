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
            :class="kanbanCardCls(t.priority)"
            @click="advance(t)"
          >
            <text class="kanban__card-title">{{ t.title }}</text>
            <text class="kanban__card-desc">{{ t.description }}</text>
            <view class="kanban__card-foot">
              <text>{{ priorityLabel(t.priority) }}</text>
              <text>{{ t.updated_at }}</text>
            </view>
          </view>
          <view v-if="!grouped[col.status].length" class="kanban__empty">No items</view>
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
  { label: 'All', value: 'all' },
  { label: 'Urgent', value: 'urgent' },
  { label: 'High', value: 'high' },
  { label: 'Medium', value: 'medium' },
  { label: 'Low', value: 'low' },
];

const columns = [
  { status: 'open' as Ticket['status'], label: 'Open', color: '#FFF1F0' },
  { status: 'in_progress' as Ticket['status'], label: 'In Progress', color: '#FFF7E8' },
  { status: 'blocked' as Ticket['status'], label: 'Blocked', color: '#FFE7E7' },
  { status: 'closed' as Ticket['status'], label: 'Closed', color: '#E8F5E9' },
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

function priorityLabel(p: Ticket['priority']): string {
  return ({ low: 'L', medium: 'M', high: 'H', urgent: 'U' } as Record<Ticket['priority'], string>)[p] || p;
}

function kanbanCardCls(p: Ticket['priority']): string {
  return 'kanban__card--' + p;
}

function advance(t: Ticket): void {
  const flow: Record<Ticket['status'], Ticket['status']> = {
    open: 'in_progress',
    in_progress: 'closed',
    blocked: 'in_progress',
    closed: 'closed',
  };
  const next = flow[t.status];
  const idx = items.value.findIndex((x) => x.id === t.id);
  if (idx >= 0) {
    items.value[idx].status = next;
    items.value[idx].updated_at = new Date().toISOString().slice(0, 16).replace('T', ' ');
  }
  uni.showToast({ title: 'Advanced', icon: 'success' });
}

onMounted(() => {
  items.value = [
    { id: 't1', title: 'Senior Python JD review', description: 'Client requests K8s experience', priority: 'high', status: 'open', updated_at: '2026-07-12' },
    { id: 't2', title: 'Candidate profile audit', description: 'L4 skill gap', priority: 'urgent', status: 'in_progress', updated_at: '2026-07-12' },
    { id: 't3', title: 'Q3 OKR confirm', description: '4 KPIs pending', priority: 'medium', status: 'closed', updated_at: '2026-07-11' },
  ];
});
</script>

<style lang="scss" scoped>
.kanban {
  padding: 24rpx;
  &__filters { display: flex; gap: 16rpx; margin-bottom: 24rpx; flex-wrap: wrap; }
  &__chip { padding: 12rpx 24rpx; background: #fff; border-radius: 32rpx; font-size: 24rpx; color: #4E5969; }
  &__chip--active { background: #1772F6; color: #fff; }
  &__board { white-space: nowrap; padding-bottom: 24rpx; }
  &__col { display: inline-block; vertical-align: top; width: 320rpx; margin-right: 16rpx; background: #fff; border-radius: 16rpx; overflow: hidden; box-shadow: 0 2rpx 8rpx rgba(31,35,41,0.04); }
  &__col-head { padding: 16rpx 24rpx; font-size: 26rpx; font-weight: 600; color: #1F2329; }
  &__col-body { padding: 16rpx; min-height: 200rpx; }
  &__card { background: #F7F8FA; border-radius: 12rpx; padding: 16rpx; margin-bottom: 12rpx; border-left: 6rpx solid #C9CDD4; }
  &__card--urgent { border-left-color: #F53F3F; }
  &__card--high { border-left-color: #FF7D00; }
  &__card--medium { border-left-color: #1772F6; }
  &__card--low { border-left-color: #00B42A; }
  &__card-title { display: block; font-size: 26rpx; font-weight: 600; color: #1F2329; margin-bottom: 8rpx; }
  &__card-desc { display: block; font-size: 22rpx; color: #4E5969; line-height: 1.5; margin-bottom: 8rpx; overflow: hidden; text-overflow: ellipsis; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  &__card-foot { display: flex; justify-content: space-between; font-size: 22rpx; color: #8A8E99; }
  &__empty { text-align: center; color: #C9CDD4; font-size: 24rpx; padding: 32rpx 0; }
}
</style>
