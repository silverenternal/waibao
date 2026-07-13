"use client";

/**
 * HR Active Suggestions page — v8.1 T3709.
 *
 * DailySuggestions component renders the feed. We wrap it in a layout that
 * also exposes a settings panel (frequency / channel preferences).
 */

import * as React from "react";
import dynamic from "next/dynamic";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Bell, Sparkles, Settings } from "lucide-react";

const DailySuggestions = dynamic(
  () => import("@/components/hr/DailySuggestions").then((m) => m.DailySuggestions),
  { ssr: false },
);

export default function HRSuggestionsPage() {
  return (
    <div className="space-y-6 p-4 md:p-8">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            <h1 className="text-2xl font-bold tracking-tight md:text-3xl">HR 主动建议</h1>
            <Badge variant="secondary">v8.1 T3709</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            早 9:00 推送今天的招聘机会与风险,提升 30% 转化。
          </p>
        </div>
        <Button variant="outline">
          <Settings className="mr-1 h-4 w-4" />
          通知偏好
        </Button>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">今日建议</CardTitle>
            </CardHeader>
            <CardContent>
              <DailySuggestions />
            </CardContent>
          </Card>
        </div>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Bell className="h-4 w-4" />
              推荐设置
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p>· 推送时间: 每日早 9:00</p>
            <p>· 频率: 高优先级即时,普通每日聚合</p>
            <p>· 通道: 站内 + 邮件</p>
            <p>· 学习周期: 14 天滚动窗口</p>
            <Button variant="outline" size="sm" className="w-full">
              调整设置
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">触发逻辑</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm text-muted-foreground">
          <p>· offer 已等 ≥3 天 → P1 紧急</p>
          <p>· 面试 ≤24h 未提醒 → P1 紧急</p>
          <p>· 工单 ≥48h → P1 紧急</p>
          <p>· 候选人等待 ≥7 天无回应 → P4 关怀</p>
          <p>· JD ≥14 天未优化 → P5 复审</p>
        </CardContent>
      </Card>
    </div>
  );
}
