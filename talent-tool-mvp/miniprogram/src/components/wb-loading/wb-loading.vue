<template>
  <view class="wb-loading" :class="{ 'wb-loading--inline': inline }">
    <view class="wb-loading__spinner" />
    <view v-if="text" class="wb-loading__text">{{ text }}</view>
  </view>
</template>

<script setup lang="ts">
defineProps<{ text?: string; inline?: boolean }>();
</script>

<style lang="scss" scoped>
.wb-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48rpx 0;

  &--inline {
    padding: 0;
    flex-direction: row;
  }

  &__spinner {
    width: 48rpx;
    height: 48rpx;
    border: 4rpx solid #e8efff;
    border-top-color: #3a7afe;
    border-radius: 50%;
    animation: wb-spin 0.9s linear infinite;
  }

  &__text {
    margin-top: 16rpx;
    font-size: 26rpx;
    color: #8a8e99;
  }
}

@keyframes wb-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>