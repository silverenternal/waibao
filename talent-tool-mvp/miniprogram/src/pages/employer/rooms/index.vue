<template>
  <view class="rooms">
    <view v-if="loading" class="rooms__loading">
      <wb-loading text="加载协同房间..." />
    </view>
    <wb-empty
      v-else-if="!items.length"
      title="暂无协同房间"
      description="与候选人/同事开启一个协同房间,实时跟进"
      action-text="新建房间"
      @action="onCreate"
    />
    <view v-else class="rooms__list">
      <view
        v-for="r in items"
        :key="r.id"
        class="rooms__item"
        @click="onOpen(r)"
      >
        <view class="rooms__title-row">
          <text class="rooms__title">{{ r.title }}</text>
          <view v-if="r.unread" class="rooms__badge">{{ r.unread }}</view>
        </view>
        <view class="rooms__meta">
          <text>{{ r.participant_count }} 人参与</text>
          <text>{{ formatDate(r.last_message_at, false) }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { listRooms, type Room } from '@/api';
import { formatDate } from '@/utils/format';

const items = ref<Room[]>([]);
const loading = ref(false);

function onCreate() {
  uni.showModal({ title: '提示', content: '请到 Web 端创建协同房间' });
}

function onOpen(r: Room) {
  uni.showToast({ title: `打开房间: ${r.title}`, icon: 'none' });
}

onMounted(async () => {
  loading.value = true;
  try {
    const res = await listRooms();
    if (res.ok && res.data) items.value = res.data;
  } finally {
    loading.value = false;
  }
});
</script>

<style lang="scss" scoped>
.rooms {
  padding: 32rpx;

  &__loading {
    padding: 96rpx 0;
  }

  &__item {
    background: #fff;
    border-radius: 24rpx;
    padding: 24rpx;
    margin-bottom: 16rpx;
    box-shadow: 0 4rpx 16rpx rgba(31, 35, 41, 0.06);
  }

  &__title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12rpx;
  }

  &__title {
    font-size: 30rpx;
    font-weight: 600;
    color: #1f2329;
  }

  &__badge {
    min-width: 36rpx;
    height: 36rpx;
    line-height: 36rpx;
    text-align: center;
    background: #f53f3f;
    color: #fff;
    font-size: 22rpx;
    border-radius: 18rpx;
    padding: 0 12rpx;
  }

  &__meta {
    display: flex;
    justify-content: space-between;
    font-size: 24rpx;
    color: #8a8e99;
  }
}
</style>