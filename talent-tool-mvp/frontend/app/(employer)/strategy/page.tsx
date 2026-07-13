"use client";

/**
 * Strategy Map — v8.1 T3703.
 *
 * 4-layer stacked visualization (Vision → Planning → Strategy → Tactic).
 *
 * Each layer is a StrategyMap card with horizon + icon, color-banded for
 * instant scan-ability. Top = horizon (long), bottom = horizon (now).
 * Recruiters click a row to see AI's hiring impact (StrategyImpactCard) in a
 * side rail.
 *
 * Below the map: gap alerts and timeline.
 */

import * as React from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sparkles, ChevronRight, Layers } from "lucide-react";
import type { StrategyItem } from "@/lib/api-strategy";

const StrategyMap = dynamic(
  () => import("@/components/strategy/StrategyMap").then((m) => m.StrategyMap),
  { ssr: false },
);
const StrategyImpactCard = dynamic(
  () => import("@/components/strategy/StrategyImpactCard").then((m) => m.StrategyImpactCard),
  { ssr: false },
);
const StrategyTimeline = dynamic(
  () => import("@/components/strategy/StrategyTimeline").then((m) => m.StrategyTimeline),
  { ssr: false },
);
const StrategyDiffView = dynamic(
  () => import("@/components/strategy/StrategyDiff").then((m) => m.StrategyDiffView),
  { ssr: false },
);
const GapAlert = dynamic(
  () => import("@/components/strategy/GapAlert").then((m) => m.GapAlert),
  { ssr: false },
);

const NOW = new Date().toISOString();

const ITEMS: StrategyItem[] = [
  { id: "v1", level: "vision", title: "成为 AI Agent 时代的入口", description: "公司未来 3 年的北极星指标", horizon: "3y", owner_role: "CEO", owner_user_id: null, parent_id: null, organisation_id: "org-demo", status: "active", created_at: NOW, updated_at: NOW },
  { id: "p1", level: "planning", title: "Q2 国际化扩张", description: "英语岗位 +5，搭建海外 BD 团队", horizon: "Q2", owner_role: "COO", owner_user_id: null, parent_id: null, organisation_id: "org-demo", status: "active", created_at: NOW, updated_at: NOW },
  { id: "p2", level: "planning", title: "Q3 AI 全面升级", description: "全员 AI 工作流，淘汰重复性岗位", horizon: "Q3", owner_role: "CTO", owner_user_id: null, parent_id: null, organisation_id: "org-demo", status: "active", created_at: NOW, updated_at: NOW },
  { id: "s1", level: "strategy", title: "招聘 5 名英语 BD", description: "海外人才优先", horizon: "Q2 - Q3", owner_role: "Head of Sales", owner_user_id: null, parent_id: "p1", organisation_id: "org-demo", status: "active", created_at: NOW, updated_at: NOW },
  { id: "s2", level: "strategy", title: "算法 / Agent 工程团队 +12", description: "技术 leader 引荐优先", horizon: "Q2 - Q4", owner_role: "CTO", owner_user_id: null, parent_id: "p2", organisation_id: "org-demo", status: "active", created_at: NOW, updated_at: NOW },
  { id: "t1", level: "tactic", title: "本月 JD：英语 BD (海外)", description: "薪资 30-60k · Remote", horizon: "本周", owner_role: "Recruiter", owner_user_id: null, parent_id: "s1", organisation_id: "org-demo", status: "active", created_at: NOW, updated_at: NOW },
  { id: "t2", level: "tactic", title: "本月 JD：Agent 工程师", description: "薪资 35-70k · 加股权", horizon: "本周", owner_role: "Recruiter", owner_user_id: null, parent_id: "s2", organisation_id: "org-demo", status: "active", created_at: NOW, updated_at: NOW },
];

const ITEMS_BY_LEVEL: Partial<Record<string, StrategyItem[]>> = {
  vision: ITEMS.filter((i) => i.level === "vision"),
  planning: ITEMS.filter((i) => i.level === "planning"),
  strategy: ITEMS.filter((i) => i.level === "strategy"),
  tactic: ITEMS.filter((i) => i.level === "tactic"),
};

const PRESENT_LEVELS = Object.keys(ITEMS_BY_LEVEL).filter(
  (k) => (ITEMS_BY_LEVEL as any)[k]?.length,
);

export default function StrategyMapPage() {
  return (
    <div className="space-y-6 p-4 md:p-8">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" />
            <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
              战略地图 · Strategy Map
            </h1>
            <Badge variant="secondary">v8.1 T3703</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            四层（Vision · Planning · Strategy · Tactic）逐步缩进 — 招聘影响实时计算。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild>
            <Link href="/strategy/feed">
              <Sparkles className="mr-1 h-4 w-4" /> 战略 Feed
            </Link>
          </Button>
          <Button>
            <ChevronRight className="mr-1 h-4 w-4" /> 新发布
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">分层视图</CardTitle>
              <p className="text-xs text-muted-foreground">
                点任一行查看招聘影响 / 关联人才。
              </p>
            </CardHeader>
            <CardContent>
              <StrategyMap items={ITEMS_BY_LEVEL as any} />
            </CardContent>
          </Card>
        </div>
        <div className="space-y-4">
          <StrategyImpactCard />
          <GapAlert missing={["vision"]} />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">战略变更时间线</CardTitle>
        </CardHeader>
        <CardContent>
          <StrategyTimeline items={ITEMS} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">变更对照</CardTitle>
        </CardHeader>
        <CardContent>
          <StrategyDiffView before={[]} after={ITEMS} />
        </CardContent>
      </Card>
    </div>
  );
}
