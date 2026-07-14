"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * T1106 — 招聘方 onboarding 欢迎页.
 */

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Briefcase, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { OnboardingChecklist } from "@/components/OnboardingChecklist";
import {
  ProductTour,
  type TourStep,
} from "@/components/ProductTour";
import {
  useOnboarding,
  markProductTourDone,
} from "@/hooks/use-onboarding";

export default function EmployerWelcomePage() {
  const router = useRouter();
  const ob = useOnboarding("employer");
  const [tourOpen, setTourOpen] = React.useState(true);

  const tourSteps: TourStep[] = [
    {
      targetSelector: "a[href='/employer/policy']",
      title: "公司画像",
      content: "在这里维护你的雇主品牌和文化关键词,匹配引擎会据此排序候选人。",
    },
    {
      targetSelector: "a[href='/employer/role']",
      title: "发布职位",
      content: "从模板快速创建 JD,AI 会自动补全技能 / 经验要求并提示过规范字段。",
    },
    {
      targetSelector: "a[href='/employer/strategy']",
      title: "候选人匹配",
      content: "为每个 JD 看到 AI 推荐的候选人,带完整解释与匹配评分。",
    },
    {
      targetSelector: "a[href='/employer/rooms']",
      title: "协作房间",
      content: "拉上招聘顾问、HR、候选人一起在协作房间讨论 offer 细节。",
    },
  ];

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-5xl px-4 py-10 sm:py-14">
        <header className="mb-8">
          <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
            <Briefcase className="size-3.5" />
            雇主端 · 欢迎使用 waibao
          </div>
          <h1 className="mt-4 text-3xl font-bold tracking-tight sm:text-4xl">
            找到最合适的候选人,只需 4 步
          </h1>
          <p className="mt-3 max-w-2xl text-base text-muted-foreground">
            waibao 把招聘流程拆成清晰的几步:发布职位 → AI 匹配候选人 →
            协作评审 → 创建 Handoff。每一环都自动留痕,合规可追溯。
          </p>
        </header>
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>第 1 步:完善公司档案</CardTitle>
                <CardDescription>
                  完善画像后,AI 匹配引擎才能精准推荐最契合的候选人。
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  size="lg"
                  onClick={() => router.push("/employer/policy")}
                  className="w-full sm:w-auto"
                >
                  开始完善
                  <ArrowRight className="ml-2 size-4" />
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>核心能力一览</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <FeatureItem
                  title="JD 模板库"
                  desc="10+ 行业模板,一键套用,AI 自动检测过规范字段。"
                />
                <FeatureItem
                  title="AI 匹配"
                  desc="候选人 vs JD,结构化 + 语义双路打分,带可解释推理链。"
                />
                <FeatureItem
                  title="协作房间"
                  desc="5 方实时协同:招聘顾问 + HR + 用人经理 + 候选人 + Copilot。"
                />
                <FeatureItem
                  title="Handoff 工单"
                  desc="候选人对岗位感兴趣 → 自动创建 handoff 工单进入面试流程。"
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>合规与审计</CardTitle>
                <CardDescription>
                  每一份访问、导出、修改都会写入不可篡改的审计日志 (T1004)。
                </CardDescription>
              </CardHeader>
              <CardContent className="text-sm">
                <ul className="space-y-2">
                  <li className="flex gap-2">
                    <span className="mt-1 size-1.5 rounded-full bg-primary" />
                    GDPR 数据访问请求自动响应
                  </li>
                  <li className="flex gap-2">
                    <span className="mt-1 size-1.5 rounded-full bg-primary" />
                    候选人 PII 加密存储 (T108)
                  </li>
                  <li className="flex gap-2">
                    <span className="mt-1 size-1.5 rounded-full bg-primary" />
                    Webhook 签名 + 重试队列 (T802)
                  </li>
                </ul>
                <Link
                  href="/employer/policy"
                  className="mt-3 inline-block text-xs text-primary underline"
                >
                  查看完整合规说明 →
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
                <Sparkles className="mr-1 size-3.5" />
                重新播放产品导览
              </Button>
            </div>
          </aside>
        </div>
        <ProductTour
          steps={tourSteps}
          open={tourOpen}
          onClose={() => setTourOpen(false)}
          onComplete={markProductTourDone}
        />
        {ob.isAllDone && (
          <div className="mt-8 rounded-xl border border-emerald-200/60 bg-emerald-50 p-6 text-center">
            <p className="text-lg font-semibold text-emerald-700">
              全部 4 步已完成!你可以开始招聘了 🎉
            </p>
            <p className="mt-1 text-sm text-emerald-600">
              <Link className="underline" href="/employer/role">去发布第一个职位</Link>
            </p>
          </div>
        )}
      </div>)</ErrorBoundary>
  );
}

function FeatureItem({ title, desc }: { title: string; desc: string }) {
  return (
    <div>
      <p className="font-medium">{title}</p>
      <p className="text-xs text-muted-foreground">{desc}</p>
    </div>
  );
}