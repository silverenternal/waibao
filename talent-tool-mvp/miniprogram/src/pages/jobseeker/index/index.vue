<template>
  <view class="js-home">
    <view class="js-home__hero">
      <view class="js-home__greeting">
        <text class="js-home__hello">你好,{{ user?.user?.email?.split('@')[0] || '求职者' }}</text>
        <text class="js-home__date">{{ today }}</text>
      </view>
      <image
        class="js-home__avatar"
        src="https://thirdwx.qlogo.cn/mmopen/vi_32/Q0j4TwGTfTKvXzS4viaYpQ/132"
        mode="aspectFill"
      />
    </view>

    <wb-card title="智能对话" extra="立即进入" @click="goChat" tap>
      <view class="js-home__entry">
        <view class="js-home__entry-icon">AI</view>
        <view class="js-home__entry-text">
          <text class="js-home__entry-title">和招聘智能体聊聊</text>
          <text class="js-home__entry-sub">简历优化 · 岗位匹配 · 面试准备</text>
        </view>
      </view>
    </wb-card>

    <view class="js-home__grid">
      <wb-card title="我的画像" @click="nav('/pages/jobseeker/profile/index')" tap>
        <view class="js-home__metric">
          <text class="js-home__metric-num">{{ profileCompletion }}</text>
          <text class="js-home__metric-label">完整度</text>
        </view>
      </wb-card>
      <wb-card title="职业规划" @click="nav('/pages/jobseeker/plan/index')" tap>
        <view class="js-home__metric">
          <text class="js-home__metric-num">{{ planProgress }}</text>
          <text class="js-home__metric-label">%</text>
        </view>
      </wb-card>
      <wb-card title="工作日记" @click="nav('/pages/jobseeker/journal/index')" tap>
        <view class="js-home__metric">
          <text class="js-home__metric-num">{{ journalCount }}</text>
          <text class="js-home__metric-label">篇</text>
        </view>
      </wb-card>
      <wb-card title="我的工单" @click="nav('/pages/jobseeker/tickets/index')" tap>
        <view class="js-home__metric">
          <text class="js-home__metric-num">{{ openTickets }}</text>
          <text class="js-home__metric-label">进行中</text>
        </view>
      </wb-card>
    </view>

    <wb-card title="今日推荐" extra="换一批">
      <view v-if="loading" class="js-home__loading">
        <wb-loading text="正在为你匹配岗位..." />
      </view>
      <view v-else-if="!recommendations.length">
        <wb-empty
          title="还没有推荐"
          description="完善画像后,智能体会根据你的偏好推荐岗位"
          action-text="去完善画像"
          @action="nav('/pages/jobseeker/profile/index')"
        />
      </view>
      <view v-else class="js-home__rec-list">
        <view
          v-for="job in recommendations"
          :key="job.id"
          class="js-home__rec"
          @click="onApply(job)"
        >
          <view class="js-home__rec-row">
            <text class="js-home__rec-title">{{ job.title }}</text>
            <text class="js-home__rec-score">{{ Math.round(job.score * 100) }}%</text>
          </view>
          <text class="js-home__rec-meta">{{ job.company }} · {{ job.location }}</text>
          <text class="js-home__rec-salary">{{ job.salary }}</text>
        </view>
      </view>
    </wb-card>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useUserStore } from '@/store/user';
import { fetchProfile, listJournal, listMyTickets, fetchPlan } from '@/api';
import { formatDate } from '@/utils/format';

definePage({ navigationStyle: 'custom' });

const user = useUserStore();
const today = formatDate(new Date(), false);
const profileCompletion = ref(60);
const planProgress = ref(0);
const journalCount = ref(0);
const openTickets = ref(0);
const loading = ref(false);
const recommendations = ref<
  Array<{ id: string; title: string; company: string; location: string; salary: string; score: number }>
>([]);

function nav(url: string) {
  uni.navigateTo({ url });
}

function goChat() {
  uni.navigateTo({ url: '/pages/jobseeker/chat/index' });
}

