"use client";

/**
 * T1106 — 求职者 onboarding 欢迎页 (首次登录后落地).
 *
 * 包含:
 * - 4 步 checklist (从 use-onboarding 拿步骤)
 * - 引导用户: 完善档案 -> 首次匹配 -> 约谈 -> 邀请同事
 * - 浮动的 ProductTour (高亮侧边导航)
 */

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Sparkles } from "lucide-react";

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

export default function JobseekerWelcomePage() {
  const router = useRouter();
  const ob = useOnboarding("jobseeker");
  const [tourOpen, setTourOpen] = React.useState(true);

  const tourSteps: TourStep[] = [
    {
      targetSelector: "a[href='/jobseeker/match']",
      title: "AI 智能匹配",
      content: "把你的档案和岗位 JD 做结构化 + 语义双路打分,前 10 名透明可解释。",
    },
    {
      targetSelector: "a[href='/jobseeker/onboarding']",
      title: "建档向导",
      content: "上传简历或手动填写,完整度越高,推荐越精准。",
    },
    {
      targetSelector: "a[href='/jobseeker/journal']",
      title: "情绪日记",
      content: "每周 30 秒记录心情,AI 会帮你发现趋势并给出建议。",
    },
  ];

  const handleTourComplete = () => {
    markProductTourDone();
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:py-14">
      <header className="mb-8">
        <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
          <Sparkles className="size-3.5" />
          欢迎使用 waibao
        </div>
        <h1 className="mt-4 text-3xl font-bold tracking-tight sm:text-4xl">
          让我们一起找到你心仪的工作
        </h1>
        <p className="mt-3 max-w-2xl text-base text-muted-foreground">
          waibao 是为英国/欧洲求职市场设计的 AI 招聘助理。完成下面 4 步,
          你就能收到个性化的工作推荐和 1:1 顾问服务。
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>从这里开始</CardTitle>
              <CardDescription>
                建议顺序:完善档案 → 浏览匹配 → 联系顾问 → 邀请朋友
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                size="lg"
                onClick={() => router.push("/jobseeker/onboarding")}
                className="w-full sm:w-auto"
              >
                完善我的档案
                <ArrowRight className="ml-2 size-4" />
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>你将体验到的功能</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3 text-sm">
                <FeatureItem
                  title="AI 匹配"
                  desc="结合你的技能、经验、偏好,前 10 名岗位透明打分。"
                />
                <FeatureItem
                  title="情绪日记"
                  desc="每周 30 秒,识别求职焦虑来源并给出建议。"
                />
                <FeatureItem
                  title="协作房间"
                  desc="招聘顾问、企业 HR 和你一起讨论岗位细节。"
                />
                <FeatureItem
                  title="1:1 约谈"
                  desc="对感兴趣的角色,直接联系顾问进行 1 对 1 沟通。"
                />
              </ul>
              <div className="mt-5 rounded-lg border border-dashed border-muted-foreground/30 p-4 text-xs text-muted-foreground">
                💡 想了解技术原理? <Link className="text-primary underline" href="/match">看匹配算法的演示</Link>
              </div>
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
        onComplete={handleTourComplete}
      />

      {ob.isAllDone && (
        <div className="mt-8 rounded-xl border border-emerald-200/60 bg-emerald-50 p-6 text-center">
          <p className="text-lg font-semibold text-emerald-700">
            太棒了!你已完成全部 4 步 🎉
          </p>
          <p className="mt-1 text-sm text-emerald-600">
            <Link className="underline" href="/match">去看看为你推荐的工作</Link>
          </p>
        </div>
      )}
    </div>
  );
}

function FeatureItem({ title, desc }: { title: string; desc: string }) {
  return (
    <li className="flex gap-3">
      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />
      <div>
        <p className="font-medium">{title}</p>
        <p className="text-xs text-muted-foreground">{desc}</p>
      </div>
    </li>
  );
}