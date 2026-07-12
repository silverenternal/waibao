<template>
  <view class="strategy">
    <view v-if="!root" class="strategy__loading">
      <wb-loading text="加载战略地图..." />
    </view>
    <view v-else class="strategy__canvas">
      <view
        v-for="(p, idx) in perspectives"
        :key="p.key"
        class="strategy__lane"
        :style="{ top: idx * 280 + 'rpx' }"
      >
        <view class="strategy__lane-head" :style="{ background: p.color }">
          {{ p.label }}
        </view>
        <scroll-view scroll-x class="strategy__lane-scroll">
          <view class="strategy__node-list">
            <view
              v-for="node in root.children.filter((c) => c.perspective === p.key)"
              :key="node.id"
              class="strategy__node"
              :style="{ borderColor: p.color }"
              @click="onNode(node)"
            >
              <text class="strategy__node-title">{{ node.title }}</text>
              <view class="strategy__node-bar">
                <view
                  class="strategy__node-fill"
                  :style="{ width: node.progress + '%', background: p.color }"
                />
              </view>
              <text class="strategy__node-pct">{{ node.progress }}%</text>
            </view>
          </view>
        </scroll-view>
      </view>
      <view class="strategy__canvas-spacer" :style="{ height: perspectives.length * 280 + 'rpx' }" />
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { fetchStrategyMap, type StrategyNode } from '@/api';

const root = ref<StrategyNode | null>(null);

const perspectives = [
  { key: 'financial' as const, label: '财务', color: '#3a7afe' },
  { key: 'customer' as const, label: '客户', color: '#00b42a' },
  { key: 'process' as const, label: '流程', color: '#ff7d00' },
  { key: 'learning' as const, label: '学习', color: '#9b59b6' },
];

function onNode(node: StrategyNode) {
  uni.showModal({
    title: node.title,
    content: `当前进度 ${node.progress}%`,
    showCancel: false,
  });
}

onMounted(async () => {
  const res = await fetchStrategyMap();
  if (res.ok && res.data) root.value = res.data.root;
});
</script>

<style lang="scss" scoped>
.strategy {
  padding: 24rpx;

  &__loading {
    padding: 96rpx 0;
  }

  &__canvas {
    position: relative;
  }

  &__lane {
    position: absolute;
    left: 0;
    right: 0;
    height: 240rpx;
  }

  &__lane-head {
    padding: 16rpx 24rpx;
    border-radius: 12rpx 12rpx 0 0;
    color: #fff;
    font-weight: 600;
    font-size: 26rpx;
  }

  &__lane-scroll {
    background: #fff;
    border-radius: 0 0 16rpx 16rpx;
    padding: 16rpx;
    white-space: nowrap;
    box-shadow: 0 2rpx 8rpx rgba(31, 35, 41, 0.04);
  }

  &__node-list {
    display: inline-flex;
    gap: 16rpx;
  }

  &__node {
    display: inline-block;
    vertical-align: top;
    width: 280rpx;
    padding: 16rpx;
    background: #f7f8fa;
    border-radius: 12rpx;
    border-left: 8rpx solid #c9cdd4;
  }

  &__node-title {
    display: block;
    font-size: 26rpx;
    font-weight: 600;
    color: #1f2329;
    margin-bottom: 12rpx;
  }

  &__node-bar {
    height: 8rpx;
    background: #e5e6eb;
    border-radius: 4rpx;
    overflow: hidden;
    margin-bottom: 8rpx;
  }

  &__node-fill {
    height: 100%;
  }

  &__node-pct {
    font-size: 22rpx;
    color: #4e5969;
  }

  &__canvas-spacer {
    width: 100%;
  }
}
</style>