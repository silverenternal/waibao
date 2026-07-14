"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v9.1 — 求职者通知偏好 (细粒度).
 *
 * 组合:
 *  - 全局频率 (实时 / 每日摘要 / 每周摘要)
 *  - 免打扰时间段 (24h 拖动)
 *  - 类别 × 优先级 × 通道 矩阵 (使用 CategorySwitch)
 *  - LLM 智能建议 + 一键应用 (SmartSuggestion)
 *  - 实时保存,带最后保存时间提示
 *
 * 设计:
 *  - 中文为主,使用 lucide-react 图标
 *  - 顶部摘要:今天会发多少条
 *  - 移动优先,sm / lg 断点
 *  - ARIA: form / switch / region / aria-live
 *  - 客户端 state,localStorage 持久化
 */

import * as React from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Bell,
  CalendarRange,
  CheckCheck,
  Clock,
  Hourglass,
  Info,
  Loader2,
  Save,
  Sparkles,
  TimerReset,
  Volume2,
  Zap,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import {
  CategorySwitch,
  type ChannelKey,
  type PriorityKey,
} from "@/components/notifications/CategorySwitch";
import { QuietHoursPicker } from "@/components/notifications/QuietHoursPicker";
import {
  SmartSuggestion,
  type SmartSuggestionItem,
  type SuggestionType,
} from "@/components/notifications/SmartSuggestion";

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------

type Frequency = "realtime" | "hourly" | "daily" | "weekly";

type CategoryKey =
  | "matching"
  | "interview"
  | "offer"
  | "subscription"
  | "system"
  | "marketing";

const CATEGORIES: { key: CategoryKey; label: string; desc: string; icon: LucideIcon }[] =
  [
    {
      key: "matching",
      label: "AI 匹配",
      desc: "新增匹配岗位、档案完整度变化、订阅触发。",
      icon: Sparkles,
    },
    {
      key: "interview",
      label: "面试 / 约谈",
      desc: "顾问邀约、面试提醒、改期与确认。",
      icon: CalendarRange,
    },
    {
      key: "offer",
      label: "Offer 与合同",
      desc: "Offer 草稿、状态变更、合同签署提醒。",
      icon: CheckCheck,
    },
    {
      key: "subscription",
      label: "订阅更新",
      desc: "订阅触发、暂停、命中数周报。",
      icon: Bell,
    },
    {
      key: "system",
      label: "账户与安全",
      desc: "登录、密码、风控告警、容量预警。",
      icon: Info,
    },
    {
      key: "marketing",
      label: "内容与营销",
      desc: "行业报告、招聘活动、平台公告。",
      icon: Volume2,
    },
  ];

const PRIORITIES: PriorityKey[] = ["high", "medium", "low"];
const CHANNELS: ChannelKey[] = ["smtp", "dingtalk", "feishu", "im", "web"];

const FREQUENCY_OPTIONS: { key: Frequency; label: string; desc: string; icon: LucideIcon }[] =
  [
    {
      key: "realtime",
      label: "实时",
      desc: "事件触发后立即推送 (≤ 1 分钟)",
      icon: Zap,
    },
    {
      key: "hourly",
      label: "每小时",
      desc: "合并为 1 小时摘要",
      icon: Hourglass,
    },
    {
      key: "daily",
      label: "每日",
      desc: "次日 09:00 汇总",
      icon: CalendarRange,
    },
    {
      key: "weekly",
      label: "每周",
      desc: "每周一 09:00 汇总",
      icon: TimerReset,
    },
  ];

type Matrix = Record<
  CategoryKey,
  Record<PriorityKey, Record<ChannelKey, boolean>>
>;

interface PrefsState {
  frequency: Frequency;
  quietStart: string | null;
  quietEnd: string | null;
  matrix: Matrix;
}

const STORAGE_KEY = "v9.1.jobseeker.notifprefs";

function makeDefaultMatrix(): Matrix {
  const m: Matrix = {} as Matrix;
  for (const c of CATEGORIES) {
    m[c.key] = {} as Record<PriorityKey, Record<ChannelKey, boolean>>;
    for (const p of PRIORITIES) {
      m[c.key][p] = {} as Record<ChannelKey, boolean>;
      for (const ch of CHANNELS) {
        // 默认:系统类全部开;营销类只保留邮件和 Web;其它默认开 Web/邮件
        if (c.key === "marketing") {
          m[c.key][p][ch] = ch === "smtp" || ch === "web";
        } else if (c.key === "system") {
          m[c.key][p][ch] = true;
        } else {
          m[c.key][p][ch] = ch === "smtp" || ch === "web" || ch === "im";
        }
      }
    }
  }
  return m;
}

