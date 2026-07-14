"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Roles list — v8.1 T3705 + OpenResume-style polish.
 *
 * Layout: dual-tab (Open · Draft) above a DataTable (shadcn-admin style).
 * Each row links to /roles/[id] and surfaces JD score, hire count, channel
 * performance.
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
import { PlusCircle, Search, Eye } from "lucide-react";
import { DataTable } from "@/components/shared/DataTable";
import type { ColumnDef } from "@tanstack/react-table";
import { JDScorer } from "@/components/jd/JDScorer";

interface Role {
  id: string;
  title: string;
  department: string;
  location: string;
  openings: number;
  status: "open" | "draft" | "paused" | "closed";
  hiringManager: string;
  recruiter: string;
  postedAt: string;
  totalCandidates: number;
  pipeline: { stage: string; count: number }[];
  jdScore: number;
}

const SAMPLE_ROLES: Role[] = [
  {
    id: "r-101",
    title: "高级前端工程师",
    department: "技术",
    location: "北京",
    openings: 2,
    status: "open",
    hiringManager: "Sarah Lee",
    recruiter: "Alex K.",
    postedAt: "2026-06-12",
    totalCandidates: 38,
    pipeline: [
      { stage: "推荐", count: 38 },
      { stage: "联系", count: 16 },
      { stage: "面试", count: 5 },
      { stage: "Offer", count: 1 },
    ],
    jdScore: 86,
  },
  {
    id: "r-102",
    title: "算法工程师 (LLM)",
    department: "技术",
    location: "上海",
    openings: 1,
    status: "open",
    hiringManager: "Jason Wu",
    recruiter: "Alex K.",
    postedAt: "2026-06-25",
    totalCandidates: 21,
    pipeline: [
      { stage: "推荐", count: 21 },
      { stage: "联系", count: 8 },
      { stage: "面试", count: 2 },
      { stage: "Offer", count: 0 },
    ],
    jdScore: 78,
  },
  {
    id: "r-103",
    title: "海外 BD",
    department: "市场",
    location: "Remote",
    openings: 5,
    status: "open",
    hiringManager: "Maya Liu",
    recruiter: "Anna",
    postedAt: "2026-07-01",
    totalCandidates: 14,
    pipeline: [
      { stage: "推荐", count: 14 },
      { stage: "联系", count: 4 },
      { stage: "面试", count: 1 },
      { stage: "Offer", count: 0 },
    ],
    jdScore: 92,
  },
  {
    id: "r-104",
    title: "产品经理",
    department: "产品",
    location: "杭州",
    openings: 1,
    status: "draft",
    hiringManager: "Lin",
    recruiter: "—",
    postedAt: "—",
    totalCandidates: 0,
    pipeline: [],
    jdScore: 64,
  },
  {
    id: "r-105",
    title: "财务 BP",
    department: "财务",
    location: "北京",
    openings: 1,
    status: "paused",
    hiringManager: "Bob",
    recruiter: "Vivian",
    postedAt: "2026-05-08",
    totalCandidates: 12,
    pipeline: [],
    jdScore: 71,
  },
];

const STATUS_LABEL = {
  open: { label: "招聘中", cls: "bg-emerald-500/10 text-emerald-700" },
  draft: { label: "草稿", cls: "bg-amber-500/10 text-amber-700" },
  paused: { label: "暂停", cls: "bg-slate-500/10 text-slate-700" },
  closed: { label: "已关闭", cls: "bg-rose-500/10 text-rose-700" },
} as const;