function onApply(job: { id: string; title: string }) {
  uni.showModal({
    title: '投递确认',
    content: `确认投递「${job.title}」吗?`,
    success: ({ confirm }) => {
      if (confirm) uni.showToast({ title: '已加入投递队列', icon: 'success' });
    },
  });
}

onMounted(async () => {
  loading.value = true;
  try {
    const [prof, plan, journal, tickets] = await Promise.all([
      fetchProfile(),
      fetchPlan(),
      listJournal({ limit: 1 }),
      listMyTickets({ status: 'open' }),
    ]);
    if (prof.ok && prof.data) {
      profileCompletion.value = Math.min(
        100,
        40 + (prof.data.skills?.length || 0) * 5 + (prof.data.bio ? 20 : 0)
      );
    }
    if (plan.ok && plan.data) {
      const total = plan.data.milestones?.length || 0;
      const done = plan.data.milestones?.filter((m) => m.status === 'done').length || 0;
      planProgress.value = total ? Math.round((done / total) * 100) : 0;
    }
    if (journal.ok && journal.data) journalCount.value = journal.data.items.length;
    if (tickets.ok && tickets.data) openTickets.value = tickets.data.length;
  } finally {
    loading.value = false;
  }

  // 占位推荐 — 真实环境调用 /api/matches/recommend
  recommendations.value = [
    { id: 'r1', title: '高级前端工程师', company: '某出海 SaaS', location: '杭州', salary: '35-55K · 14 薪', score: 0.92 },
    { id: 'r2', title: '全栈工程师 (Vue/Node)', company: '某 AI 创业公司', location: '远程', salary: '30-50K', score: 0.86 },
    { id: 'r3', title: '技术 PM', company: '某大型互联网', location: '北京', salary: '40-70K', score: 0.78 },
  ];
});
</script>

<style lang="scss" scoped>
.js-home {
  padding: 32rpx;
  padding-top: 96rpx;

  &__hero {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 32rpx;
  }

  &__greeting {
    display: flex;
    flex-direction: column;
  }

  &__hello {
    font-size: 40rpx;
    font-weight: 600;
    color: #1f2329;
  }

  &__date {
    font-size: 26rpx;
    color: #8a8e99;
    margin-top: 8rpx;
  }

  &__avatar {
    width: 96rpx;
    height: 96rpx;
    border-radius: 50%;
    background: #e8efff;
  }

  &__entry {
    display: flex;
    align-items: center;
  }

  &__entry-icon {
    width: 96rpx;
    height: 96rpx;
    border-radius: 32rpx;
    background: linear-gradient(135deg, #3a7afe 0%, #5a8dff 100%);
    color: #fff;
    font-size: 36rpx;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 24rpx;
  }

  &__entry-text {
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  &__entry-title {
    font-size: 32rpx;
    font-weight: 600;
    color: #1f2329;
  }

  &__entry-sub {
    font-size: 24rpx;
    color: #8a8e99;
    margin-top: 6rpx;
  }

  &__grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16rpx;
  }

  &__metric {
    display: flex;
    align-items: baseline;
  }

  &__metric-num {
    font-size: 56rpx;
    font-weight: 700;
    color: #3a7afe;
  }

  &__metric-label {
    margin-left: 8rpx;
    font-size: 24rpx;
    color: #8a8e99;
  }

  &__loading {
    padding: 24rpx 0;
  }

  &__rec-list {
    display: flex;
    flex-direction: column;
  }

  &__rec {
    padding: 24rpx 0;
    border-bottom: 1rpx solid #f0f1f3;

    &:last-child {
      border-bottom: none;
    }
  }

  &__rec-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8rpx;
  }

  &__rec-title {
    font-size: 30rpx;
    font-weight: 600;
    color: #1f2329;
  }

  &__rec-score {
    font-size: 26rpx;
    color: #00b42a;
    font-weight: 600;
  }

  &__rec-meta {
    font-size: 24rpx;
    color: #8a8e99;
  }

  &__rec-salary {
    display: block;
    margin-top: 8rpx;
    font-size: 26rpx;
    color: #ff7d00;
    font-weight: 500;
  }
}
</style>