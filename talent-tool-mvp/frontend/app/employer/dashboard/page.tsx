"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * T1403 — Employer dashboard.
 *
 *   - 招聘方首页 (雇主登录后落地).
 *   - 首次访问自动播放 ProductTour.
 *   - 联动 OnboardingChecklist 跟踪 4 步 onboarding.
 */

import * as React from "react";
import Link from "next/link";
import { ArrowRight, Sparkles, Briefcase, Users, MessageSquare } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { OnboardingChecklist } from "@/components/OnboardingChecklist";
import { ProductTour, type TourStep } from "@/components/ProductTour";
import {
  useOnboarding,
  isProductTourDone,
  markProductTourDone,
} from "@/hooks/use-onboarding";

export default function EmployerDashboardPage() {
  const ob = useOnboarding("employer");
  const [tourOpen, setTourOpen] = React.useState(false);

  React.useEffect(() => {
    if (!isProductTourDone()) {
      setTourOpen(true);
    }
  }, []);

  const tourSteps: TourStep[] = [
    {
      targetSelector: "[data-tour='roles']",
      title: "发布职位",
      content: "从模板快速创建 JD,AI 会自动补全技能 / 经验要求。",
    },
    {
      targetSelector: "[data-tour='candidates']",
      title: "候选人匹配",
      content: "为每个 JD 看到 AI 推荐的候选人,带完整解释。",
    },
    {
      targetSelector: "[data-tour='rooms']",
      title: "协作房间",
      content: "拉上顾问 + HR + 用人经理一起在协作房间讨论 offer。",
    },
  ];

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
        <header className="mb-8">
          <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
            <Briefcase className="size-3.5" />
            招聘方工作台
          </div>
          <h1 className="mt-4 text-3xl font-bold tracking-tight">
            今天为你的招聘流程做点什么?
          </h1>
          <p className="mt-2 text-base text-muted-foreground">
            发布职位、查看匹配、跟踪候选人 — 全流程协作。
          </p>
        </header>
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="grid gap-4 sm:grid-cols-2">
            <Link
              href="/role/new"
              data-tour="roles"
              className="group rounded-xl border bg-card p-5 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="flex items-start justify-between">
                <Briefcase className="size-5 text-primary" />
                <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-1" />
              </div>
              <h2 className="mt-4 text-lg font-semibold">发布职位</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                模板 + AI 自动补全,3 分钟发完。
              </p>
            </Link>

            <Link
              href="/candidates"
              data-tour="candidates"
              className="group rounded-xl border bg-card p-5 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="flex items-start justify-between">
                <Users className="size-5 text-emerald-500" />
                <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-1" />
              </div>
              <h2 className="mt-4 text-lg font-semibold">候选人匹配</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                AI 推荐前 10 名候选人 + 完整解释。
              </p>
            </Link>

            <Link
              href="/rooms"
              data-tour="rooms"
              className="group rounded-xl border bg-card p-5 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="flex items-start justify-between">
                <MessageSquare className="size-5 text-amber-500" />
                <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-1" />
              </div>
              <h2 className="mt-4 text-lg font-semibold">协作房间</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                顾问 + HR + 用人经理实时协同。
              </p>
            </Link>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Sparkles className="size-4 text-blue-500" />
                  当前进度
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                <p>
                  已完成 {ob.completed.size}/{ob.steps.length} 步 onboarding ·
                  进度 {Math.round(ob.progress * 100)}%
                </p>
                <Link
                  href="/employer/onboarding/welcome"
                  className="mt-4 inline-flex items-center text-sm font-medium text-primary hover:underline"
                >
                  查看完整 onboarding
                  <ArrowRight className="ml-1 size-4" />
                </Link>
              </CardContent>
            </Card>
          </div>

          <aside>
            <OnboardingChecklist role="employer" />
            <div className="mt-4 text-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setTourOpen(true)}
              >
                重新播放产品导览
              </Button>
            </div>
          </aside>
        </div>
        <ProductTour
          steps={tourSteps}
          open={tourOpen}
          onClose={() => setTourOpen(false)}
          onComplete={() => markProductTourDone()}
        />
      </div>)</ErrorBoundary>
  );
}
