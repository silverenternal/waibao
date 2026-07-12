"use client";

/**
 * T1403 — Jobseeker dashboard.
 *
 *   - 默认首页 (访客登录后落地).
 *   - 首次访问自动触发 ProductTour 高亮核心入口.
 *   - 右侧悬浮 OnboardingChecklist 跟踪 4 步 onboarding 进度.
 *
 * 设计原则见 docs/ONBOARDING_DESIGN.md.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, Sparkles, Bell, Inbox, Compass } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { OnboardingChecklist } from "@/components/OnboardingChecklist";
import { ProductTour, type TourStep } from "@/components/ProductTour";
import {
  useOnboarding,
  isProductTourDone,
  markProductTourDone,
} from "@/hooks/use-onboarding";

export default function JobseekerDashboardPage() {
  const router = useRouter();
  const ob = useOnboarding("jobseeker");
  const [tourOpen, setTourOpen] = React.useState(false);

  // Auto-open tour on first visit (gated by localStorage flag in hook).
  React.useEffect(() => {
    if (!isProductTourDone()) {
      setTourOpen(true);
    }
  }, []);

  const tourSteps: TourStep[] = [
    {
      targetSelector: "[data-tour='matches']",
      title: "AI 智能匹配",
      content:
        "把你的档案和岗位 JD 做结构化 + 语义双路打分,前 10 名透明可解释。",
    },
    {
      targetSelector: "[data-tour='profile']",
      title: "完善你的档案",
      content: "上传简历或手动填写,完整度越高,推荐越精准。",
    },
    {
      targetSelector: "[data-tour='inbox']",
      title: "消息中心",
      content: "招聘顾问消息、工单状态、活动提醒都在这里。",
    },
  ];

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
      <header className="mb-8">
        <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
          <Sparkles className="size-3.5" />
          欢迎回来
        </div>
        <h1 className="mt-4 text-3xl font-bold tracking-tight">
          今天为你的求职旅程做点什么?
        </h1>
        <p className="mt-2 text-base text-muted-foreground">
          继续完善档案、查看 AI 匹配、或联系招聘顾问。
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="grid gap-4 sm:grid-cols-2">
          <Link
            href="/match"
            data-tour="matches"
            className="group rounded-xl border bg-card p-5 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <div className="flex items-start justify-between">
              <Compass className="size-5 text-primary" />
              <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-1" />
            </div>
            <h2 className="mt-4 text-lg font-semibold">AI 智能匹配</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              浏览为你推荐的岗位,前 10 名带完整推理链。
            </p>
          </Link>

          <Link
            href="/jobseeker/profile"
            data-tour="profile"
            className="group rounded-xl border bg-card p-5 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <div className="flex items-start justify-between">
              <Sparkles className="size-5 text-emerald-500" />
              <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-1" />
            </div>
            <h2 className="mt-4 text-lg font-semibold">完善我的档案</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              完善度越高,匹配越好。30 秒搞定。
            </p>
          </Link>

          <Link
            href="/my-tickets"
            data-tour="inbox"
            className="group rounded-xl border bg-card p-5 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <div className="flex items-start justify-between">
              <Inbox className="size-5 text-amber-500" />
              <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-1" />
            </div>
            <h2 className="mt-4 text-lg font-semibold">消息中心</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              工单 + 顾问消息 + 活动提醒一站式管理。
            </p>
          </Link>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Bell className="size-4 text-blue-500" />
                今日提醒
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              <p>
                完成 4 步 onboarding 解锁全部功能,当前进度{" "}
                <span className="font-medium text-foreground">
                  {Math.round(ob.progress * 100)}%
                </span>
                。
              </p>
              <Button
                size="sm"
                className="mt-4"
                onClick={() => router.push("/jobseeker/onboarding")}
              >
                继续 onboarding
                <ArrowRight className="ml-2 size-4" />
              </Button>
            </CardContent>
          </Card>
        </div>

        <aside>
          <OnboardingChecklist role="jobseeker" />
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
    </div>
  );
}
