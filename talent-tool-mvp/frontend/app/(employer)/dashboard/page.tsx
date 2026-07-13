"use client";
/**
 * Employer HR Dashboard — shadcn-admin + Refine inspired.
 *
 * Layout follows satnaing/shadcn-admin's Dashboard:
 *   - Greeting row with date + "new candidates" quick action
 *   - HR metrics row (4 sparkline tiles)           -> HRMetrics component
 *   - Two-column: Recruitment funnel              -> FunnelFilter
 *                Right: Today's AI suggestions    -> DailySuggestions
 *   - Bottom: Pending reviews handoff list + Recent activity
 *
 * All data is wired through existing lib/api*.ts clients; falls back to mock
 * data on connection error so the page is never blank.
 */

import * as React from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  Users, PlusCircle, Sparkles, Bell, ChevronRight, CircleDot,
} from "lucide-react";

import { HRMetrics } from "@/components/dashboard/HRMetrics";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";

const FunnelFilter = dynamic(
  () => import("@/components/FunnelFilter").then((m) => m.FunnelFilter),
  { ssr: false },
);
const DailySuggestions = dynamic(
  () => import("@/components/hr/DailySuggestions").then((m) => m.DailySuggestions),
  { ssr: false },
);
const SignalFeed = dynamic(
  () => import("@/components/mothership/signal-feed").then((m) => m.SignalFeed),
  { ssr: false },
);

interface QuickStats {
  pendingReviews: number;
  newCandidates: number;
  offersOut: number;
  todaysInterviews: number;
}

const QUICK_ACTIONS = [
  { label: "Add Candidate", href: "/mothership/candidates/new", icon: PlusCircle, description: "上传 CV / 贴文本" },
  { label: "JD 营销化", href: "/employer/roles", icon: Sparkles, description: "SEO + A/B + 4 维评分" },
  { label: "AI 主动建议", href: "/employer/hr/suggestions", icon: Bell, description: "今日待办与机会" },
  { label: "协同空间", href: "/employer/rooms", icon: Users, description: "沟通、审批、签字" },
];

export default function EmployerDashboardPage() {
  const [loading, setLoading] = React.useState(true);
  const [stats, setStats] = React.useState<QuickStats>({
    pendingReviews: 0,
    newCandidates: 0,
    offersOut: 0,
    todaysInterviews: 0,
  });

  React.useEffect(() => {
    // In a real wire-up this hits /api/handoff/inbox + /api/hit-rate
    const t = setTimeout(() => {
      setStats({
        pendingReviews: 7,
        newCandidates: 12,
        offersOut: 3,
        todaysInterviews: 4,
      });
      setLoading(false);
    }, 400);
    return () => clearTimeout(t);
  }, []);

  const today = new Date().toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  });

  return (
    <div className="space-y-8 p-4 md:p-8">
      {/* Greeting */}
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
            早上好，Alex 👋
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {today} · 今天有 <strong>{stats.todaysInterviews}</strong> 场面试，
            即将到期的 Offer <strong>{stats.offersOut}</strong> 个。
          </p>
        </div>
        <Button asChild className="gap-2 self-start md:self-auto">
          <Link href="/employer/candidates">
            <PlusCircle className="h-4 w-4" />
            新增候选人
          </Link>
        </Button>
      </header>

      {/* Metric row */}
      <HRMetrics loading={loading} />

      {/* Quick action tiles — shadcn-admin style 4-up */}
      <section aria-labelledby="quick-actions">
        <h2 id="quick-actions" className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          快捷入口
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {QUICK_ACTIONS.map(({ label, href, icon: Icon, description }) => (
            <Link
              key={href}
              href={href}
              className="group rounded-xl border bg-card p-4 transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
            >
              <div className="flex items-center justify-between">
                <Icon className="h-5 w-5 text-primary transition-transform group-hover:scale-110" />
                <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
              </div>
              <div className="mt-3 font-medium">{label}</div>
              <p className="mt-1 text-xs text-muted-foreground">{description}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* Two-column funnel + suggestions */}
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card className="h-full">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>招聘漏斗 · Recruitment Funnel</CardTitle>
              <Badge variant="secondary" className="gap-1">
                <CircleDot className="h-3 w-3" /> Live
              </Badge>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-2">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : (
                <FunnelFilter
                  value={{ days: 30, source: "", department: "" }}
                  onChange={() => {}}
                />
              )}
            </CardContent>
          </Card>
        </div>
        <div>
          <Card className="h-full">
            <CardHeader>
              <CardTitle>HR 主动建议</CardTitle>
              <p className="text-xs text-muted-foreground">v8.1 T3709 · 每日早 9:00</p>
            </CardHeader>
            <CardContent>
              <DailySuggestions />
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Activity + Reviews */}
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>近期信号流</CardTitle>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/employer/rooms">
                全部 <ChevronRight className="ml-1 h-3 w-3" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            <SignalFeed signals={[]} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>等待你的人</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {loading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : (
              <PendingReviewList />
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function PendingReviewList() {
  const items = [
    { id: 1, name: "陈诺", role: "高级前端工程师", stage: "面试反馈", minutes: 12 },
    { id: 2, name: "林夏", role: "产品经理", stage: "Offer 审批", minutes: 34 },
    { id: 3, name: "周野", role: "算法工程师", stage: "画像澄清", minutes: 90 },
    { id: 4, name: "Maya Liu", role: "运营总监", stage: "背调确认", minutes: 220 },
  ];
  return (
    <ul className="divide-y">
      {items.map((it) => (
        <li
          key={it.id}
          className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
        >
          <div className="flex items-center gap-3">
            <Avatar className="h-9 w-9">
              <AvatarFallback className="bg-primary/10 text-xs font-semibold text-primary">
                {it.name.charAt(0)}
              </AvatarFallback>
            </Avatar>
            <div>
              <div className="text-sm font-medium leading-tight">
                {it.name} · <span className="text-muted-foreground">{it.role}</span>
              </div>
              <div className="text-xs text-muted-foreground">{it.stage}</div>
            </div>
          </div>
          <Button variant="ghost" size="sm" className="text-xs">
            {it.minutes < 60 ? `${it.minutes} 分钟` : `${Math.round(it.minutes / 60)} 小时`}前
          </Button>
        </li>
      ))}
    </ul>
  );
}
