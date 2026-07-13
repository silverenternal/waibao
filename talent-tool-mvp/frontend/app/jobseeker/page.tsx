"use client";

/**
 * v9.1 · 求职者核心 Dashboard
 * --------------------------------------------------------------------
 * 布局:关怀 banner / 4 KPI / AI 入口 / 5 个推荐职位 / 待办 / 活动图表 / 情绪趋势
 * 数据:全部使用本地 mock,接口后续接入;若 components/jobseeker 出现,
 *     这些占位卡片会被同名导出自然替换。
 */

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  Briefcase,
  Calendar,
  ChevronRight,
  Compass,
  Heart,
  MessageSquare,
  Mic,
  Sparkles,
  Sun,
  TrendingUp,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { TimeSeriesChart } from "@/components/charts/time-series-chart";

// --------------------------------------------------------------------
// 1. Mock 数据(后续替换为 lib/api-portal.ts / lib/api-emotion.ts)
// --------------------------------------------------------------------

type KpiTrend = "up" | "down" | "neutral";

const KPIS: Array<{
  key: string;
  label: string;
  value: string;
  delta: string;
  trend: KpiTrend;
  hint: string;
  accent: string;
  icon: typeof Compass;
  iconColor: string;
}> = [
  {
    key: "matches",
    label: "本周新增匹配",
    value: "12",
    delta: "+4",
    trend: "up",
    hint: "AI 已读完你的最新档案",
    accent: "from-indigo-500/15 to-indigo-500/0",
    icon: Compass,
    iconColor: "text-indigo-500",
  },
  {
    key: "profile",
    label: "档案完整度",
    value: "86%",
    delta: "+8%",
    trend: "up",
    hint: "还差 2 项即可解锁金牌推荐",
    accent: "from-emerald-500/15 to-emerald-500/0",
    icon: Sparkles,
    iconColor: "text-emerald-500",
  },
  {
    key: "interviews",
    label: "本周面试",
    value: "3",
    delta: "1 待确认",
    trend: "neutral",
    hint: "周三 14:00 · 客户技术终面",
    accent: "from-amber-500/15 to-amber-500/0",
    icon: Calendar,
    iconColor: "text-amber-500",
  },
  {
    key: "mood",
    label: "情绪指数",
    value: "7.4",
    delta: "+0.6",
    trend: "up",
    hint: "过去 7 天平均,稳定偏积极",
    accent: "from-rose-500/15 to-rose-500/0",
    icon: Heart,
    iconColor: "text-rose-500",
  },
];

const RECOMMENDED_JOBS = [
  {
    id: "j-001",
    title: "高级前端工程师 · React",
    company: "Tidewave Tech",
    location: "London · 远程友好",
    salary: "£75k – £95k",
    match: 94,
    skills: ["React", "TypeScript", "Next.js"],
    stage: "面试中",
    stageTone: "amber",
  },
  {
    id: "j-002",
    title: "全栈工程师 · 金融科技",
    company: "Lumen Pay",
    location: "Manchester · 混合办公",
    salary: "£80k – £105k",
    match: 91,
    skills: ["Node.js", "PostgreSQL", "AWS"],
    stage: "新机会",
    stageTone: "indigo",
  },
  {
    id: "j-003",
    title: "产品工程师 · AI 方向",
    company: "Northwind Labs",
    location: "Remote · UK",
    salary: "£85k – £120k",
    match: 88,
    skills: ["Python", "LLM", "RAG"],
    stage: "简历已投",
    stageTone: "slate",
  },
  {
    id: "j-004",
    title: "技术负责人 · 平台组",
    company: "Helix Bio",
    location: "Cambridge · 现场",
    salary: "£110k – £140k",
    match: 82,
    skills: ["架构", "团队管理", "Kubernetes"],
    stage: "推荐中",
    stageTone: "emerald",
  },
  {
    id: "j-005",
    title: "前端 Tech Lead",
    company: "Verdant Studio",
    location: "Edinburgh · 远程",
    salary: "£90k – £115k",
    match: 79,
    skills: ["React", "设计系统", "GraphQL"],
    stage: "新机会",
    stageTone: "indigo",
  },
];

const TODOS = [
  {
    id: "t-1",
    title: "确认周三 14:00 客户终面",
    meta: "高优 · 截止 7/15 09:00",
    done: false,
  },
  {
    id: "t-2",
    title: "上传最新版英文简历(覆盖 2024 Q2 经历)",
    meta: "完善度 +6%",
    done: false,
  },
  {
    id: "t-3",
    title: "和 Lily 聊 Tidewave 薪资预期",
    meta: "顾问消息 · 2 条未读",
    done: false,
  },
  {
    id: "t-4",
    title: "周记:这周最值得记录的一件事",
    meta: "建议 3 分钟",
    done: true,
  },
];

