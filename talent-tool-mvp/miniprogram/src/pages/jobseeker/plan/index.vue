<template>
  <view class="plan">
    <wb-card v-if="plan" :title="plan.title" :extra="`${plan.horizon_months} 个月`">
      <view class="plan__progress">
        <text class="plan__progress-num">{{ progress }}%</text>
        <view class="plan__bar">
          <view class="plan__bar-fill" :style="{ width: progress + '%' }" />
        </view>
      </view>

      <view class="plan__milestones">
        <view
          v-for="m in plan.milestones"
          :key="m.id"
          class="plan__milestone"
          :class="`plan__milestone--${m.status}`"
          @click="toggleMilestone(m.id)"
        >
          <view class="plan__dot" />
          <view class="plan__body">
            <text class="plan__milestone-title">{{ m.title }}</text>
            <text class="plan__milestone-date">{{ formatDate(m.target_date, false) }}</text>
          </view>
          <text class="plan__status">{{ statusLabel(m.status) }}</text>
        </view>
      </view>
    </wb-card>

    <wb-empty
      v-else
      title="尚未生成职业规划"
      description="完成画像后,智能体会自动生成一份专属职业规划"
      action-text="去完善画像"
      @action="nav('/pages/jobseeker/profile/index')"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { fetchPlan, type CareerPlan } from '@/api';
import { formatDate } from '@/utils/format';

const plan = ref<CareerPlan | null>(null);

const progress = computed(() => {
  if (!plan.value?.milestones?.length) return 0;
  const done = plan.value.milestones.filter((m) => m.status === 'done').length;
  return Math.round((done / plan.value.milestones.length) * 100);
});

function statusLabel(s: string) {
  return { pending: '待开始', in_progress: '进行中', done: '已完成' }[s] || s;
}

function toggleMilestone(id: string) {
  if (!plan.value) return;
  // 本地切换状态;真实环境应调用 /api/career-plan/milestone/:id 推进
  const m = plan.value.milestones.find((x) => x.id === id);
  if (!m) return;
  m.status = m.status === 'done' ? 'in_progress' : 'done';
}

function nav(url: string) {
  uni.navigateTo({ url });
}

onMounted(async () => {
  const res = await fetchPlan();
  if (res.ok && res.data) plan.value = res.data;
});
</script>

<style lang="scss" scoped>
.plan {
  padding: 32rpx;

  &__progress {
    display: flex;
    align-items: center;
    margin-bottom: 24rpx;
  }

  &__progress-num {
    font-size: 40rpx;
    font-weight: 700;
    color: #3a7afe;
    margin-right: 16rpx;
  }

  &__bar {
    flex: 1;
    height: 16rpx;
    background: #f2f3f5;
    border-radius: 8rpx;
    overflow: hidden;
  }

  &__bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #3a7afe, #00b42a);
  }

  &__milestones {
    margin-top: 16rpx;
  }

  &__milestone {
    display: flex;
    align-items: center;
    padding: 20rpx 0;
    border-bottom: 1rpx solid #f0f1f3;

    &:last-child {
      border-bottom: none;
    }
  }

  &__dot {
    width: 20rpx;
    height: 20rpx;
    border-radius: 50%;
    background: #c9cdd4;
    margin-right: 16rpx;
  }

  &__milestone--in_progress &__dot { background: #ff7d00; }
  &__milestone--done &__dot { background: #00b42a; }

  &__body {
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  &__milestone-title {
    font-size: 28rpx;
    color: #1f2329;
  }

  &__milestone-date {
    font-size: 22rpx;
    color: #8a8e99;
    margin-top: 4rpx;
  }

  &__status {
    font-size: 24rpx;
    color: #8a8e99;
  }

  &__milestone--in_progress &__status { color: #ff7d00; }
  &__milestone--done &__status { color: #00b42a; }
}
</style>