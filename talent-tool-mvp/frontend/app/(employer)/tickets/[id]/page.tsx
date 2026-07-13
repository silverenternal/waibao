"use client";

/**
 * Ticket Detail — split-pane ticket view (Linear/GitHub inspired):
 *   - Left: ticket header + comments timeline
 *   - Right: sidebar with status, priority, assignee, tags
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
import { Textarea } from "@/components/ui/textarea";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { ChevronLeft, AlertCircle, User, Tag } from "lucide-react";

const SAMPLE = {
  id: "tk-1042",
  title: "复审：陈诺 degree 资质核验",
  status: "in_progress",
  priority: "p0",
  assignee: "Alex K.",
  reporter: "Sarah",
  created: "今天 14:21",
  labels: ["compliance", "fake-qual"],
  description:
    "ELA 噪点不均 + Photoshop EXIF；高度疑似伪造。建议联系候选人要求补传原件。",
  timeline: [
    { at: "14:21", author: "system", body: "自动升级 · PSDetectionBadge 92%" },
    { at: "14:32", author: "Sarah", body: "已经联系候选人,10 分钟内补传新版本。" },
    { at: "15:08", author: "Alex", body: "收到新版本,正在重新跑对比。" },
  ],
};

export default function TicketDetailPage({ params }: { params: { id: string } }) {
  const t = SAMPLE;
  return (
    <div className="space-y-6 p-4 md:p-8">
      <Button variant="ghost" size="sm" asChild className="-ml-2 self-start">
        <Link href="/employer/tickets">
          <ChevronLeft className="mr-1 h-4 w-4" /> 看板
        </Link>
      </Button>

      <header className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight">{t.title}</h1>
            <Badge variant="destructive">P0</Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {t.id} · 由 {t.reporter} 创建于 {t.created}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">编辑</Button>
          <Button>关闭</Button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">描述</CardTitle>
            </CardHeader>
            <CardContent className="text-sm leading-relaxed">{t.description}</CardContent>
          </Card>
          <Tabs defaultValue="timeline">
            <TabsList>
              <TabsTrigger value="timeline">时间线</TabsTrigger>
              <TabsTrigger value="comments">评论</TabsTrigger>
            </TabsList>
            <TabsContent value="timeline">
              <Card>
                <CardContent className="space-y-3 p-4">
                  <ol className="space-y-3">
                    {t.timeline.map((it, i) => (
                      <li key={i} className="rounded-md border p-3 text-sm">
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>{it.author}</span>
                          <span>{it.at}</span>
                        </div>
                        <p className="mt-1">{it.body}</p>
                      </li>
                    ))}
                  </ol>
                  <Separator />
                  <Textarea rows={3} placeholder="新增评论..." />
                  <Button size="sm">提交</Button>
                </CardContent>
              </Card>
            </TabsContent>
            <TabsContent value="comments">
              <Card>
                <CardContent className="p-4 text-sm text-muted-foreground">
                  暂无评论。
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">属性</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Row icon={<AlertCircle className="h-4 w-4" />} label="状态" value={<Badge>{t.status}</Badge>} />
            <Row icon={<AlertCircle className="h-4 w-4" />} label="优先级" value={<Badge variant="destructive">P0</Badge>} />
            <Row icon={<User className="h-4 w-4" />} label="处理人" value={t.assignee} />
            <Row icon={<Tag className="h-4 w-4" />} label="标签" value={
              <div className="flex flex-wrap gap-1">
                {t.labels.map((l) => <Badge key={l} variant="outline">{l}</Badge>)}
              </div>
            } />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="inline-flex items-center gap-2 text-muted-foreground">
        {icon}
        {label}
      </span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
