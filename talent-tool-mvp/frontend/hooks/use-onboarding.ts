"use client";

/**
 * T1106 — Onboarding 进度管理 hook.
 *
 * 用 localStorage 持久化 checklist 状态:
 * - 4 步 onboarding (profile / first_match / first_handoff / invite_teammate)
 * - 单独跟踪 product tour 的"已展示过"标记
 *
 * 进度值 0..1,可用于 progress bar / confetti 触发判断.
 */

import * as React from "react";

export type OnboardingStep =
  | "profile_complete"
  | "first_match_viewed"
  | "first_handoff_created"
  | "first_teammate_invited";

export interface StepDef {
  key: OnboardingStep;
  title: string;
  description: string;
  href?: string;
}

export const JOBSEEKER_STEPS: StepDef[] = [
  {
    key: "profile_complete",
    title: "完善个人档案",
    description: "上传简历或手动填写,解锁匹配引擎",
    href: "/jobseeker/onboarding",
  },
  {
    key: "first_match_viewed",
    title: "查看第一次 AI 匹配",
    description: "浏览推荐的工作机会,了解评分逻辑",
    href: "/match",
  },
  {
    key: "first_handoff_created",
    title: "联系一位招聘顾问",
    description: "对感兴趣的角色发起约谈",
    href: "/match",
  },
  {
    key: "first_teammate_invited",
    title: "邀请朋友一起使用",
    description: "成功推荐可获得额外算力 (可选)",
  },
];

export const EMPLOYER_STEPS: StepDef[] = [
  {
    key: "profile_complete",
    title: "完善公司档案",
    description: "补充公司信息,匹配引擎才能精准推荐",
    href: "/employer/policy",
  },
  {
    key: "first_match_viewed",
    title: "查看候选人匹配",
    description: "对发布的职位查看 AI 推荐候选人",
    href: "/employer/strategy",
  },
  {
    key: "first_handoff_created",
    title: "完成一次候选人沟通",
    description: "为感兴趣的候选人创建 handoff",
    href: "/employer/tickets",
  },
  {
    key: "first_teammate_invited",
    title: "邀请同事加入",
    description: "招聘需要协作,邀请同事一起用",
  },
];

const STORAGE_KEY = "wb_onboarding_progress";
const TOUR_KEY = "wb_product_tour_done";

interface PersistedState {
  completed: OnboardingStep[];
  dismissed: boolean;
}

function loadState(): PersistedState {
  if (typeof window === "undefined") return { completed: [], dismissed: false };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { completed: [], dismissed: false };
    return JSON.parse(raw);
  } catch {
    return { completed: [], dismissed: false };
  }
}

function saveState(s: PersistedState) {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
}

export interface UseOnboardingReturn {
  steps: StepDef[];
  completed: Set<OnboardingStep>;
  progress: number;       // 0..1
  isAllDone: boolean;
  dismissed: boolean;
  markStep: (k: OnboardingStep) => void;
  reset: () => void;
  dismiss: () => void;
  isDone: (k: OnboardingStep) => boolean;
}

export function useOnboarding(role: "jobseeker" | "employer"): UseOnboardingReturn {
  const steps = role === "employer" ? EMPLOYER_STEPS : JOBSEEKER_STEPS;
  const [state, setState] = React.useState<PersistedState>(() => loadState());

  React.useEffect(() => {
    saveState(state);
  }, [state]);

  const completedSet = React.useMemo(
    () => new Set(state.completed),
    [state.completed],
  );

  const markStep = React.useCallback((k: OnboardingStep) => {
    setState((s) => {
      if (s.completed.includes(k)) return s;
      return { ...s, completed: [...s.completed, k] };
    });
  }, []);

  const reset = React.useCallback(() => {
    setState({ completed: [], dismissed: false });
  }, []);

  const dismiss = React.useCallback(() => {
    setState((s) => ({ ...s, dismissed: true }));
  }, []);

  const isDone = React.useCallback(
    (k: OnboardingStep) => completedSet.has(k),
    [completedSet],
  );

  const progress = steps.length === 0 ? 1 : completedSet.size / steps.length;
  const isAllDone = completedSet.size >= steps.length;

  return {
    steps,
    completed: completedSet,
    progress,
    isAllDone,
    dismissed: state.dismissed,
    markStep,
    reset,
    dismiss,
    isDone,
  };
}

/**
 * 标记 ProductTour 已展示 (供 layout 调用).
 */
export function markProductTourDone() {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOUR_KEY, "1");
}

export function isProductTourDone(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(TOUR_KEY) === "1";
}

export function resetProductTour() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOUR_KEY);
}