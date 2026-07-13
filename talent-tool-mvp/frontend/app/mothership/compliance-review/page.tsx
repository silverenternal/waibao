"use client";

/**
 * Compliance Review — v8.1 T3702 (假资质 AI 检测).
 *
 * Layout inspired by Notion's reviewer dashboard:
 *   - Left: VerificationScore panel + ELA image preview
 *   - Right: queue with PSDetectionBadge + manual actions
 *   - Below: Cross-source mismatch timeline
 */

import * as React from "react";
import dynamic from "next/dynamic";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ShieldCheck,
  ShieldAlert,
  ChevronRight,
  Image as ImageIcon,
  History,
  Sparkles,
} from "lucide-react";
import {
  PSDetectionBadge,
  PSDetectionBreakdown,
  type PSFinding,
} from "@/components/compliance/PSDetectionBadge";

const VerificationScore = dynamic(
  () => import("@/components/compliance/VerificationScore").then((m) => m.VerificationScore),
  { ssr: false },
);

interface QueueItem {
  id: string;
  candidate: string;
  doc: string;
  suspicion: number;
  findings: PSFinding[];
  escalated: boolean;
  submittedAt: string;
}

const SAMPLE_QUEUE: QueueItem[] = [
  {
    id: "Q-1042",
    candidate: "陈诺",
    doc: "degree.pdf",
    suspicion: 0.92,
    findings: [
      { code: "ela_inhomogeneous", label: "ELA 噪点不均", severity: 0.93, detail: "照片区域 ELA 残留伪影" },
      { code: "exif_software", label: "Photoshop 软件指纹", severity: 0.87 },
      { code: "cross_source", label: "学信网不一致", severity: 0.81 },
    ],
    escalated: true,
    submittedAt: "今天 14:21",
  },
  {
    id: "Q-1041",
    candidate: "林夏",
    doc: "license.jpg",
    suspicion: 0.71,
    findings: [
      { code: "ela_inhomogeneous", label: "ELA 噪点不均", severity: 0.71 },
      { code: "expiry_warning", label: "90 天内到期", severity: 0.65 },
    ],
    escalated: false,
    submittedAt: "今天 11:08",
  },
  {
    id: "Q-1040",
    candidate: "周野",
    doc: "credit_code.png",
    suspicion: 0.18,
    findings: [],
    escalated: false,
    submittedAt: "昨天 22:45",
  },
];

export default function ComplianceReviewPage() {
  const [queue] = React.useState<QueueItem[]>(SAMPLE_QUEUE);
  const [active, setActive] = React.useState<QueueItem>(SAMPLE_QUEUE[0]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 md:p-8">
      <header className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
            合规复审 · Compliance Review
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            v8.1 T3702 — ELA + 噪点 + 哈希 + EXIF + 跨源 + 过期；自动 ≥ 0.85 转人工。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline">导出报告</Button>
          <Button>
            <Sparkles className="mr-1 h-4 w-4" />
            复核全部
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>{active.candidate} · {active.doc}</CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">
                  提交于 {active.submittedAt} · 编号 {active.id}
                </p>
              </div>
              <PSDetectionBadge
                suspicion={active.suspicion}
                findings={active.findings}
                escalated={active.escalated}
              />
            </CardHeader>
            <CardContent>
              <Tabs defaultValue="ela" className="w-full">
                <TabsList>
                  <TabsTrigger value="ela">
                    <ImageIcon className="mr-1 h-3 w-3" />
                    ELA 视图
                  </TabsTrigger>
                  <TabsTrigger value="checks">
                    <ShieldCheck className="mr-1 h-3 w-3" />
                    多维检查
                  </TabsTrigger>
                  <TabsTrigger value="history">
                    <History className="mr-1 h-3 w-3" />
                    历史
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="ela" className="space-y-3">
                  <VerificationScore target={active.doc} />
                </TabsContent>
                <TabsContent value="checks">
                  <PSDetectionBreakdown findings={active.findings} />
                </TabsContent>
                <TabsContent value="history">
                  <ol className="space-y-2 text-sm">
                    <li className="flex gap-3 rounded-md border p-2">
                      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <div>
                        <div>候选人上传</div>
                        <div className="text-xs text-muted-foreground">{active.submittedAt}</div>
                      </div>
                    </li>
                    <li className="flex gap-3 rounded-md border p-2">
                      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <div>
                        <div>自动检测</div>
                        <div className="text-xs text-muted-foreground">ELA + EXIF + 跨源</div>
                      </div>
                    </li>
                    {active.escalated && (
                      <li className="flex gap-3 rounded-md border border-rose-300 bg-rose-50 p-2 dark:bg-rose-950/30">
                        <ShieldAlert className="h-4 w-4 shrink-0 text-rose-500" />
                        <div>
                          <div className="font-medium text-rose-700 dark:text-rose-300">
                            自动升级到合规官
                          </div>
                          <div className="text-xs text-rose-700/80 dark:text-rose-300/80">
                            高于阈值 0.85
                          </div>
                        </div>
                      </li>
                    )}
                  </ol>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">待复审队列 ({queue.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {queue.map((it) => (
                <li key={it.id}>
                  <button
                    onClick={() => setActive(it)}
                    className={`flex w-full items-center justify-between gap-2 rounded-md border p-2 text-left text-sm transition-colors hover:bg-muted/60 ${
                      it.id === active.id ? "border-primary bg-primary/5" : ""
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{it.candidate}</div>
                      <div className="truncate text-xs text-muted-foreground">{it.doc}</div>
                    </div>
                    <PSDetectionBadge
                      suspicion={it.suspicion}
                      escalated={it.escalated}
                    />
                  </button>
                </li>
              ))}
            </ul>
            <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
              <Badge variant="outline">{queue.filter((q) => q.escalated).length} 已升级</Badge>
              <span>{queue.length - queue.filter((q) => q.escalated).length} 待办</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
