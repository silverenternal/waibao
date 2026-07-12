"use client";

/**
 * T1106 — Pilot admin dashboard.
 *
 * 展示:
 * - 所有 pilot programs 列表
 * - 当前选中 program 的: 邀请统计 / NPS / 反馈分类 / Top 痛点
 * - 邀请新用户的入口
 *
 * 数据源:
 * - GET /api/pilot/programs
 * - GET /api/pilot/programs/{id}/stats
 * - GET /api/pilot/feedback?program_id=...
 */

import * as React from "react";
import { Mail, Plus, RefreshCw, TrendingUp, Users } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";

interface Program {
  id: string;
  name: string;
  status: string;
  organisation_id: string;
  target_nps: number;
  max_users: number;
  started_at: string | null;
  ended_at: string | null;
  organisations?: { name?: string } | null;
}

interface Stats {
  program_id: string;
  invitations: {
    total: number;
    accepted: number;
    pending: number;
    expired: number;
  };
  nps: {
    nps: number | null;
    promoters: number;
    passives: number;
    detractors: number;
    responses: number;
  };
  feedback_by_category: Record<string, number>;
  feedback_by_feature: Record<string, number>;
  top_pain_points: Array<{ category: string; count: number }>;
  feedback_count: number;
}

interface FeedbackRow {
  id: string;
  category: string;
  score: number | null;
  comment: string | null;
  feature_used: string | null;
  created_at: string;
  users?: { email?: string } | null;
}

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("sb_token") || "";
}

function npsColor(nps: number | null): string {
  if (nps == null) return "bg-slate-100 text-slate-700";
  if (nps >= 50) return "bg-emerald-100 text-emerald-700";
  if (nps >= 0) return "bg-amber-100 text-amber-700";
  return "bg-rose-100 text-rose-700";
}

