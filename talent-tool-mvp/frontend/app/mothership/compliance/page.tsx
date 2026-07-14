"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Compliance index — landing page for v8.1 T3702.
 *
 * Renders three KPI tiles (today's volume, escalated %, signatures cleared)
 * and surfaces a feed of recent compliance events with PSDetectionBadge +
 * quick links into the review queue.
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
import {
  PSDetectionBadge,
  type PSFinding,
} from "@/components/compliance/PSDetectionBadge";
import { ChevronRight, ShieldCheck, ShieldAlert, Activity } from "lucide-react";

interface ComplianceEvent {
  id: string;
  candidate: string;
  action: string;
  suspicion: number;
  findings: PSFinding[];
  ts: string;
}

const SAMPLE_EVENTS: ComplianceEvent[] = [
  { id: "E-1", candidate: "陈诺", action: "上传 degree.pdf", suspicion: 0.92, findings: [], ts: "14:21" },
  { id: "E-2", candidate: "韩冬", action: "OCR 比对通过", suspicion: 0.05, findings: [], ts: "13:55" },
  { id: "E-3", candidate: "林夏", action: "license.jpg 复核", suspicion: 0.71, findings: [], ts: "11:08" },
  { id: "E-4", candidate: "周野", action: "credit_code.png", suspicion: 0.18, findings: [], ts: "昨天 22:45" },
];

export default function ComplianceIndexPage() {
  return (
    <ErrorBoundary>(<div className="mx-auto max-w-6xl space-y-6 p-4 md:p-8">
        <header>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">合规中心</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            资质审查、隐私合规、签字存档的统一入口。
          </p>
        </header>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <KpiCard label="今日核验" value={124} icon={<Activity className="h-4 w-4" />} />
          <KpiCard
            label="自动升级"
            value={5}
            icon={<ShieldAlert className="h-4 w-4" />}
            tone="rose"
          />
          <KpiCard
            label="签字完成"
            value={86}
            icon={<ShieldCheck className="h-4 w-4" />}
            tone="emerald"
          />
          <KpiCard label="平均时效" value="3.2h" icon={<Activity className="h-4 w-4" />} />
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>今日活动流</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="divide-y">
                {SAMPLE_EVENTS.map((e) => (
                  <li
                    key={e.id}
                    className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
                  >
                    <div>
                      <div className="text-sm font-medium">
                        {e.candidate} · <span className="text-muted-foreground">{e.action}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">{e.ts}</div>
                    </div>
                    <PSDetectionBadge suspicion={e.suspicion} />
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>常用入口</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Link
                href="/mothership/compliance-review"
                className="flex items-center justify-between rounded-md p-2 hover:bg-muted"
              >
                <span>复审队列</span>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </Link>
              <Link
                href="/mothership/compliance-review?tab=history"
                className="flex items-center justify-between rounded-md p-2 hover:bg-muted"
              >
                <span>跨源比对</span>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </Link>
              <Link
                href="/mothership/admin/audit"
                className="flex items-center justify-between rounded-md p-2 hover:bg-muted"
              >
                <span>审计日志</span>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </Link>
            </CardContent>
          </Card>
        </div>
        <div className="flex justify-end">
          <Button asChild>
            <Link href="/mothership/compliance-review">
              进入复审队列 <ChevronRight className="ml-1 h-4 w-4" />
            </Link>
          </Button>
        </div>
      </div>)</ErrorBoundary>
  );
}

function KpiCard({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  tone?: "rose" | "emerald";
}) {
  const toneCls =
    tone === "rose"
      ? "text-rose-700 dark:text-rose-300 bg-rose-500/10"
      : tone === "emerald"
      ? "text-emerald-700 dark:text-emerald-300 bg-emerald-500/10"
      : "text-muted-foreground bg-muted";
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        <span className={`rounded p-1.5 ${toneCls}`}>{icon}</span>
      </div>
      <div className="mt-3 text-2xl font-bold tabular-nums">{value}</div>
    </Card>
  );
}
