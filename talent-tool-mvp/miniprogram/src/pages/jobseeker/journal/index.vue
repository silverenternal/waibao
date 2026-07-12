<template>
  <view class="journal">
    <view class="journal__composer">
      <textarea
        v-model="draft"
        class="journal__textarea"
        placeholder="今天有什么心得或进展?写下来,AI 会帮你分析情绪和成长轨迹..."
      />
      <view class="journal__actions">
        <view class="journal__action" @click="toggleRecord">
          {{ recording ? '停止录音' : '语音录入' }}
        </view>
        <view class="journal__action" @click="save(false)">保存文字</view>
        <view class="journal__action journal__action--primary" @click="save(true)">保存并分析</view>
      </view>
      <view v-if="recording" class="journal__recording">
        <view class="journal__rec-dot" />
        正在录音... {{ recordSeconds }}s
      </view>
    </view>

    <view class="journal__list">
      <view v-if="loading" class="journal__loading">
        <wb-loading text="加载日记..." />
      </view>
      <wb-empty
        v-else-if="!items.length"
        title="还没有日记"
        description="写第一篇日记,让 AI 帮你识别职业发展轨迹"
      />
      <view
        v-for="j in items"
        v-else
        :key="j.id"
        class="journal__item"
      >
        <view class="journal__row">
          <text class="journal__time">{{ formatTime(j.created_at) }}</text>
          <text v-if="j.emotion" class="journal__emotion">{{ j.emotion }}</text>
        </view>
        <text class="journal__content">{{ j.content }}</text>
        <view v-if="j.audio_url" class="journal__audio">
          <text class="journal__audio-icon">♪</text>
          点击播放语音
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { createJournal, listJournal, uploadJournalAudio, type JournalEntry } from '@/api';
import { startRecord, stopRecord } from '@/utils/wx';
import { relativeTime } from '@/utils/format';

const draft = ref('');
const items = ref<JournalEntry[]>([]);
const loading = ref(false);
const recording = ref(false);
const recordSeconds = ref(0);
let timer: ReturnType<typeof setInterval> | null = null;

async function toggleRecord() {
  if (!recording.value) {
    try {
      await startRecord();
      recording.value = true;
      recordSeconds.value = 0;
      timer = setInterval(() => recordSeconds.value++, 1000);
    } catch {
      uni.showToast({ title: '需要麦克风权限', icon: 'none' });
    }
  } else {
    try {
      const { tempFilePath } = await stopRecord();
      recording.value = false;
      if (timer) clearInterval(timer);
      const upload = await uploadJournalAudio(tempFilePath);
      await createJournal({ content: draft.value || '(语音日记)', audio_url: upload.url });
      draft.value = '';
      await refresh();
      uni.showToast({ title: '语音日记已保存', icon: 'success' });
    } catch {
      uni.showToast({ title: '录音失败', icon: 'none' });
    }
  }
}

async function save(analyze: boolean) {
  if (!draft.value.trim()) {
    uni.showToast({ title: '内容不能为空', icon: 'none' });
    return;
  }
  const res = await createJournal({ content: draft.value });
  if (res.ok) {
    draft.value = '';
    await refresh();
    uni.showToast({ title: analyze ? '已记录,稍后分析' : '已保存', icon: 'success' });
  } else {
    uni.showToast({ title: res.message || '保存失败', icon: 'none' });
  }
}

async function refresh() {
  loading.value = true;
  try {
    const res = await listJournal({ limit: 50 });
    if (res.ok && res.data) items.value = res.data.items;
  } finally {
    loading.value = false;
  }
}

function formatTime(t: string) {
  return relativeTime(t);
}

onMounted(refresh);
</script>

<style lang="scss" scoped>
.journal {
  padding: 32rpx;

  &__composer {
    background: #fff;
    border-radius: 24rpx;
    padding: 24rpx;
    box-shadow: 0 4rpx 16rpx rgba(31, 35, 41, 0.06);
    margin-bottom: 32rpx;
  }

  &__textarea {
    width: 100%;
    min-height: 200rpx;
    padding: 16rpx;
    font-size: 28rpx;
    line-height: 1.6;
  }

  &__actions {
    display: flex;
    justify-content: flex-end;
    gap: 16rpx;
    margin-top: 16rpx;
  }

  &__action {
    padding: 12rpx 24rpx;
    border-radius: 32rpx;
    background: #f2f3f5;
    color: #4e5969;
    font-size: 24rpx;

    &--primary {
      background: #3a7afe;
      color: #fff;
    }
  }

  &__recording {
    margin-top: 16rpx;
    display: flex;
    align-items: center;
    color: #f53f3f;
    font-size: 24rpx;
  }

  &__rec-dot {
    width: 16rpx;
    height: 16rpx;
    border-radius: 50%;
    background: #f53f3f;
    margin-right: 12rpx;
    animation: blink 1s infinite;
  }

  &__loading {
    padding: 64rpx 0;
  }

  &__item {
    background: #fff;
    border-radius: 24rpx;
    padding: 24rpx;
    margin-bottom: 16rpx;
    box-shadow: 0 4rpx 16rpx rgba(31, 35, 41, 0.06);
  }

  &__row {
    display: flex;
    justify-content: space-between;
    margin-bottom: 8rpx;
  }

  &__time {
    font-size: 24rpx;
    color: #8a8e99;
  }

  &__emotion {
    font-size: 22rpx;
    padding: 4rpx 12rpx;
    background: #e8efff;
    color: #3a7afe;
    border-radius: 16rpx;
  }

  &__content {
    font-size: 28rpx;
    line-height: 1.6;
    color: #1f2329;
    display: block;
    white-space: pre-wrap;
  }

  &__audio {
    margin-top: 12rpx;
    display: inline-flex;
    align-items: center;
    padding: 8rpx 16rpx;
    background: #f7f8fa;
    border-radius: 24rpx;
    color: #4e5969;
    font-size: 24rpx;
  }

  &__audio-icon {
    margin-right: 8rpx;
    color: #3a7afe;
  }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>