"use client";
/**
 * HR Tone Configuration page — v8.1 T3701.
 *
 * Three sections:
 *   1. Live simulator (ToneSimulator w/ Open WebUI dual-pane preview)
 *   2. Tone learning history (timeline of past aggregations)
 *   3. Sample library (templates HR can fork)
 *
 * Page references the existing /api/v8_1_p2/tone/* backend.
 */

import * as React from "react";
import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Clock, Mic, MessagesSquare } from "lucide-react";

const ToneSimulator = dynamic(
  () => import("@/components/hr/ToneSimulator").then((m) => m.ToneSimulator),
  { ssr: false },
);

const TIMELINE = [
  { at: "今天 09:12", event: "画像再学习", detail: "样本 +18 主语气偏关系维护" },
  { at: "昨天 16:30", event: "手动覆盖 · 关系维护", detail: "候选人 林夏 反馈「像朋友一样」" },
  { at: "本周一", event: "新建模板 · 拒绝信", detail: "语气: 关系维护" },
  { at: "上周五", event: "画像更新", detail: "样本数突破 200,稳定在「关系+数据」" },
];

const TEMPLATES = [
  {
    id: "tpl-1",
    title: "拒信（友好+留口子）",
    tone: "关系维护",
    excerpt: "很高兴认识您…",
  },
  {
    id: "tpl-2",
    title: "面试邀请（数据+亲切）",
    tone: "数据驱动",
    excerpt: "本月已招聘 3 位工程经理…",
  },
  {
    id: "tpl-3",
    title: "Offer 沟通（正式）",
    tone: "正式得体",
    excerpt: "我们很荣幸地通知您…",
  },
];

export default function HRTonePage() {
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 md:p-8">
      <header className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">语气设置 · HR Tone</h1>
          <Badge variant="secondary">v8.1 T3701</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          让所有 HR 沟通按你 (老板) 的历史语气,而不是模板。
        </p>
      </header>

      <ToneSimulator />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Clock className="h-4 w-4" />
              学习时间线
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="relative ml-3 border-l border-dashed pl-6">
              {TIMELINE.map((t, i) => (
                <li key={i} className="mb-5 last:mb-0">
                  <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full bg-primary ring-4 ring-primary/15" />
                  <div className="text-xs text-muted-foreground">{t.at}</div>
                  <div className="text-sm font-medium">{t.event}</div>
                  <div className="text-xs text-muted-foreground">{t.detail}</div>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <MessagesSquare className="h-4 w-4" />
              模板库 ({TEMPLATES.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {TEMPLATES.map((t) => (
              <React.Fragment key={t.id}>
                <div className="flex items-start justify-between gap-3 rounded-md p-2 hover:bg-muted/60">
                  <div>
                    <div className="font-medium">{t.title}</div>
                    <div className="text-xs text-muted-foreground">{t.excerpt}</div>
                  </div>
                  <Badge variant="outline">{t.tone}</Badge>
                </div>
                <Separator />
              </React.Fragment>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Mic className="h-4 w-4" />
            调优建议
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>1) 在「手动覆盖」选择你最常用的语气,系统会以它为种子;</p>
          <p>2) 当自动识别与你的直觉不符时,选择「手动覆盖」并保存,系统会再学习;</p>
          <p>3) 每次和候选人聊天后,系统都会再学习一点点 — 让语气越来越像你。</p>
        </CardContent>
      </Card>
    </div>
  );
}
