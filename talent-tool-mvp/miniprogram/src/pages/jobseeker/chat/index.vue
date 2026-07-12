<template>
  <view class="chat">
    <scroll-view
      class="chat__scroll"
      :scroll-y="true"
      :scroll-into-view="scrollIntoView"
      :scroll-with-animation="true"
    >
      <view
        v-for="turn in turns"
        :key="turn.id"
        :id="`msg-${turn.id}`"
        class="chat__row"
        :class="{ 'chat__row--me': turn.role === 'user' }"
      >
        <view class="chat__avatar">
          {{ turn.role === 'user' ? '我' : 'AI' }}
        </view>
        <view class="chat__bubble">{{ turn.content }}</view>
      </view>
      <view v-if="loading" class="chat__typing">智能体正在思考...</view>
    </scroll-view>

    <view class="chat__quick">
      <view
        v-for="q in quickPrompts"
        :key="q"
        class="chat__quick-item"
        @click="send(q)"
      >
        {{ q }}
      </view>
    </view>

    <view class="chat__composer">
      <textarea
        v-model="input"
        class="chat__input"
        placeholder="和智能体聊聊..."
        :auto-height="true"
        :show-confirm-bar="false"
        :adjust-position="true"
      />
      <button class="chat__send" :disabled="!input.trim() || loading" @click="onSend">发送</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue';
import { createSession, sendMessage, type ChatTurn } from '@/api';
import { uuid } from '@/utils/format';

const turns = ref<ChatTurn[]>([]);
const input = ref('');
const loading = ref(false);
const scrollIntoView = ref('');
const sessionId = ref<string>('');

const quickPrompts = [
  '帮我优化一下简历',
  '推荐适合我的岗位',
  '面试前要做哪些准备?',
  '我的职业规划有哪些建议?',
];

async function ensureSession() {
  if (sessionId.value) return sessionId.value;
  const res = await createSession('新对话');
  if (!res.ok) throw new Error(res.message || '创建会话失败');
  sessionId.value = res.data.id;
  return sessionId.value;
}

async function send(content: string) {
  if (!content.trim() || loading.value) return;
  const userTurn: ChatTurn = {
    id: uuid(),
    role: 'user',
    content,
    created_at: new Date().toISOString(),
  };
  turns.value.push(userTurn);
  input.value = '';
  await scrollToBottom();
  loading.value = true;
  try {
    const sid = await ensureSession();
    const res = await sendMessage(sid, content);
    if (res.ok && res.data) {
      turns.value.push(res.data.turn);
      // also reflect any earlier assistant turns if the session is fresh
      if (turns.value.length === 2 && res.data.session.turns.length > 2) {
        turns.value = res.data.session.turns;
      }
    } else {
      throw new Error(res.message || '发送失败');
    }
  } catch (err) {
    turns.value.push({
      id: uuid(),
      role: 'assistant',
      content: `抱歉,出错了: ${(err as Error).message}`,
      created_at: new Date().toISOString(),
    });
  } finally {
    loading.value = false;
    await scrollToBottom();
  }
}

function onSend() {
  send(input.value);
}

async function scrollToBottom() {
  await nextTick();
  const last = turns.value[turns.value.length - 1];
  if (last) scrollIntoView.value = `msg-${last.id}`;
}
</script>

<style lang="scss" scoped>
.chat {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f7f8fa;

  &__scroll {
    flex: 1;
    padding: 24rpx 32rpx;
  }

  &__row {
    display: flex;
    align-items: flex-start;
    margin-bottom: 24rpx;

    &--me {
      flex-direction: row-reverse;
    }
  }

  &__avatar {
    width: 72rpx;
    height: 72rpx;
    border-radius: 50%;
    background: #e8efff;
    color: #3a7afe;
    font-size: 26rpx;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  &__row--me &__avatar {
    background: #3a7afe;
    color: #fff;
  }

  &__bubble {
    max-width: 70%;
    padding: 20rpx 24rpx;
    margin: 0 16rpx;
    background: #fff;
    border-radius: 24rpx;
    box-shadow: 0 2rpx 8rpx rgba(31, 35, 41, 0.04);
    font-size: 28rpx;
    line-height: 1.6;
    word-break: break-word;
  }

  &__row--me &__bubble {
    background: #3a7afe;
    color: #fff;
  }

  &__typing {
    margin-left: 96rpx;
    font-size: 24rpx;
    color: #8a8e99;
    margin-bottom: 24rpx;
  }

  &__quick {
    display: flex;
    flex-wrap: wrap;
    gap: 16rpx;
    padding: 16rpx 32rpx;
    background: #fff;
    border-top: 1rpx solid #e5e6eb;
  }

  &__quick-item {
    padding: 12rpx 24rpx;
    border-radius: 32rpx;
    background: #f2f3f5;
    color: #4e5969;
    font-size: 24rpx;
  }

  &__composer {
    display: flex;
    align-items: flex-end;
    padding: 16rpx 24rpx 32rpx;
    background: #fff;
    border-top: 1rpx solid #e5e6eb;
    padding-bottom: calc(32rpx + env(safe-area-inset-bottom));
  }

  &__input {
    flex: 1;
    min-height: 72rpx;
    max-height: 240rpx;
    padding: 16rpx 24rpx;
    background: #f2f3f5;
    border-radius: 16rpx;
    font-size: 28rpx;
    line-height: 1.5;
  }

  &__send {
    margin-left: 16rpx;
    height: 72rpx;
    line-height: 72rpx;
    padding: 0 32rpx;
    border-radius: 36rpx;
    background: #3a7afe;
    color: #fff;
    border: none;
    font-size: 28rpx;
  }
}
</style>