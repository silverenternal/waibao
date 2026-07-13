"use client";

/**
 * Candidate detail — Notion-style three-pane:
 *   - Top: candidate profile summary + match score
 *   - Middle left: AI-extracted fields
 *   - Middle right: pipeline progression
 *   - Bottom: AI conversation history + rooms link
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  ChevronLeft,
  Star,
  Sparkles,
  MessagesSquare,
  FileText,
  Calendar,
  ExternalLink,
} from "lucide-react";

const SAMPLE = {
  id: "c-101",
  name: "陈诺",
  email: "chennuo@example.com",
  phone: "+86 138 0000 0001",
  location: "上海",
  role: "高级前端工程师",
  match: 88,
  stage: "面试",
  source: "LinkedIn",
  applied: "今天",
  experience: "6 年",
  rating: 4.6,
  skills: ["React", "TypeScript", "Next.js", "Tailwind", "设计系统", "Performance"],
  pipeline: [
    { stage: "推荐", at: "今天 09:21" },
    { stage: "联系", at: "今天 10:42" },
    { stage: "简历筛选", at: "今天 14:08" },
    { stage: "面试", at: "今天 16:30" },
    { stage: "Offer", at: "" },
  ],
  aiSummary:
    "陈诺是一位 6 年 React 专家,过去 2 年专注 SaaS 设计系统建设,最近一份工作主导团队从 CRA 迁移到 Next.js App Router,LCP 优化从 4.5s 降到 1.8s。对我们的 HR Dashboard 高度相关。",
  rooms: [
    { id: "rm-1", title: "面试 1 · 技术", unread: 2 },
    { id: "rm-2", title: "画像澄清", unread: 0 },
  ],
};

export default function CandidateDetailPage({ params }: { params: { id: string } }) {
  const c = SAMPLE;
  return (
    <div className="space-y-6 p-4 md:p-8">
      <Button variant="ghost" size="sm" asChild className="-ml-2 self-start">
        <Link href="/employer/candidates">
          <ChevronLeft className="mr-1 h-4 w-4" /> 返回列表
        </Link>
      </Button>

      <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-4">
          <Avatar className="h-16 w-16">
            <AvatarFallback className="bg-primary/10 text-xl text-primary">
              {c.name.charAt(0)}
            </AvatarFallback>
          </Avatar>
          <div>
            <h1 className="text-2xl font-bold tracking-tight md:text-3xl">{c.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {c.role} · {c.location} · {c.experience}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge className="gap-1">
                <Sparkles className="h-3 w-3" /> 匹配 {c.match}
              </Badge>
              <Badge variant="secondary">{c.stage}</Badge>
              <Badge variant="outline">{c.source}</Badge>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline">
            <Star className="mr-1 h-4 w-4" /> Star
          </Button>
          <Button variant="outline">
            <Calendar className="mr-1 h-4 w-4" /> 约面
          </Button>
          <Button>
            <MessagesSquare className="mr-1 h-4 w-4" /> 进入协同
          </Button>
        </div>
      </header>

      <Tabs defaultValue="summary">
        <TabsList>
          <TabsTrigger value="summary">总结</TabsTrigger>
          <TabsTrigger value="pipeline">进度</TabsTrigger>
          <TabsTrigger value="rooms">协同 ({c.rooms.length})</TabsTrigger>
          <TabsTrigger value="docs">简历</TabsTrigger>
        </TabsList>

        <TabsContent value="summary" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">AI 总结 · v8.1 T3705</CardTitle>
            </CardHeader>
            <CardContent className="text-sm leading-relaxed">{c.aiSummary}</CardContent>
          </Card>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">技能</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {c.skills.map((s) => (
                  <Badge key={s} variant="secondary">{s}</Badge>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">联系方式</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <div>{c.email}</div>
                <div>{c.phone}</div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="pipeline">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">应聘进度</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="relative ml-3 border-l border-dashed pl-6">
                {c.pipeline.map((p, i) => (
                  <li key={i} className="mb-5 last:mb-0">
                    <span
                      className={`absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full ring-4 ${
                        p.at
                          ? "bg-emerald-500 ring-emerald-200"
                          : "bg-muted ring-muted/30"
                      }`}
                    />
                    <div className="text-sm font-medium">{p.stage}</div>
                    <div className="text-xs text-muted-foreground">{p.at || "待进行"}</div>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="rooms">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {c.rooms.map((r) => (
              <Card key={r.id}>
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <div className="font-medium">{r.title}</div>
                    <div className="text-xs text-muted-foreground">
                      {r.unread} 未读
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" asChild>
                    <Link href={`/employer/rooms/${r.id}`}>
                      打开 <ExternalLink className="ml-1 h-3 w-3" />
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="docs">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">简历 / 附件</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2 text-sm">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <span>chennuo_resume.pdf</span>
                <Button variant="ghost" size="sm" className="ml-auto">
                  <ExternalLink className="mr-1 h-3 w-3" /> 打开
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">HR 反馈</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="text-muted-foreground">
            这位候选人您是否合适？提交反馈将自动调整模型权重（v8.1 T3710）。
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline">
              👍 合适
            </Button>
            <Button size="sm" variant="outline">
              👎 不合适
            </Button>
            <Button size="sm" variant="outline">
              ⏸ 继续观察
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