const ACTIVITY = [
  { day: "周一", applications: 4, interviews: 1, replies: 3 },
  { day: "周二", applications: 6, interviews: 0, replies: 4 },
  { day: "周三", applications: 3, interviews: 2, replies: 2 },
  { day: "周四", applications: 5, interviews: 1, replies: 5 },
  { day: "周五", applications: 7, interviews: 1, replies: 4 },
  { day: "周六", applications: 1, interviews: 0, replies: 1 },
  { day: "周日", applications: 2, interviews: 0, replies: 2 },
];

const MOOD_TREND = [
  { date: "07-07", value: 6.4 },
  { date: "07-08", value: 6.8 },
  { date: "07-09", value: 6.2 },
  { date: "07-10", value: 7.0 },
  { date: "07-11", value: 7.6 },
  { date: "07-12", value: 7.2 },
  { date: "07-13", value: 7.4 },
];

// --------------------------------------------------------------------
// 2. 小组件
// --------------------------------------------------------------------

const STAGE_TONE: Record<string, string> = {
  amber: "bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20",
  indigo: "bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-500/20",
  slate: "bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20",
  emerald:
    "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20",
};

function CareBanner() {
  // 关怀 banner —— 一句温度问候 + 一个动作入口
  return (
    <Card className="relative overflow-hidden border-0 bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500 text-white">
      <div
        aria-hidden
        className="pointer-events-none absolute -right-10 -top-10 size-48 rounded-full bg-white/10 blur-2xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-8 left-1/3 size-32 rounded-full bg-white/10 blur-2xl"
      />
      <CardContent className="relative flex flex-col gap-4 py-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1.5">
          <div className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-0.5 text-xs font-medium backdrop-blur">
            <Sun className="size-3.5" />
            早安,今天是 7 月 13 日(周日)
          </div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            今天感觉如何?先从最重要的一件事开始。
          </h1>
          <p className="max-w-xl text-sm text-white/85">
            过去 7 天你提交了 28 份匹配,完成了 5 次面试。下一份心仪 offer
            可能就在这次对话里。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            asChild
            className="bg-white text-indigo-700 hover:bg-white/90"
            size="sm"
          >
            <Link href="/jobseeker/chat">
              <MessageSquare className="size-4" />
              和 AI 聊聊
            </Link>
          </Button>
          <Button
            asChild
            variant="ghost"
            className="text-white hover:bg-white/15"
            size="sm"
          >
            <Link href="/jobseeker/journal">
              <Mic className="size-4" />
              录一段今日心情
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function KpiGrid() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {KPIS.map((k) => {
        const Icon = k.icon;
        return (
          <Card key={k.key} className="relative overflow-hidden">
            <div
              aria-hidden
              className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${k.accent}`}
            />
            <CardContent className="relative space-y-2 p-4">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">{k.label}</p>
                <Icon className={`size-4 ${k.iconColor}`} />
              </div>
              <p className="text-2xl font-semibold tracking-tight">{k.value}</p>
              <div className="flex items-center justify-between text-xs">
                <span
                  className={
                    k.trend === "up"
                      ? "font-medium text-emerald-600 dark:text-emerald-400"
                      : k.trend === "down"
                        ? "font-medium text-rose-600 dark:text-rose-400"
                        : "text-muted-foreground"
                  }
                >
                  {k.delta}
                </span>
                <span className="text-muted-foreground line-clamp-1 text-right">
                  {k.hint}
                </span>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function AiEntry() {
  return (
    <Card className="bg-gradient-to-br from-indigo-50 via-white to-fuchsia-50 dark:from-indigo-950/30 dark:via-background dark:to-fuchsia-950/20">
      <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white shadow-sm">
            <Sparkles className="size-5" />
          </div>
          <div className="space-y-0.5">
            <h2 className="font-semibold">让 AI 帮你做下一步</h2>
            <p className="text-sm text-muted-foreground">
              告诉 Copilot 你今天的卡点,它会结合你的档案和当前机会给出可执行建议。
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm">
            <Link href="/jobseeker/chat">
              打开 Copilot
              <ArrowRight className="size-4" />
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href="/match">浏览匹配</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function JobRow({ job }: { job: (typeof RECOMMENDED_JOBS)[number] }) {
  return (
    <Link
      href={`/match/${job.id}`}
      className="group flex items-center gap-4 rounded-lg px-2 py-3 transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-sm font-medium text-muted-foreground">
        {job.company.slice(0, 2).toUpperCase()}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-sm font-medium">{job.title}</p>
          <Badge variant="outline" className="border-current/20">
            {job.company}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {job.location} · {job.salary}
        </p>
        <div className="flex flex-wrap items-center gap-1.5">
          {job.skills.map((s) => (
            <Badge key={s} variant="secondary" className="text-[10px]">
              {s}
            </Badge>
          ))}
          <span
            className={`inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${STAGE_TONE[job.stageTone]}`}
          >
            {job.stage}
          </span>
        </div>
      </div>
      <div className="hidden w-24 shrink-0 sm:block">
        <div className="flex items-baseline justify-between text-xs text-muted-foreground">
          <span>匹配度</span>
          <span className="font-semibold text-foreground">{job.match}</span>
        </div>
        <Progress value={job.match} className="mt-1 h-1.5" />
      </div>
      <ArrowUpRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
    </Link>
  );
}

function RecommendedJobs() {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Briefcase className="size-4 text-indigo-500" />
            为你推荐的 5 个机会
          </CardTitle>
          <CardDescription>基于档案 + 近期互动 · 每 30 分钟刷新</CardDescription>
        </div>
        <Button asChild variant="ghost" size="sm">
          <Link href="/match">
            全部
            <ChevronRight className="size-4" />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="px-2">
        <div className="divide-y">
          {RECOMMENDED_JOBS.map((job) => (
            <JobRow key={job.id} job={job} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function TodoList() {
  const [items, setItems] = React.useState(TODOS);
  const remaining = items.filter((t) => !t.done).length;
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle>今日待办</CardTitle>
          <CardDescription>
            还剩 {remaining} 项 · 完成后档案完整度 +6%
          </CardDescription>
        </div>
        <Button variant="ghost" size="sm">
          管理
        </Button>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.map((t) => (
          <label
            key={t.id}
            className="flex cursor-pointer items-start gap-3 rounded-md px-2 py-2 transition-colors hover:bg-muted/60"
          >
            <input
              type="checkbox"
              checked={t.done}
              onChange={() =>
                setItems((prev) =>
                  prev.map((p) =>
                    p.id === t.id ? { ...p, done: !p.done } : p,
                  ),
                )
              }
              className="mt-0.5 size-4 rounded border-input accent-indigo-500"
              aria-label={t.title}
            />
            <div className="min-w-0 flex-1">
              <p
                className={
                  t.done
                    ? "text-sm text-muted-foreground line-through"
                    : "text-sm"
                }
              >
                {t.title}
              </p>
              <p className="text-xs text-muted-foreground">{t.meta}</p>
            </div>
          </label>
        ))}
      </CardContent>
    </Card>
  );
}

function ActivityChart() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="size-4 text-emerald-500" />
          本周求职活动
        </CardTitle>
        <CardDescription>投递 / 面试 / 收到回复</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-44 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={ACTIVITY}
              margin={{ top: 4, right: 4, bottom: 0, left: -16 }}
            >
              <defs>
                <linearGradient id="g-app" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="g-int" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#f59e0b" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="g-rep" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
              <XAxis
                dataKey="day"
                tick={{ fontSize: 11, fill: "#64748b" }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#64748b" }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 8,
                  border: "1px solid #e2e8f0",
                }}
              />
              <Area
                type="monotone"
                dataKey="applications"
                stroke="#6366f1"
                fill="url(#g-app)"
                strokeWidth={2}
                name="投递"
              />
              <Area
                type="monotone"
                dataKey="interviews"
                stroke="#f59e0b"
                fill="url(#g-int)"
                strokeWidth={2}
                name="面试"
              />
              <Area
                type="monotone"
                dataKey="replies"
                stroke="#10b981"
                fill="url(#g-rep)"
                strokeWidth={2}
                name="回复"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-indigo-500" />
            投递 28
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-amber-500" />
            面试 5
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-emerald-500" />
            回复 21
          </span>
          <Separator orientation="vertical" className="h-3" />
          <span>回复率 75% · 高于同类候选人 22%</span>
        </div>
      </CardContent>
    </Card>
  );
}

function MoodTrend() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Heart className="size-4 text-rose-500" />
          情绪趋势 · 近 7 天
        </CardTitle>
        <CardDescription>
          来自日记和语音日记 · 由情绪智能体每日聚合
        </CardDescription>
      </CardHeader>
      <CardContent>
        <TimeSeriesChart data={MOOD_TREND} color="#f43f5e" height={180} />
        <p className="mt-3 text-xs text-muted-foreground">
          周四的小高峰来自收到 Tidewave 面试邀请。可以继续记录本周心情,
          让 AI 更懂你。
        </p>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------
// 3. 页面
// --------------------------------------------------------------------

export default function JobseekerHomePage() {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-4 lg:p-8">
      <CareBanner />
      <KpiGrid />
      <AiEntry />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <RecommendedJobs />
        </div>
        <div>
          <TodoList />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <ActivityChart />
        </div>
        <div className="lg:col-span-2">
          <MoodTrend />
        </div>
      </div>
    </div>
  );
}
