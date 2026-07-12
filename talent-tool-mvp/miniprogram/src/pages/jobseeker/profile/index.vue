<template>
  <view class="profile">
    <wb-card title="基础信息">
      <view class="profile__field">
        <text class="profile__label">一句话介绍</text>
        <input
          v-model="form.headline"
          class="profile__input"
          placeholder="例如:5 年 SaaS 前端,React/Vue 双栈"
          @blur="save"
        />
      </view>
      <view class="profile__field">
        <text class="profile__label">个人简介</text>
        <textarea
          v-model="form.bio"
          class="profile__textarea"
          placeholder="说说你的优势、兴趣和方向"
          @blur="save"
        />
      </view>
      <view class="profile__field">
        <text class="profile__label">工作年限</text>
        <input
          v-model.number="form.experience_years"
          type="number"
          class="profile__input"
          @blur="save"
        />
      </view>
    </wb-card>

    <wb-card title="技能标签" extra="回车添加">
      <view class="profile__skills">
        <view v-for="s in form.skills" :key="s" class="profile__skill">
          {{ s }}
          <text class="profile__skill-x" @click="removeSkill(s)">×</text>
        </view>
        <input
          v-model="skillDraft"
          class="profile__skill-input"
          placeholder="+ 添加技能"
          @confirm="addSkill"
        />
      </view>
    </wb-card>

    <wb-card title="偏好">
      <view class="profile__field">
        <text class="profile__label">期望城市</text>
        <input v-model="city" class="profile__input" @blur="save" />
      </view>
      <view class="profile__field">
        <text class="profile__label">期望薪资 (K)</text>
        <view class="profile__row">
          <input v-model.number="salaryMin" type="number" class="profile__input profile__input--small" @blur="save" />
          <text class="profile__dash">—</text>
          <input v-model.number="salaryMax" type="number" class="profile__input profile__input--small" @blur="save" />
        </view>
      </view>
    </wb-card>

    <view class="profile__completion">
      <text>画像完整度 {{ completion }}%</text>
      <view class="profile__bar">
        <view class="profile__bar-fill" :style="{ width: completion + '%' }" />
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { fetchProfile, updateProfile } from '@/api';

const form = reactive({
  headline: '',
  bio: '',
  experience_years: 0,
  skills: [] as string[],
});
const skillDraft = ref('');
const city = ref('');
const salaryMin = ref<number | null>(null);
const salaryMax = ref<number | null>(null);
const saving = ref(false);

const completion = computed(() => {
  let s = 0;
  if (form.headline) s += 20;
  if (form.bio) s += 20;
  if (form.experience_years > 0) s += 15;
  if (form.skills.length) s += Math.min(25, form.skills.length * 5);
  if (city.value) s += 10;
  if (salaryMin.value && salaryMax.value) s += 10;
  return Math.min(100, s);
});

function addSkill() {
  const v = skillDraft.value.trim();
  if (!v || form.skills.includes(v)) {
    skillDraft.value = '';
    return;
  }
  form.skills.push(v);
  skillDraft.value = '';
  save();
}

function removeSkill(s: string) {
  form.skills = form.skills.filter((x) => x !== s);
  save();
}

async function save() {
  if (saving.value) return;
  saving.value = true;
  try {
    await updateProfile({
      ...form,
      preferences: {
        city: city.value,
        salary_min: salaryMin.value,
        salary_max: salaryMax.value,
      },
    });
    uni.showToast({ title: '已保存', icon: 'success', duration: 1200 });
  } catch (err) {
    uni.showToast({ title: '保存失败', icon: 'none' });
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  const res = await fetchProfile();
  if (res.ok && res.data) {
    form.headline = res.data.headline || '';
    form.bio = res.data.bio || '';
    form.experience_years = res.data.experience_years || 0;
    form.skills = res.data.skills || [];
    const prefs = res.data.preferences || {};
    city.value = (prefs.city as string) || '';
    salaryMin.value = (prefs.salary_min as number) || null;
    salaryMax.value = (prefs.salary_max as number) || null;
  }
});
</script>

<style lang="scss" scoped>
.profile {
  padding: 32rpx;

  &__field {
    margin-bottom: 24rpx;
    display: flex;
    flex-direction: column;
  }

  &__label {
    font-size: 26rpx;
    color: #8a8e99;
    margin-bottom: 8rpx;
  }

  &__input {
    padding: 16rpx 24rpx;
    background: #f7f8fa;
    border-radius: 12rpx;
    font-size: 28rpx;

    &--small {
      flex: 1;
    }
  }

  &__textarea {
    padding: 16rpx 24rpx;
    background: #f7f8fa;
    border-radius: 12rpx;
    font-size: 28rpx;
    min-height: 160rpx;
    width: 100%;
  }

  &__row {
    display: flex;
    align-items: center;
  }

  &__dash {
    padding: 0 16rpx;
    color: #8a8e99;
  }

  &__skills {
    display: flex;
    flex-wrap: wrap;
    gap: 16rpx;
  }

  &__skill {
    display: inline-flex;
    align-items: center;
    padding: 12rpx 24rpx;
    background: #e8efff;
    color: #3a7afe;
    border-radius: 32rpx;
    font-size: 24rpx;
  }

  &__skill-x {
    margin-left: 12rpx;
    color: #3a7afe;
    font-size: 30rpx;
  }

  &__skill-input {
    padding: 12rpx 24rpx;
    background: #f2f3f5;
    border-radius: 32rpx;
    font-size: 24rpx;
    min-width: 200rpx;
  }

  &__completion {
    margin-top: 24rpx;
    padding: 24rpx;
    background: #fff;
    border-radius: 24rpx;
    box-shadow: 0 4rpx 16rpx rgba(31, 35, 41, 0.06);
    font-size: 26rpx;
    color: #4e5969;
  }

  &__bar {
    margin-top: 12rpx;
    height: 12rpx;
    background: #f2f3f5;
    border-radius: 6rpx;
    overflow: hidden;
  }

  &__bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #3a7afe, #00b42a);
    transition: width 0.3s ease;
  }
}
</style>