export default function PilotDashboardPage() {
  const [programs, setPrograms] = React.useState<Program[] | null>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [stats, setStats] = React.useState<Stats | null>(null);
  const [feedback, setFeedback] = React.useState<FeedbackRow[]>([]);
  const [loading, setLoading] = React.useState(false);

  // invite form
  const [inviteEmail, setInviteEmail] = React.useState("");
  const [inviteRole, setInviteRole] = React.useState("jobseeker");
  const [inviting, setInviting] = React.useState(false);
  const [inviteResult, setInviteResult] = React.useState<string | null>(null);

  const loadPrograms = React.useCallback(async () => {
    try {
      const res = await fetch("/api/pilot/programs", {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) {
        const json = await res.json();
        setPrograms(json.data || []);
        if (!selectedId && json.data?.[0]?.id) setSelectedId(json.data[0].id);
      }
    } catch {
      /* swallow */
    }
  }, [selectedId]);

  const loadStats = React.useCallback(async (id: string) => {
    setLoading(true);
    try {
      const [s, f] = await Promise.all([
        fetch(`/api/pilot/programs/${id}/stats`, {
          headers: { Authorization: `Bearer ${getToken()}` },
        }),
        fetch(`/api/feedback?program_id=${id}&limit=20`, {
          headers: { Authorization: `Bearer ${getToken()}` },
        }),
      ]);
      if (s.ok) setStats(await s.json());
      if (f.ok) {
        const jf = await f.json();
        setFeedback(jf.data || []);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadPrograms();
  }, [loadPrograms]);

  React.useEffect(() => {
    if (selectedId) void loadStats(selectedId);
  }, [selectedId, loadStats]);

  const selected = programs?.find((p) => p.id === selectedId);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail || !selectedId) return;
    setInviting(true);
    setInviteResult(null);
    try {
      const res = await fetch("/api/pilot/invite", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          program_id: selectedId,
          email: inviteEmail,
          role: inviteRole,
        }),
      });
      if (res.ok) {
        const j = await res.json();
        setInviteResult(`已发送邀请给 ${j.email},URL: ${j.invite_url}`);
        setInviteEmail("");
        void loadStats(selectedId);
      } else {
        const err = await res.json().catch(() => ({}));
        setInviteResult(`失败: ${err.detail || res.status}`);
      }
    } finally {
      setInviting(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:py-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Pilot 试用仪表盘</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            监控所有试用合作方:邀请数 / NPS / 反馈分类 / Top 痛点
          </p>
        </div>
        <Button size="sm" onClick={() => { void loadPrograms(); if (selectedId) void loadStats(selectedId); }}>
          <RefreshCw className="mr-1 size-3.5" />
          刷新
        </Button>
      </header>

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        {/* Programs 列表 */}
        <aside className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium">试用合作</h2>
            <Badge variant="secondary">{programs?.length ?? 0}</Badge>
          </div>
          {programs === null && (
            <div className="space-y-2">
              {[1, 2].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
            </div>
          )}
          {programs && programs.length === 0 && (
            <p className="rounded-md bg-muted/40 p-4 text-center text-xs text-muted-foreground">
              暂无 pilot program
            </p>
          )}
          <ul className="space-y-1.5">
            {programs?.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(p.id)}
                  className={cn(
                    "w-full rounded-md border p-3 text-left transition-colors",
                    selectedId === p.id
                      ? "border-primary bg-primary/5"
                      : "hover:bg-muted/40",
                  )}
                >
                  <p className="text-sm font-medium">{p.name}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {p.organisations?.name || p.organisation_id}
                  </p>
                  <div className="mt-1 flex items-center gap-1.5">
                    <StatusBadge status={p.status} />
                    <Badge variant="outline" className="text-[10px]">
                      目标 NPS {p.target_nps}
                    </Badge>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        {/* 详情 */}
        <main className="space-y-6">
          {!selected && programs && (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                请选择左侧的 pilot program 查看详情
              </CardContent>
            </Card>
          )}

          {selected && (
            <>
              <div className="grid gap-4 sm:grid-cols-4">
                <StatCard
                  label="NPS"
                  value={stats?.nps.nps ?? null}
                  unit=""
                  color={npsColor(stats?.nps.nps ?? null)}
                  sub={`目标 ${selected.target_nps}`}
                />
                <StatCard
                  label="已邀请"
                  value={stats?.invitations.total ?? 0}
                  unit=" 人"
                  icon={<Mail className="size-4" />}
                  sub={`接受 ${stats?.invitations.accepted ?? 0}`}
                />
                <StatCard
                  label="反馈条数"
                  value={stats?.feedback_count ?? 0}
                  unit=""
                  icon={<TrendingUp className="size-4" />}
                  sub={`NPS ${stats?.nps.responses ?? 0} 答`}
                />
                <StatCard
                  label="接受率"
                  value={
                    stats && stats.invitations.total > 0
                      ? Math.round(
                          (stats.invitations.accepted / stats.invitations.total) * 100,
                        )
                      : 0
                  }
                  unit="%"
                  icon={<Users className="size-4" />}
                  sub={`上限 ${selected.max_users}`}
                />
              </div>

              <div className="grid gap-6 lg:grid-cols-2">
                {/* NPS breakdown */}
                <Card>
                  <CardHeader>
                    <CardTitle>NPS 分布</CardTitle>
                    <CardDescription>
                      Promoter 9-10 / Passive 7-8 / Detractor 0-6
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {loading && !stats ? (
                      <Skeleton className="h-24 w-full" />
                    ) : stats ? (
                      <NpsBar stats={stats.nps} />
                    ) : null}
                  </CardContent>
                </Card>

                {/* 反馈分类 */}
                <Card>
                  <CardHeader>
                    <CardTitle>反馈分类</CardTitle>
                    <CardDescription>按 category 计数</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {loading && !stats ? (
                      <Skeleton className="h-24 w-full" />
                    ) : stats ? (
                      <CategoryBars counts={stats.feedback_by_category} />
                    ) : null}
                  </CardContent>
                </Card>
              </div>

              {/* 邀请新用户 */}
              <Card>
                <CardHeader>
                  <CardTitle>邀请新用户</CardTitle>
                  <CardDescription>
                    通过邮件发送邀请链接 (链接 14 天内有效)
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <form onSubmit={handleInvite} className="grid gap-3 sm:grid-cols-[1fr_180px_auto]">
                    <div className="space-y-1">
                      <Label htmlFor="email">邮箱</Label>
                      <Input
                        id="email"
                        type="email"
                        value={inviteEmail}
                        onChange={(e) => setInviteEmail(e.target.value)}
                        placeholder="alice@example.com"
                        required
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="role">角色</Label>
                      <select
                        id="role"
                        value={inviteRole}
                        onChange={(e) => setInviteRole(e.target.value)}
                        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                      >
                        <option value="jobseeker">求职者</option>
                        <option value="employer">雇主</option>
                        <option value="observer">观察员</option>
                      </select>
                    </div>
                    <div className="flex items-end">
                      <Button type="submit" disabled={inviting} className="w-full">
                        <Plus className="mr-1 size-4" />
                        {inviting ? "发送中..." : "发送邀请"}
                      </Button>
                    </div>
                  </form>
                  {inviteResult && (
                    <p className="mt-3 break-all rounded-md bg-muted/40 p-2 text-xs text-muted-foreground">
                      {inviteResult}
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* 最近反馈 */}
              <Card>
                <CardHeader>
                  <CardTitle>最近反馈</CardTitle>
                  <CardDescription>最新 20 条</CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>类别</TableHead>
                        <TableHead>评分</TableHead>
                        <TableHead>用户</TableHead>
                        <TableHead>内容</TableHead>
                        <TableHead>时间</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {feedback.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-6">
                            暂无反馈
                          </TableCell>
                        </TableRow>
                      )}
                      {feedback.map((f) => (
                        <TableRow key={f.id}>
                          <TableCell>
                            <Badge variant="outline">{f.category}</Badge>
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {f.score ?? "-"}
                          </TableCell>
                          <TableCell className="text-xs">
                            {f.users?.email || "-"}
                          </TableCell>
                          <TableCell className="max-w-md truncate text-xs">
                            {f.comment || (
                              <span className="text-muted-foreground">
                                {f.feature_used || "-"}
                              </span>
                            )}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {new Date(f.created_at).toLocaleDateString("zh-CN")}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  unit,
  sub,
  icon,
  color,
}: {
  label: string;
  value: number | null;
  unit: string;
  sub?: string;
  icon?: React.ReactNode;
  color?: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{label}</span>
          {icon}
        </div>
        <p
          className={cn(
            "mt-2 inline-block rounded px-1.5 text-2xl font-bold",
            color ?? "text-foreground",
          )}
        >
          {value == null ? "-" : `${value}${unit}`}
        </p>
        {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function NpsBar({ stats }: { stats: Stats["nps"] }) {
  const total = stats.promoters + stats.passives + stats.detractors;
  if (total === 0) {
    return <p className="text-sm text-muted-foreground">暂无 NPS 反馈</p>;
  }
  const pPct = (stats.promoters / total) * 100;
  const paPct = (stats.passives / total) * 100;
  const dPct = (stats.detractors / total) * 100;
  return (
    <div className="space-y-2">
      <div className="flex h-3 overflow-hidden rounded-full">
        <div className="bg-emerald-500" style={{ width: `${pPct}%` }} />
        <div className="bg-amber-400" style={{ width: `${paPct}%` }} />
        <div className="bg-rose-500" style={{ width: `${dPct}%` }} />
      </div>
      <div className="flex justify-between text-xs">
        <span className="text-emerald-700">推广者 {stats.promoters}</span>
        <span className="text-amber-700">中立者 {stats.passives}</span>
        <span className="text-rose-700">贬损者 {stats.detractors}</span>
      </div>
    </div>
  );
}

function CategoryBars({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无反馈</p>;
  }
  const max = Math.max(...entries.map((e) => e[1]), 1);
  return (
    <div className="space-y-2">
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-center gap-2 text-xs">
          <span className="w-28 shrink-0 text-muted-foreground">{k}</span>
          <div className="h-2 flex-1 rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${(v / max) * 100}%` }}
            />
          </div>
          <span className="w-8 text-right font-mono">{v}</span>
        </div>
      ))}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    recruiting: { label: "招募中", cls: "bg-slate-100 text-slate-700" },
    active: { label: "试用中", cls: "bg-emerald-100 text-emerald-700" },
    completed: { label: "已完成", cls: "bg-blue-100 text-blue-700" },
    cancelled: { label: "已取消", cls: "bg-rose-100 text-rose-700" },
  };
  const conf = map[status] ?? map.recruiting;
  return <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", conf.cls)}>{conf.label}</span>;
}