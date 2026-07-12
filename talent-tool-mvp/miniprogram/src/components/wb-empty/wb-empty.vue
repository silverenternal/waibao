<template>
  <view class="wb-empty">
    <view class="wb-empty__icon">{{ icon }}</view>
    <view class="wb-empty__title">{{ title }}</view>
    <view v-if="description" class="wb-empty__desc">{{ description }}</view>
    <button v-if="actionText" class="wb-empty__action" @click="$emit('action')">
      {{ actionText }}
    </button>
  </view>
</template>

<script setup lang="ts">
defineProps<{
  icon?: string;
  title: string;
  description?: string;
  actionText?: string;
}>();
defineEmits<{ (e: 'action'): void }>();
</script>

<style lang="scss" scoped>
.wb-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 96rpx 32rpx;
  color: #8a8e99;

  &__icon {
    font-size: 96rpx;
    margin-bottom: 24rpx;
  }

  &__title {
    font-size: 32rpx;
    color: #1f2329;
    margin-bottom: 12rpx;
  }

  &__desc {
    font-size: 26rpx;
    line-height: 1.6;
    text-align: center;
    max-width: 560rpx;
  }

  &__action {
    margin-top: 32rpx;
    padding: 0 48rpx;
    height: 72rpx;
    line-height: 72rpx;
    border-radius: 36rpx;
    background: #3a7afe;
    color: #fff;
    font-size: 28rpx;
    border: none;
  }
}
</style>