const DEFAULT_STATE: PrefsState = {
  frequency: "realtime",
  quietStart: "22:00",
  quietEnd: "08:00",
  matrix: makeDefaultMatrix(),
};

const SEED_SUGGESTIONS: SmartSuggestionItem[] = [
  {
    id: "sg-001",
    type: "frequency_change",
    description:
      "近 7 天你在 22:00 后还收到 12 条匹配推送,建议改为「每小时」摘要,减少打扰。",
    suggestion: { from: "realtime", to: "hourly" },
    confidence: 0.78,
  },
  {
    id: "sg-002",
    type: "category_disable",
    description:
      "过去 30 天你从未点击过「内容与营销」邮件,建议关闭该类别的邮件通道。",
    suggestion: { category: "marketing", channel: "smtp", enabled: false },
    confidence: 0.84,
  },
  {
    id: "sg-003",
    type: "quiet_hours_extend",
    description: "周末上午 (周六/周日 08:00 - 11:00) 适合延长为免打扰。",
    suggestion: { weekend: true, start: "08:00", end: "11:00" },
    confidence: 0.62,
  },
];

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

export default function NotificationsPrefsPage() {
  const [state, setState] = React.useState<PrefsState>(DEFAULT_STATE);
  const [suggestions, setSuggestions] =
    React.useState<SmartSuggestionItem[]>(SEED_SUGGESTIONS);
  const [hydrated, setHydrated] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [savedAt, setSavedAt] = React.useState<string | null>(null);
  const [dirty, setDirty] = React.useState(false);

  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as PrefsState;
        setState({
          ...DEFAULT_STATE,
          ...parsed,
          matrix: { ...DEFAULT_STATE.matrix, ...(parsed.matrix ?? {}) },
        });
      }
    } catch {
      /* ignore */
    } finally {
      setHydrated(true);
    }
  }, []);

  // 自动保存 (debounce 600ms)
  React.useEffect(() => {
    if (!hydrated || !dirty) return;
    const t = window.setTimeout(() => {
      void doSave(false);
    }, 600);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, hydrated, dirty]);

  const doSave = async (manual: boolean) => {
    setSaving(true);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      await new Promise((r) => setTimeout(r, manual ? 380 : 120));
      setSavedAt(new Date().toLocaleTimeString("zh-CN"));
      setDirty(false);
    } finally {
      setSaving(false);
    }
  };

  const onToggle = React.useCallback(
    (cat: CategoryKey, pri: PriorityKey, ch: ChannelKey, enabled: boolean) => {
      setState((prev) => ({
        ...prev,
        matrix: {
          ...prev.matrix,
          [cat]: {
            ...prev.matrix[cat],
            [pri]: { ...prev.matrix[cat][pri], [ch]: enabled },
          },
        },
      }));
      setDirty(true);
    },
    [],
  );

  const onQuietChange = React.useCallback(
    (start: string | null, end: string | null) => {
      setState((prev) => ({ ...prev, quietStart: start, quietEnd: end }));
      setDirty(true);
    },
    [],
  );

  const onFrequencyChange = React.useCallback((f: Frequency) => {
    setState((prev) => ({ ...prev, frequency: f }));
    setDirty(true);
  }, []);

  // 计算"今天会收到多少条" (基于已开启通道数)
  const todayEstimate = React.useMemo(() => {
    let n = 0;
    for (const c of CATEGORIES) {
      for (const p of PRIORITIES) {
        for (const ch of CHANNELS) {
          if (state.matrix[c.key][p][ch]) n += 1;
        }
      }
    }
    // 按频率调整展示
    const mult =
      state.frequency === "realtime"
        ? 1
        : state.frequency === "hourly"
          ? 0.4
          : state.frequency === "daily"
            ? 0.15
            : 0.05;
    return Math.round(n * mult);
  }, [state.matrix, state.frequency]);

  const applySuggestion = React.useCallback(
    async (id: string) => {
      const item = suggestions.find((s) => s.id === id);
      if (!item) return;
      setSuggestions((arr) =>
        arr.map((s) => (s.id === id ? { ...s, status: "applied" } : s)),
      );
      const t: SuggestionType = item.type;
      if (t === "frequency_change") {
        const to = (item.suggestion as { to?: Frequency }).to;
        if (to) onFrequencyChange(to);
      } else if (t === "category_disable") {
        const { category, channel, enabled } = item.suggestion as {
          category?: CategoryKey;
          channel?: ChannelKey;
          enabled?: boolean;
        };
        if (category && channel) {
          for (const p of PRIORITIES) {
            onToggle(category, p, channel, enabled ?? false);
          }
        }
      } else if (t === "quiet_hours_extend") {
        const { start, end } = item.suggestion as {
          start?: string;
          end?: string;
        };
        if (start && end) onQuietChange(start, end);
      } else if (t === "channel_change" || t === "priority_reduce") {
        // 通用占位:不修改状态,只标记
      }
    },
    [suggestions, onFrequencyChange, onToggle, onQuietChange],
  );

  const dismissSuggestion = React.useCallback(async (id: string) => {
    setSuggestions((arr) =>
      arr.map((s) => (s.id === id ? { ...s, status: "dismissed" } : s)),
    );
  }, []);

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
        {/* 顶部 */}
        <header className="mb-6 sm:mb-8">
          <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
            <Link
              href="/jobseeker/account"
              className="inline-flex items-center gap-1 hover:text-foreground"
            >
              <ArrowLeft className="size-3" aria-hidden="true" />
              返回账户
            </Link>
            <span aria-hidden="true">/</span>
            <span aria-current="page">通知偏好</span>
          </div>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
                <Bell className="size-3.5" aria-hidden="true" />
                通知偏好
              </div>
              <h1 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
                决定你会被怎样打扰
              </h1>
              <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                按「类别 × 优先级 × 通道」精细控制;支持免打扰时段与 LLM 一键优化。
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {saving ? (
                <span className="inline-flex items-center gap-1">
                  <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                  保存中
                </span>
              ) : savedAt ? (
                <span className="inline-flex items-center gap-1 text-emerald-600">
                  <CheckCheck className="size-3" aria-hidden="true" />
                  已保存 · {savedAt}
                </span>
              ) : (
                <span>尚未修改</span>
              )}
              <Button
                size="sm"
                onClick={() => doSave(true)}
                disabled={!dirty || saving}
              >
                <Save className="mr-1.5 size-4" aria-hidden="true" />
                立即保存
              </Button>
            </div>
          </div>
        </header>
        {/* 摘要卡 */}
        <section
          aria-label="今日推送预估"
          className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4"
        >
          <SummaryTile
            icon={Zap}
            label="频率"
            value={
              FREQUENCY_OPTIONS.find((o) => o.key === state.frequency)?.label ??
              "实时"
            }
            tone="indigo"
          />
          <SummaryTile
            icon={Clock}
            label="免打扰"
            value={
              state.quietStart && state.quietEnd
                ? `${state.quietStart} - ${state.quietEnd}`
                : "未设置"
            }
            tone="emerald"
          />
          <SummaryTile
            icon={Bell}
            label="今日预估"
            value={`${todayEstimate} 条`}
            tone="amber"
          />
          <SummaryTile
            icon={CheckCheck}
            label="已开启通道"
            value={countEnabled(state.matrix).toString()}
            tone="rose"
          />
        </section>
        {/* 频率 + 免打扰 */}
        <div className="mb-6 grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">全局推送频率</CardTitle>
              <CardDescription>
                适用于所有类别;高级类别仍可单独覆盖。
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-2 sm:grid-cols-2">
              {FREQUENCY_OPTIONS.map((opt) => {
                const Icon = opt.icon;
                const active = state.frequency === opt.key;
                return (
                  <button
                    key={opt.key}
                    type="button"
                    onClick={() => onFrequencyChange(opt.key)}
                    aria-pressed={active}
                    className={cn(
                      "group flex items-start gap-3 rounded-lg border p-3 text-left transition-colors",
                      active
                        ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                        : "border-border hover:bg-muted/40",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-0.5 grid size-9 place-items-center rounded-md",
                        active
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground",
                      )}
                      aria-hidden="true"
                    >
                      <Icon className="size-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium leading-tight">
                        {opt.label}
                      </span>
                      <span className="mt-0.5 block text-[11px] text-muted-foreground">
                        {opt.desc}
                      </span>
                    </span>
                  </button>
                );
              })}
            </CardContent>
          </Card>

          <QuietHoursPicker
            start={state.quietStart}
            end={state.quietEnd}
            onChange={onQuietChange}
          />
        </div>
        {/* 类别矩阵 */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">分类 × 优先级 × 通道</CardTitle>
            <CardDescription>
              单元格 = 开启/关闭该类下、该优先级、通过该通道的推送。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {!hydrated ? (
              <div className="space-y-3">
                {CATEGORIES.map((c) => (
                  <Skeleton key={c.key} className="h-28 w-full" />
                ))}
              </div>
            ) : (
              CATEGORIES.map((c) => (
                <CategorySwitch
                  key={c.key}
                  category={c.key}
                  label={c.label}
                  description={c.desc}
                  priorities={PRIORITIES}
                  channels={CHANNELS}
                  matrix={state.matrix[c.key]}
                  onToggle={(p, ch, e) => onToggle(c.key, p, ch, e)}
                  badge={categoryBadge(c.key, state.matrix)}
                />
              ))
            )}
          </CardContent>
        </Card>
        {/* 智能建议 */}
        <Card className="mb-6 border-amber-200/60 bg-amber-50/40 dark:border-amber-900/40 dark:bg-amber-950/20">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles
                className="size-4 text-amber-600 dark:text-amber-400"
                aria-hidden="true"
              />
              AI 优化建议
            </CardTitle>
            <CardDescription>
              根据近 30 天你的点击/已读行为,LLM 给出 1 键应用方案。
            </CardDescription>
          </CardHeader>
          <CardContent>
            {suggestions.filter((s) => s.status !== "dismissed").length === 0 ? (
              <p className="text-sm text-muted-foreground">
                目前没有可应用的建议 ✨
              </p>
            ) : (
              <ul className="grid gap-3 sm:grid-cols-2">
                {suggestions
                  .filter((s) => s.status !== "dismissed")
                  .map((s) => (
                    <li key={s.id}>
                      <SmartSuggestion
                        item={s}
                        onApply={applySuggestion}
                        onDismiss={dismissSuggestion}
                      />
                    </li>
                  ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Separator className="my-6" />
        <p className="text-center text-xs text-muted-foreground">
          想了解每个通道的含义?
          <Link
            href="/jobseeker/account/privacy"
            className="ml-1 underline-offset-2 hover:underline"
          >
            查看隐私与数据使用
          </Link>
        </p>
      </div>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// 子组件 / 工具
// ---------------------------------------------------------------------------

function SummaryTile({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  tone: "indigo" | "emerald" | "amber" | "rose";
}) {
  const toneCls: Record<typeof tone, string> = {
    indigo:
      "bg-indigo-50 text-indigo-700 ring-indigo-200/60 dark:bg-indigo-950/40 dark:text-indigo-200 dark:ring-indigo-900",
    emerald:
      "bg-emerald-50 text-emerald-700 ring-emerald-200/60 dark:bg-emerald-950/40 dark:text-emerald-200 dark:ring-emerald-900",
    amber: "bg-amber-50 text-amber-800 ring-amber-200/60 dark:bg-amber-950/40 dark:text-amber-200 dark:ring-amber-900",
    rose: "bg-rose-50 text-rose-700 ring-rose-200/60 dark:bg-rose-950/40 dark:text-rose-200 dark:ring-rose-900",
  };
  return (
    <div
      className={cn(
        "rounded-xl p-3 ring-1 sm:p-4",
        toneCls[tone],
      )}
      role="status"
      aria-label={`${label}: ${value}`}
    >
      <div className="flex items-center justify-between text-xs sm:text-sm">
        <span className="font-medium opacity-80">{label}</span>
        <Icon className="size-4 opacity-70" aria-hidden="true" />
      </div>
      <p className="mt-1.5 text-lg font-bold sm:text-xl">{value}</p>
    </div>
  );
}

function categoryBadge(
  key: CategoryKey,
  matrix: Matrix,
): string | undefined {
  const total = PRIORITIES.length * CHANNELS.length;
  const on = Object.values(matrix[key]).reduce(
    (acc, row) => acc + Object.values(row).filter(Boolean).length,
    0,
  );
  if (on === total) return "全部开启";
  if (on === 0) return "全部关闭";
  return `${on}/${total} 通道`;
}

function countEnabled(matrix: Matrix): number {
  let n = 0;
  for (const c of CATEGORIES) {
    for (const p of PRIORITIES) {
      for (const ch of CHANNELS) {
        if (matrix[c.key][p][ch]) n += 1;
      }
    }
  }
  return n;
}
