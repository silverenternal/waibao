"use client";

/**
 * Candidates Manager — shadcn-admin DataTable pattern.
 *
 * Sortable, filterable, multi-select. Mobile-friendly via horizontal scroll.
 * Bulk actions: bulk archive / bulk move to role / bulk export (CSV/Excel).
 *
 * Reuses our shared DataTable (built on @tanstack/react-table).
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
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  PlusCircle,
  Download,
  Users2,
  Sparkles,
  Star,
} from "lucide-react";
import { DataTable } from "@/components/shared/DataTable";
import { ExportButton } from "@/components/ExportButton";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import type { ColumnDef } from "@tanstack/react-table";

interface Candidate {
  id: string;
  name: string;
  role: string;
  stage: "推荐" | "联系" | "面试" | "Offer" | "已入职" | "已归档";
  match: number;
  applied: string;
  source: string;
  starred?: boolean;
}

const SAMPLE_CANDIDATES: Candidate[] = [
  { id: "c-101", name: "陈诺", role: "高级前端工程师", stage: "面试", match: 88, applied: "今天", source: "LinkedIn", starred: true },
  { id: "c-102", name: "周野", role: "算法工程师", stage: "Offer", match: 92, applied: "昨天", source: "内推", starred: true },
  { id: "c-103", name: "林夏", role: "产品经理", stage: "联系", match: 76, applied: "2 天前", source: "Boss" },
  { id: "c-104", name: "Maya Liu", role: "运营总监", stage: "面试", match: 81, applied: "3 天前", source: "猎聘" },
  { id: "c-105", name: "Bob Zhao", role: "财务 BP", stage: "推荐", match: 64, applied: "5 天前", source: "官网" },
  { id: "c-106", name: "Vivian Tang", role: "海外 BD", stage: "面试", match: 86, applied: "1 周前", source: "邮件", starred: true },
  { id: "c-107", name: "韩冬", role: "前端工程师", stage: "面试", match: 79, applied: "1 周前", source: "LinkedIn" },
  { id: "c-108", name: "Anna Park", role: "数据分析师", stage: "联系", match: 71, applied: "2 周前", source: "猎头" },
  { id: "c-109", name: "Lin", role: "工程经理", stage: "推荐", match: 73, applied: "3 周前", source: "内推" },
  { id: "c-110", name: "Sarah", role: "UI 设计师", stage: "Offer", match: 84, applied: "3 周前", source: "官网" },
];

const STAGE_TONE: Record<Candidate["stage"], string> = {
  "推荐": "bg-slate-100 text-slate-700",
  "联系": "bg-amber-100 text-amber-800",
  "面试": "bg-blue-100 text-blue-800",
  "Offer": "bg-emerald-100 text-emerald-800",
  "已入职": "bg-emerald-500 text-white",
  "已归档": "bg-rose-100 text-rose-800",
};

export default function CandidatesPage() {
  const [stage, setStage] = React.useState<Candidate["stage"] | "all">("all");
  const [starredOnly, setStarredOnly] = React.useState(false);

  const rows = React.useMemo(
    () =>
      SAMPLE_CANDIDATES.filter((c) => {
        if (stage !== "all" && c.stage !== stage) return false;
        if (starredOnly && !c.starred) return false;
        return true;
      }),
    [stage, starredOnly],
  );

  const columns: ColumnDef<Candidate>[] = React.useMemo(
    () => [
      {
        id: "name",
        header: "候选人",
        cell: ({ row }) => (
          <Link
            href={`/employer/candidates/${row.original.id}`}
            className="flex items-center gap-2 font-medium hover:underline"
          >
            <Avatar className="h-7 w-7">
              <AvatarFallback className="bg-primary/10 text-xs text-primary">
                {row.original.name.charAt(0)}
              </AvatarFallback>
            </Avatar>
            {row.original.name}
            {row.original.starred && (
              <Star className="h-3 w-3 fill-amber-400 text-amber-400" />
            )}
          </Link>
        ),
      },
      {
        id: "role",
        header: "应聘岗位",
        cell: ({ row }) => (
          <span className="text-sm">{row.original.role}</span>
        ),
      },
      {
        id: "match",
        header: "匹配度",
        cell: ({ row }) => {
          const m = row.original.match;
          const tone = m >= 85 ? "text-emerald-700" : m >= 70 ? "text-amber-700" : "text-rose-700";
          return (
            <span className={`inline-flex items-center gap-1 font-mono text-sm font-medium ${tone}`}>
              <Sparkles className="h-3 w-3" />
              {m}
            </span>
          );
        },
      },
      {
        id: "stage",
        header: "阶段",
        cell: ({ row }) => (
          <span
            className={`inline-flex rounded-full px-2 py-0.5 text-xs ${STAGE_TONE[row.original.stage]}`}
          >
            {row.original.stage}
          </span>
        ),
      },
      {
        id: "source",
        header: "渠道",
        cell: ({ row }) => <Badge variant="outline">{row.original.source}</Badge>,
      },
      {
        id: "applied",
        header: "申请时间",
        cell: ({ row }) => <span className="text-xs text-muted-foreground">{row.original.applied}</span>,
      },
    ],
    [],
  );

  return (
    <div className="space-y-6 p-4 md:p-8">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">候选人 · Candidates</h1>
          <p className="text-sm text-muted-foreground">
            v8.1 + shadcn-admin DataTable · 排序/筛选/批量操作
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ExportButton kind="candidate" />
          <Button asChild>
            <Link href="/mothership/candidates/new">
              <PlusCircle className="mr-1 h-4 w-4" />
              新增候选人
            </Link>
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label="总数" value={SAMPLE_CANDIDATES.length} icon={<Users2 className="h-4 w-4" />} />
        <Kpi label="面试中" value={SAMPLE_CANDIDATES.filter((c) => c.stage === "面试").length} icon={<Users2 className="h-4 w-4" />} tone="blue" />
        <Kpi label="Offer" value={SAMPLE_CANDIDATES.filter((c) => c.stage === "Offer").length} icon={<Users2 className="h-4 w-4" />} tone="emerald" />
        <Kpi label="Starred" value={SAMPLE_CANDIDATES.filter((c) => c.starred).length} icon={<Star className="h-4 w-4" />} tone="amber" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">筛选</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <div className="w-full md:w-64">
            <Input placeholder="搜索姓名 / 岗位..." />
          </div>
          <Select
            value={stage}
            onValueChange={(v) => setStage(v as Candidate["stage"] | "all")}
          >
            <SelectTrigger className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部阶段</SelectItem>
              <SelectItem value="推荐">推荐</SelectItem>
              <SelectItem value="联系">联系</SelectItem>
              <SelectItem value="面试">面试</SelectItem>
              <SelectItem value="Offer">Offer</SelectItem>
              <SelectItem value="已入职">已入职</SelectItem>
              <SelectItem value="已归档">已归档</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant={starredOnly ? "default" : "outline"}
            size="sm"
            onClick={() => setStarredOnly((v) => !v)}
          >
            <Star className="mr-1 h-3 w-3" />
            只看 Star
          </Button>
          <span className="ml-auto text-sm text-muted-foreground">
            {rows.length} / {SAMPLE_CANDIDATES.length}
          </span>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-3">
          <DataTable<Candidate>
            data={rows}
            columns={columns}
            searchPlaceholder="搜索..."
            pageSize={8}
            bulkActions={(selected) => (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{selected.length} 已选</span>
                <Button variant="outline" size="sm">
                  批量归档
                </Button>
                <Button variant="outline" size="sm">
                  批量换岗
                </Button>
                <ExportButton kind="candidate" />
              </div>
            )}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function Kpi({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  tone?: "blue" | "emerald" | "amber";
}) {
  const t =
    tone === "blue"
      ? "bg-blue-500/10 text-blue-700"
      : tone === "emerald"
      ? "bg-emerald-500/10 text-emerald-700"
      : tone === "amber"
      ? "bg-amber-500/10 text-amber-700"
      : "bg-muted text-muted-foreground";
  return (
    <Card className="p-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        <span className={`rounded p-1 ${t}`}>{icon}</span>
      </div>
      <div className="mt-2 text-xl font-bold tabular-nums">{value}</div>
    </Card>
  );
}
