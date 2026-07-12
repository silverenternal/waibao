<template>
  <view class="wb-card" :class="{ 'wb-card--tap': tap }" @click="onClick">
    <view v-if="$slots.header || title" class="wb-card__header">
      <slot name="header">
        <text class="wb-card__title">{{ title }}</text>
      </slot>
      <view v-if="extra" class="wb-card__extra">{{ extra }}</view>
    </view>
    <view class="wb-card__body">
      <slot />
    </view>
    <view v-if="$slots.footer" class="wb-card__footer">
      <slot name="footer" />
    </view>
  </view>
</template>

<script setup lang="ts">
defineProps<{
  title?: string;
  extra?: string;
  tap?: boolean;
}>();
const emit = defineEmits<{ (e: 'click'): void }>();
function onClick() {
  emit('click');
}
</script>

<style lang="scss" scoped>
.wb-card {
  background: var(--wb-color-card, #fff);
  border-radius: 24rpx;
  padding: 32rpx;
  box-shadow: 0 4rpx 16rpx rgba(31, 35, 41, 0.06);
  margin-bottom: 24rpx;

  &--tap:active {
    transform: scale(0.98);
    opacity: 0.9;
  }

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24rpx;
  }

  &__title {
    font-size: 32rpx;
    font-weight: 600;
    color: #1f2329;
  }

  &__extra {
    font-size: 26rpx;
    color: #3a7afe;
  }

  &__footer {
    margin-top: 24rpx;
    padding-top: 24rpx;
    border-top: 1rpx solid #e5e6eb;
  }
}
</style>