export default function RolesPage() {
  const [status, setStatus] = React.useState<"open" | "draft" | "paused" | "closed" | "all">(
    "all",
  );
  const [q, setQ] = React.useState("");
  const [departments, setDepartments] = React.useState<string[]>([]);

  const rows = React.useMemo(() => {
    return SAMPLE_ROLES.filter((r) => {
      if (status !== "all" && r.status !== status) return false;
      if (departments.length && !departments.includes(r.department)) return false;
      if (q && !r.title.toLowerCase().includes(q.toLowerCase())) return false;
      return true;
    });
  }, [status, departments, q]);

  const columns: ColumnDef<Role>[] = React.useMemo(
    () => [
      {
        id: "title",
        header: "岗位",
        cell: ({ row }) => (
          <Link
            href={`/employer/roles/${row.original.id}`}
            className="font-medium hover:underline"
          >
            {row.original.title}
          </Link>
        ),
      },
      {
        id: "department",
        header: "部门",
        cell: ({ row }) => <Badge variant="outline">{row.original.department}</Badge>,
      },
      {
        id: "openings",
        header: "HC",
        cell: ({ row }) => (
          <span className="font-mono text-sm">{row.original.openings}</span>
        ),
      },
      {
        id: "status",
        header: "状态",
        cell: ({ row }) => {
          const s = STATUS_LABEL[row.original.status];
          return (
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs ${s.cls}`}>
              {s.label}
            </span>
          );
        },
      },
      {
        id: "score",
        header: "JD 评分",
        cell: ({ row }) => (
          <ScorePill score={row.original.jdScore} />
        ),
      },
      {
        id: "pipeline",
        header: "漏斗",
        cell: ({ row }) => {
          const p = row.original.pipeline;
          const total = Math.max(1, row.original.totalCandidates);
          return (
            <div className="flex h-3 w-32 overflow-hidden rounded-full bg-muted">
              {p.map((s, i) => (
                <span
                  key={i}
                  style={{ width: `${(s.count / total) * 100}%` }}
                  className={
                    i === 0
                      ? "bg-primary/40"
                      : i === 1
                      ? "bg-primary/60"
                      : i === 2
                      ? "bg-primary/80"
                      : "bg-primary"
                  }
                  aria-label={`${s.stage}: ${s.count}`}
                />
              ))}
            </div>
          );
        },
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <Button asChild variant="ghost" size="sm">
            <Link href={`/employer/roles/${row.original.id}`}>
              <Eye className="h-4 w-4" />
            </Link>
          </Button>
        ),
      },
    ],
    [],
  );

  const allDepts = Array.from(new Set(SAMPLE_ROLES.map((r) => r.department)));

  return (
    <ErrorBoundary>(<div className="space-y-6 p-4 md:p-8">
        <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
              岗位 · Roles
            </h1>
            <p className="text-sm text-muted-foreground">
              v8.1 T3705 — OpenResume 风格清单,JD 评分实时计算。
            </p>
          </div>
          <Button asChild>
            <Link href="/employer/roles/new">
              <PlusCircle className="mr-1 h-4 w-4" />
              新建岗位
            </Link>
          </Button>
        </header>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">筛选</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="按名称搜索"
                className="pl-9"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
            <Select
              value={status}
              onValueChange={(v) => setStatus(v as typeof status)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value="open">招聘中</SelectItem>
                <SelectItem value="draft">草稿</SelectItem>
                <SelectItem value="paused">暂停</SelectItem>
                <SelectItem value="closed">已关闭</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex flex-wrap gap-1">
              {allDepts.map((d) => {
                const sel = departments.includes(d);
                return (
                  <button
                    key={d}
                    onClick={() =>
                      setDepartments((prev) =>
                        sel ? prev.filter((x) => x !== d) : [...prev, d],
                      )
                    }
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      sel
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground hover:bg-muted/70"
                    }`}
                  >
                    {d}
                  </button>
                );
              })}
            </div>
            <div className="text-sm text-muted-foreground">
              {rows.length} / {SAMPLE_ROLES.length} 个岗位
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <DataTable<Role>
              data={rows}
              columns={columns}
              searchPlaceholder="搜索岗位..."
              pageSize={10}
            />
          </CardContent>
        </Card>
      </div>)</ErrorBoundary>
  );
}

function ScorePill({ score }: { score: number }) {
  const tone =
    score >= 85 ? "bg-emerald-500 text-white" : score >= 70 ? "bg-amber-500 text-white" : "bg-rose-500 text-white";
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium tabular-nums ${tone}`}>
      {score}
    </span>
  );
}
