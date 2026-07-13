"use client";

/**
 * v9.1 — 求职者 4 步 onboarding 向导.
 *
 * 4 步:
 *   1) 欢迎         - 介绍价值, 选择目标 (短/长期/海外/兼职)
 *   2) 基础档案     - 姓名 / 邮箱 / 城市 / 联系方式
 *   3) 求职偏好     - 类型 / 地点 / 薪资 / 远程 / 行业
 *   4) 完成         - 总结 + 跳转
 *
 * 设计:
 *  - 进度条 + 步骤指示器 (顶部)
 *  - 前后导航 (底部)
 *  - 可选跳过 (每步右下角)
 *  - localStorage 持久化, 刷新不丢
 *  - 中文 / 移动优先 / 可访问
 */

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CircleDot,
  Compass,
  Gift,
  MapPin,
  PartyPopper,
  Rocket,
  SkipForward,
  Sparkles,
  Target,
  Wallet,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";

const STORAGE_KEY = "v9.1.jobseeker.onboarding";

type Goal = "short_term" | "long_term" | "overseas" | "side";

interface OnboardingState {
  goal: Goal | null;
  fullName: string;
  email: string;
  city: string;
  phone: string;
  jobTypes: string[];
  preferredCities: string[];
  salaryMin: string;
  salaryMax: string;
  remote: "onsite" | "hybrid" | "remote" | "";
  industries: string[];
}

const DEFAULT_STATE: OnboardingState = {
  goal: null,
  fullName: "",
  email: "",
  city: "",
  phone: "",
  jobTypes: [],
  preferredCities: [],
  salaryMin: "",
  salaryMax: "",
  remote: "",
  industries: [],
};

interface StepDef {
  key: "welcome" | "profile" | "preferences" | "done";
  title: string;
  short: string;
  description: string;
  icon: LucideIcon;
}

const STEPS: StepDef[] = [
  {
    key: "welcome",
    title: "欢迎",
    short: "开始",
    description: "告诉我们你的目标",
    icon: Compass,
  },
  {
    key: "profile",
    title: "基础档案",
    short: "档案",
    description: "招聘方联系你的方式",
    icon: Sparkles,
  },
  {
    key: "preferences",
    title: "求职偏好",
    short: "偏好",
    description: "想做什么样的工作",
    icon: Target,
  },
  {
    key: "done",
    title: "完成",
    short: "完成",
    description: "准备就绪",
    icon: PartyPopper,
  },
];

const GOALS: Array<{ key: Goal; label: string; desc: string; icon: LucideIcon; tone: string }> =
  [
    {
      key: "short_term",
      label: "短期 1-3 个月",
      desc: "急需换工作,有具体意向行业",
      icon: Rocket,
      tone: "from-rose-500 to-orange-500",
    },
    {
      key: "long_term",
      label: "中长期 3-12 个月",
      desc: "探索方向,不急于跳槽",
      icon: Compass,
      tone: "from-indigo-500 to-violet-500",
    },
    {
      key: "overseas",
      label: "海外 / 跨境",
      desc: "关注英国/欧洲岗位,接受搬迁",
      icon: MapPin,
      tone: "from-emerald-500 to-teal-500",
    },
    {
      key: "side",
      label: "兼职 / 自由职业",
      desc: "希望时间灵活,补充主业收入",
      icon: Wallet,
      tone: "from-amber-500 to-yellow-500",
    },
  ];

const JOB_TYPES = [
  { value: "full_time", label: "全职" },
  { value: "part_time", label: "兼职" },
  { value: "contract", label: "合同" },
  { value: "freelance", label: "自由职业" },
  { value: "internship", label: "实习" },
];

const INDUSTRIES = [
  "互联网 / SaaS",
  "金融科技",
  "电商 / 零售",
  "教育",
  "医疗健康",
  "制造业",
  "广告 / 媒体",
  "游戏",
  "政企 / 国企",
  "能源 / 环保",
];

const REMOTE_OPTIONS: Array<{ value: OnboardingState["remote"]; label: string; desc: string }> =
  [
    { value: "onsite", label: "现场", desc: "到办公室坐班" },
    { value: "hybrid", label: "混合", desc: "每周 1-3 天远程" },
    { value: "remote", label: "全远程", desc: "完全远程工作" },
  ];

