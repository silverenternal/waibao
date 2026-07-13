"use client";

/**
 * Role Detail — split-pane, OpenResume + Cal.com feel:
 *   - Left: JD preview + score sidebar
 *   - Right: pipeline + candidate list
 */

import * as React from "react";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  MapPin,
  Briefcase,
  Users2,
  Sparkles,
  ExternalLink,
  History,
} from "lucide-react";
import { JDScorer } from "@/components/jd/JDScorer";
import { JDTemplatePicker } from "@/components/jd/JDTemplatePicker";
import { JDVersionHistory } from "@/components/jd/JDVersionHistory";
import { JDVersionDiff } from "@/components/jd/JDVersionDiff";

const SAMPLE_ROLE = {
  id: "r-101",
  title: "高级前端工程师",
  department: "技术",
  location: "北京",
  openings: 2,
  hiringManager: "Sarah Lee",
  recruiter: "Alex K.",
  postedAt: "2026-06-12",
  status: "open" as const,
  salaryRange: "30-55k · 14 薪",
  description:
    "我们正在构建下一代 AI Agent 协作平台,前端是核心体验。团队由 8 名工程师组成,使用 React 19 + Next.js 16 + Tailwind CSS v4。",
  responsibilities: [
    "负责 waibao Mothership HR Dashboard 的核心交互研发",
    "推进组件库 (shadcn-style) 在 5+ 子产品落地",
    "主导 Performance / A11y 优化 (LCP < 2s, WCAG AA)",
  ],
  required: ["5+ 年 React 经验", "熟悉 SSR / RSC", "开源贡献者优先"],
  bonus: ["设计系统建设经验", "TypeScript 类型体操"],
  candidates: [
    { id: "c-1", name: "陈诺", stage: "面试", match: 88, applied: "昨天" },
    { id: "c-2", name: "周野", stage: "联系", match: 76, applied: "3 天前" },
    { id: "c-3", name: "Lin", stage: "推荐", match: 71, applied: "5 天前" },
    { id: "c-4", name: "Maya", stage: "推荐", match: 68, applied: "1 周前" },
  ],
};

export default function RoleDetailPage({ params }: { params: { id: string } }) {
  const r = SAMPLE_ROLE;
  return (
    <div className="space-y-6 p-4 md:p-8">
      <header className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight md:text-3xl">{r.title}</h1>
            <Badge variant="secondary">{r.status}</Badge>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Briefcase className="h-3.5 w-3.5" />
              {r.department} · HC {r.openings}
            </span>
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5" />
              {r.location}
            </span>
            <span className="inline-flex items-center gap-1">
              <Users2 className="h-3.5 w-3.5" />
              HR {r.hiringManager} · Recruiter {r.recruiter}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild>
            <Link href={`/employer/roles/${params.id}/marketing`}>
              <Sparkles className="mr-1 h-4 w-4" />
              营销化
            </Link>
          </Button>
          <Button variant="outline">
            <History className="mr-1 h-4 w-4" />
            历史
          </Button>
          <Button>
            <ExternalLink className="mr-1 h-4 w-4" />
            发布
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">JD 详情</CardTitle>
              <p className="text-xs text-muted-foreground">{r.salaryRange}</p>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <p>{r.description}</p>
              <div>
                <h4 className="mb-1 font-medium">职责</h4>
                <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                  {r.responsibilities.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <h4 className="mb-1 font-medium">必备</h4>
                  <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                    {r.required.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h4 className="mb-1 font-medium">加分</h4>
                  <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                    {r.bonus.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">营销化 · Marketing Pack</CardTitle>
              <p className="text-xs text-muted-foreground">
                v8.1 T3705 · 故事化 + SEO + A/B + 4 维评分
              </p>
            </CardHeader>
            <CardContent>
              <JDScorer />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">版本历史</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <JDVersionHistory roleId={SAMPLE_ROLE.id} />
              <Separator />
              <JDVersionDiff current="" baseline={null} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">模板</CardTitle>
            </CardHeader>
            <CardContent>
              <JDTemplatePicker />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">候选人 ({r.candidates.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="divide-y">
                {r.candidates.map((c) => (
                  <li
                    key={c.id}
                    className="flex items-center justify-between py-2 text-sm first:pt-0 last:pb-0"
                  >
                    <div>
                      <div className="font-medium">{c.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {c.stage} · {c.applied}
                      </div>
                    </div>
                    <Badge variant="outline">{c.match} 分</Badge>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
