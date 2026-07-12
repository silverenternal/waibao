<template>
  <view class="strategy">
    <view v-if="!root" class="strategy__loading">Loading...</view>
    <view v-else>
      <view
        v-for="(p, idx) in perspectives"
        :key="p.key"
        class="strategy__lane"
        :style="{ top: (idx * 280) + 'rpx' }"
      >
        <view class="strategy__lane-head" :style="{ background: p.color }">
          {{ p.label }}
        </view>
        <scroll-view scroll-x class="strategy__lane-scroll">
          <view class="strategy__node-list">
            <view
              v-for="node in nodesFor(p.key)"
              :key="node.id"
              class="strategy__node"
              :style="{ borderColor: p.color }"
              @click="onNode(node)"
            >
              <text class="strategy__node-title">{{ node.title }}</text>
              <view class="strategy__node-bar">
                <view class="strategy__node-fill" :style="{ width: node.progress + '%', background: p.color }" />
              </view>
              <text class="strategy__node-pct">{{ node.progress }}%</text>
            </view>
          </view>
        </scroll-view>
      </view>
      <view class="strategy__spacer" :style="{ height: (perspectives.length * 280) + 'rpx' }" />
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';

type Perspective = 'financial' | 'customer' | 'process' | 'learning';

interface Node {
  id: string; title: string; perspective: Perspective; progress: number;
}

const root = ref<{ children: Node[] } | null>(null);

const perspectives = [
  { key: 'financial' as const, label: 'Financial', color: '#3370FF' },
  { key: 'customer' as const, label: 'Customer', color: '#00B42A' },
  { key: 'process' as const, label: 'Process', color: '#FF7D00' },
  { key: 'learning' as const, label: 'Learning', color: '#9B59B6' },
];

function nodesFor(key: Perspective): Node[] {
  return (root.value?.children || []).filter((n) => n.perspective === key);
}

function onNode(n: Node): void {
  uni.showModal({ title: n.title, content: 'Progress ' + n.progress + '%', showCancel: false });
}

onMounted(() => {
  root.value = {
    children: [
      { id: 'f1', title: 'GMV 100M', perspective: 'financial', progress: 62 },
      { id: 'f2', title: 'Margin 35%', perspective: 'financial', progress: 41 },
      { id: 'c1', title: 'NPS 70', perspective: 'customer', progress: 78 },
      { id: 'c2', title: 'Retention 90%', perspective: 'customer', progress: 55 },
      { id: 'p1', title: 'Time-to-hire < 14d', perspective: 'process', progress: 88 },
      { id: 'p2', title: 'Bot 80%', perspective: 'process', progress: 47 },
      { id: 'l1', title: 'Training', perspective: 'learning', progress: 33 },
      { id: 'l2', title: 'AI L4', perspective: 'learning', progress: 60 },
    ],
  };
});
</script>

<style lang="scss" scoped>
.strategy { padding: 24rpx; position: relative;
  &__loading { padding: 96rpx 0; text-align: center; color: #8A8E99; }
  &__lane { position: absolute; left: 24rpx; right: 24rpx; height: 240rpx; }
  &__lane-head { padding: 16rpx 24rpx; border-radius: 12rpx 12rpx 0 0; color: #fff; font-weight: 600; font-size: 26rpx; }
  &__lane-scroll { background: #fff; border-radius: 0 0 16rpx 16rpx; padding: 16rpx; white-space: nowrap; }
  &__node-list { display: inline-flex; gap: 16rpx; }
  &__node { display: inline-block; vertical-align: top; width: 280rpx; padding: 16rpx; background: #F7F8FA; border-radius: 12rpx; border-left: 8rpx solid #C9CDD4; }
  &__node-title { display: block; font-size: 26rpx; font-weight: 600; color: #1F2329; margin-bottom: 12rpx; }
  &__node-bar { height: 8rpx; background: #E5E6EB; border-radius: 4rpx; overflow: hidden; margin-bottom: 8rpx; }
  &__node-fill { height: 100%; }
  &__node-pct { font-size: 22rpx; color: #4E5969; }
  &__spacer { width: 100%; }
}
</style>