export default function OnboardingWelcomePage() {
  const router = useRouter();
  const [stepIdx, setStepIdx] = React.useState(0);
  const [state, setState] = React.useState<OnboardingState>(DEFAULT_STATE);
  const [hydrated, setHydrated] = React.useState(false);

  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { stepIdx?: number; state?: OnboardingState };
        if (typeof parsed.stepIdx === "number") {
          setStepIdx(Math.max(0, Math.min(STEPS.length - 1, parsed.stepIdx)));
        }
        if (parsed.state) {
          setState((p) => ({ ...p, ...parsed.state }));
        }
      }
    } catch {
      /* ignore */
    } finally {
      setHydrated(true);
    }
  }, []);

  React.useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ stepIdx, state }),
      );
    } catch {
      /* ignore quota */
    }
  }, [stepIdx, state, hydrated]);

  const step = STEPS[stepIdx];
  const progressPct = Math.round(((stepIdx + 1) / STEPS.length) * 100);

  const canGoNext = (() => {
    switch (step.key) {
      case "welcome":
        return state.goal !== null;
      case "profile":
        return (
          state.fullName.trim().length > 0 &&
          /\S+@\S+\.\S+/.test(state.email) &&
          state.city.trim().length > 0
        );
      case "preferences":
        return state.jobTypes.length > 0 && state.remote !== "";
      case "done":
        return true;
    }
  })();

  const goNext = () => {
    if (stepIdx < STEPS.length - 1) setStepIdx((i) => i + 1);
  };
  const goBack = () => {
    if (stepIdx > 0) setStepIdx((i) => i - 1);
  };

  const skip = () => {
    if (stepIdx < STEPS.length - 1) {
      setStepIdx((i) => i + 1);
    }
  };

  const finish = () => {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
    router.push("/jobseeker");
  };

  const update = <K extends keyof OnboardingState>(key: K, v: OnboardingState[K]) =>
    setState((p) => ({ ...p, [key]: v }));

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-indigo-50/40 dark:from-slate-950 dark:via-slate-950 dark:to-indigo-950/30">
      {/* 顶部 */}
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2">
            <span className="grid size-7 place-items-center rounded-md bg-primary/10 text-primary">
              <Sparkles className="size-3.5" aria-hidden="true" />
            </span>
            <div>
              <h1 className="text-sm font-semibold sm:text-base">欢迎使用 waibao</h1>
              <p className="text-[11px] text-muted-foreground">
                4 步开启智能求职
              </p>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={() => router.push("/jobseeker")}>
            稍后再说
          </Button>
        </div>
        <Progress
          value={progressPct}
          className="h-1 rounded-none"
          aria-label={`进度 ${progressPct}%`}
        />
      </header>

      {/* 步骤指示 */}
      <nav aria-label="Onboarding 步骤" className="mx-auto max-w-4xl px-4 pt-6 sm:px-6">
        <ol className="flex items-center justify-between gap-2">
          {STEPS.map((s, i) => {
            const isCurrent = i === stepIdx;
            const isDone = i < stepIdx;
            const Icon = s.icon;
            return (
              <li key={s.key} className="flex flex-1 items-center">
                <div className="flex flex-col items-center text-center">
                  <div
                    className={cn(
                      "grid size-9 place-items-center rounded-full border-2 transition-colors sm:size-10",
                      isDone && "border-primary bg-primary text-primary-foreground",
                      isCurrent && "border-primary bg-primary/10 text-primary",
                      !isDone &&
                        !isCurrent &&
                        "border-muted-foreground/30 text-muted-foreground",
                    )}
                    aria-current={isCurrent ? "step" : undefined}
                  >
                    {isDone ? (
                      <Check className="size-4" aria-hidden="true" />
                    ) : (
                      <Icon className="size-4" aria-hidden="true" />
                    )}
                  </div>
                  <span
                    className={cn(
                      "mt-1.5 text-[10px] font-medium sm:text-xs",
                      isCurrent ? "text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {s.short}
                  </span>
                </div>
                {i < STEPS.length - 1 && (
                  <div
                    className={cn(
                      "mx-2 h-0.5 flex-1 rounded-full transition-colors",
                      i < stepIdx ? "bg-primary" : "bg-muted",
                    )}
                  />
                )}
              </li>
            );
          })}
        </ol>
      </nav>

      {/* 主内容 */}
      <main className="mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-10">
        <div className="mb-5 text-center sm:mb-6">
          <Badge variant="outline" className="text-[10px]">
            第 {stepIdx + 1} / {STEPS.length} 步
          </Badge>
          <h2 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
            {step.title}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground sm:text-base">
            {step.description}
          </p>
        </div>

        <div className="mx-auto max-w-2xl">
          {step.key === "welcome" && (
            <WelcomeStep
              goal={state.goal}
              onChange={(g) => update("goal", g)}
            />
          )}
          {step.key === "profile" && (
            <ProfileStep state={state} update={update} />
          )}
          {step.key === "preferences" && (
            <PreferencesStep state={state} update={update} />
          )}
          {step.key === "done" && <DoneStep state={state} />}
        </div>
      </main>

      {/* 底部导航 */}
      <footer className="sticky bottom-0 border-t bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Button
            variant="ghost"
            size="sm"
            onClick={goBack}
            disabled={stepIdx === 0}
          >
            <ArrowLeft className="mr-1 size-4" aria-hidden="true" />
            上一步
          </Button>

          {step.key !== "done" ? (
            <div className="flex items-center gap-2">
              {step.key !== "welcome" && (
                <Button variant="ghost" size="sm" onClick={skip}>
                  <SkipForward className="mr-1 size-4" aria-hidden="true" />
                  跳过
                </Button>
              )}
              <Button
                size="sm"
                onClick={goNext}
                disabled={!canGoNext}
                className="min-w-28"
              >
                下一步
                <ArrowRight className="ml-1 size-4" aria-hidden="true" />
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              onClick={finish}
              className="min-w-28 bg-gradient-to-r from-indigo-600 to-violet-600 text-white hover:from-indigo-700 hover:to-violet-700"
            >
              前往工作台
              <ArrowRight className="ml-1 size-4" aria-hidden="true" />
            </Button>
          )}
        </div>
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 步骤组件
// ---------------------------------------------------------------------------

function WelcomeStep({
  goal,
  onChange,
}: {
  goal: Goal | null;
  onChange: (g: Goal) => void;
}) {
  return (
    <div className="space-y-3">
      {GOALS.map((g) => {
        const active = goal === g.key;
        const Icon = g.icon;
        return (
          <button
            key={g.key}
            type="button"
            onClick={() => onChange(g.key)}
            aria-pressed={active}
            className={cn(
              "group flex w-full items-center gap-4 rounded-xl border p-4 text-left transition-all sm:p-5",
              active
                ? "border-primary bg-primary/5 ring-2 ring-primary/30"
                : "border-border hover:border-primary/30 hover:bg-muted/40",
            )}
          >
            <span
              className={cn(
                "grid size-12 shrink-0 place-items-center rounded-xl bg-gradient-to-br text-white shadow-sm",
                g.tone,
              )}
              aria-hidden="true"
            >
              <Icon className="size-5" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold sm:text-base">{g.label}</p>
                {active && (
                  <Badge variant="default" className="h-4 px-1.5 text-[9px]">
                    已选
                  </Badge>
                )}
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground sm:text-sm">
                {g.desc}
              </p>
            </div>
            <CircleDot
              className={cn(
                "size-4 shrink-0 transition-opacity",
                active ? "text-primary opacity-100" : "opacity-30",
              )}
              aria-hidden="true"
            />
          </button>
        );
      })}

      <Separator className="my-4" />
      <p className="text-center text-xs text-muted-foreground">
        选错了? 之后可以随时在 <Link href="/jobseeker/account" className="text-primary underline-offset-2 hover:underline">账户设置</Link> 修改。
      </p>
    </div>
  );
}

function ProfileStep({
  state,
  update,
}: {
  state: OnboardingState;
  update: <K extends keyof OnboardingState>(k: K, v: OnboardingState[K]) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">联系方式</CardTitle>
        <CardDescription>
          招聘方和顾问会通过这些方式联系你,我们不会公开邮箱。
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="ob-name">姓名 *</Label>
          <Input
            id="ob-name"
            value={state.fullName}
            onChange={(e) => update("fullName", e.target.value)}
            placeholder="请输入真实姓名"
            autoComplete="name"
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ob-email">邮箱 *</Label>
          <Input
            id="ob-email"
            type="email"
            value={state.email}
            onChange={(e) => update("email", e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ob-phone">手机 / 微信</Label>
          <Input
            id="ob-phone"
            value={state.phone}
            onChange={(e) => update("phone", e.target.value)}
            placeholder="+44 7700 900 123"
            autoComplete="tel"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="ob-city">当前所在城市 *</Label>
          <Input
            id="ob-city"
            value={state.city}
            onChange={(e) => update("city", e.target.value)}
            placeholder="London, UK"
            autoComplete="address-level2"
            required
          />
          <p className="text-[11px] text-muted-foreground">
            用于匹配通勤范围,以及「是否接受搬迁」的判断。
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function PreferencesStep({
  state,
  update,
}: {
  state: OnboardingState;
  update: <K extends keyof OnboardingState>(k: K, v: OnboardingState[K]) => void;
}) {
  const toggle = (arr: string[], v: string): string[] =>
    arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">工作类型 *</CardTitle>
          <CardDescription>可多选;之后可以调整。</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {JOB_TYPES.map((t) => {
            const on = state.jobTypes.includes(t.value);
            return (
              <button
                key={t.value}
                type="button"
                onClick={() => update("jobTypes", toggle(state.jobTypes, t.value))}
                aria-pressed={on}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors sm:text-sm",
                  on
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted/40",
                )}
              >
                {t.label}
              </button>
            );
          })}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">远程偏好 *</CardTitle>
          <CardDescription>选一个最贴近的即可。</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-3">
          {REMOTE_OPTIONS.map((r) => {
            const on = state.remote === r.value;
            return (
              <button
                key={r.value}
                type="button"
                onClick={() => update("remote", r.value)}
                aria-pressed={on}
                className={cn(
                  "rounded-lg border p-3 text-left transition-colors",
                  on
                    ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                    : "border-border hover:bg-muted/40",
                )}
              >
                <p className="text-sm font-medium">{r.label}</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {r.desc}
                </p>
              </button>
            );
          })}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">期望薪资</CardTitle>
          <CardDescription>区间形式,单位 GBP / 年薪。</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="ob-smin">下限</Label>
            <Input
              id="ob-smin"
              type="number"
              inputMode="numeric"
              min={0}
              step={1000}
              value={state.salaryMin}
              onChange={(e) => update("salaryMin", e.target.value)}
              placeholder="60000"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ob-smax">上限</Label>
            <Input
              id="ob-smax"
              type="number"
              inputMode="numeric"
              min={0}
              step={1000}
              value={state.salaryMax}
              onChange={(e) => update("salaryMax", e.target.value)}
              placeholder="95000"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">关注行业</CardTitle>
          <CardDescription>不选也可以,后续会自动推荐。</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {INDUSTRIES.map((it) => {
            const on = state.industries.includes(it);
            return (
              <label
                key={it}
                className={cn(
                  "flex cursor-pointer items-center gap-2 rounded-md border p-2 text-xs transition-colors",
                  on
                    ? "border-primary/40 bg-primary/5"
                    : "border-border hover:bg-muted/40",
                )}
              >
                <Checkbox
                  checked={on}
                  onCheckedChange={() =>
                    update("industries", toggle(state.industries, it))
                  }
                />
                <span className="truncate">{it}</span>
              </label>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}

function DoneStep({ state }: { state: OnboardingState }) {
  const goalLabel = GOALS.find((g) => g.key === state.goal)?.label;
  const remoteLabel = REMOTE_OPTIONS.find((r) => r.value === state.remote)?.label;

  return (
    <Card className="overflow-hidden border-emerald-200/60 bg-gradient-to-br from-emerald-50 via-white to-indigo-50 dark:border-emerald-900/40 dark:from-emerald-950/30 dark:via-slate-950 dark:to-indigo-950/30">
      <CardContent className="space-y-5 p-6 text-center sm:p-10">
        <div className="mx-auto grid size-16 place-items-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-300">
          <Gift className="size-8" aria-hidden="true" />
        </div>
        <div>
          <h3 className="text-2xl font-bold sm:text-3xl">准备就绪 🎉</h3>
          <p className="mt-2 text-sm text-muted-foreground sm:text-base">
            我们已经为 <span className="font-semibold text-foreground">{state.fullName || "你"}</span>{" "}
            配置了 AI 匹配引擎,会持续推送合适的工作。
          </p>
        </div>

        <div className="mx-auto grid max-w-md gap-2 text-left text-sm">
          <SummaryRow label="求职目标" value={goalLabel ?? "未选择"} />
          <SummaryRow label="所在城市" value={state.city || "未填写"} />
          <SummaryRow
            label="工作类型"
            value={
              state.jobTypes.length > 0
                ? state.jobTypes
                    .map((v) => JOB_TYPES.find((t) => t.value === v)?.label)
                    .join(" · ")
                : "未选择"
            }
          />
          <SummaryRow label="远程偏好" value={remoteLabel ?? "未选择"} />
          {state.salaryMin || state.salaryMax ? (
            <SummaryRow
              label="期望薪资"
              value={`£${state.salaryMin || "0"} - £${state.salaryMax || "∞"}`}
            />
          ) : null}
          {state.industries.length > 0 ? (
            <SummaryRow
              label="关注行业"
              value={state.industries.slice(0, 3).join("、") +
                (state.industries.length > 3 ? ` 等 ${state.industries.length} 项` : "")}
            />
          ) : null}
        </div>

        <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/jobseeker/account">完善更多档案</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/jobseeker/account/notifications-prefs">设置通知偏好</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border bg-background/60 px-3 py-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-right text-sm font-medium">{value}</span>
    </div>
  );
}
