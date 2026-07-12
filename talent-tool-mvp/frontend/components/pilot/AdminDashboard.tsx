"use client";

/**
 * T1702 — Pilot Admin Dashboard.
 *
 * - 顶部 KPI 卡 (来自 /api/pilot/programs?status=active 汇总)
 * - 程序列表 (表格, 点击进入详情)
 * - 邀请按钮 (调 /api/pilot/invite)
 * - 目标达成汇总
 */

import * as React from "react";
import {
  Plus,
  Download,
  Loader2,
  ExternalLink,
  CheckCircle2,
  XCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from "@/components/ui/dialog";

export interface PilotProgram {
  id: string;
  name: string;
  organisation_id: string;
  status: "recruiting" | "active" | "completed" | "cancelled";
  target_nps: number;
  max_users: number;
  started_at: string | null;
  ended_at: string | null;
  metadata: Record<string, any>;
  organisations?: { name: string } | Array<{ name: string }> | null;
}

export interface AdminDashboardProps {
  /** 受控 programs (跳过 fetch). */
  programs?: PilotProgram[];
  /** 受控选中 program id. */
  selectedProgramId?: string;
  /** 点击 program 回调. */
  onSelect?: (programId: string) => void;
  className?: string;
}

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("sb_token") || "";
}

function orgName(p: PilotProgram): string {
  if (!p.organisations) return "—";
  if (Array.isArray(p.organisations)) return p.organisations[0]?.name ?? "—";
  return p.organisations.name ?? "—";
}

const STATUS_BADGE: Record<PilotProgram["status"], string> = {
  recruiting: "bg-slate-100 text-slate-700",
  active: "bg-emerald-100 text-emerald-700",
  completed: "bg-blue-100 text-blue-700",
  cancelled: "bg-rose-100 text-rose-700",
};

export function AdminDashboard({
  programs: programsProp,
  selectedProgramId,
  onSelect,
  className,
}: AdminDashboardProps) {
  const [programs, setPrograms] = React.useState<PilotProgram[]>(programsProp ?? []);
  const [loading, setLoading] = React.useState(programsProp === undefined);
  const [error, setError] = React.useState<string | null>(null);
  const [generatingId, setGeneratingId] = React.useState<string | null>(null);

  const fetchPrograms = React.useCallback(async () => {
    try {
      const res = await fetch("/api/pilot/programs?limit=100", {
        headers: { Authorization: `Bearer ${getToken()}` },
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setPrograms(json.data || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (programsProp) return;
    fetchPrograms();
  }, [fetchPrograms, programsProp]);

  const downloadReport = async (programId: string) => {
    setGeneratingId(programId);
    try {
      const res = await fetch(`/api/pilot/programs/${programId}/report/download`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pilot_report_${programId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "download failed");
    } finally {
      setGeneratingId(null);
    }
  };

  const activeCount = programs.filter((p) => p.status === "active").length;
  const completedCount = programs.filter((p) => p.status === "completed").length;
  const recruitingCount = programs.filter((p) => p.status === "recruiting").length;

  return (
    <div className={cn("space-y-6", className)}>
      {/* KPI 总览 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="活跃项目" value={activeCount} hint={`招募中 ${recruitingCount}`} />
        <KpiCard label="已完成" value={completedCount} />
        <KpiCard label="全部项目" value={programs.length} />
        <KpiCard label="目标 NPS" value="≥ 40" hint="Pilot 全员目标" />
      </div>

      {/* 项目列表 */}
      <Card>
        <div className="flex items-center justify-between border-b p-4">
          <h2 className="text-sm font-semibold">Pilot 项目列表</h2>
          <CreateProgramDialog onCreated={fetchPrograms} />
        </div>

        {loading ? (
          <div className="flex items-center justify-center p-8 text-muted-foreground">
            <Loader2 className="mr-2 size-4 animate-spin" />
            加载中...
          </div>
        ) : error ? (
          <div className="p-4 text-sm text-rose-700">{error}</div>
        ) : programs.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            还没有 pilot 项目.点击右上角"创建项目"开始.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                  <th className="px-4 py-3">项目</th>
                  <th className="px-4 py-3">组织</th>
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3">目标 NPS</th>
                  <th className="px-4 py-3">开始</th>
                  <th className="px-4 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {programs.map((p) => (
                  <tr
                    key={p.id}
                    className={cn(
                      "border-b hover:bg-muted/30",
                      selectedProgramId === p.id && "bg-primary/5",
                    )}
                  >
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => onSelect?.(p.id)}
                        className="text-left font-medium hover:underline"
                      >
                        {p.name}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{orgName(p)}</td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-xs",
                          STATUS_BADGE[p.status] ?? "bg-slate-100",
                        )}
                      >
                        {p.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">{p.target_nps}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {p.started_at ? new Date(p.started_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => onSelect?.(p.id)}
                          aria-label="查看详情"
                        >
                          <ExternalLink className="size-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => downloadReport(p.id)}
                          disabled={generatingId === p.id}
                          aria-label="下载报告"
                        >
                          {generatingId === p.id ? (
                            <Loader2 className="size-4 animate-spin" />
                          ) : (
                            <Download className="size-4" />
                          )}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function KpiCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <Card className="p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </Card>
  );
}

function CreateProgramDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [orgId, setOrgId] = React.useState("");
  const [targetNps, setTargetNps] = React.useState(50);
  const [maxUsers, setMaxUsers] = React.useState(20);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submit = async () => {
    if (!name.trim() || !orgId.trim()) {
      setError("请填写项目名和组织 ID");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/pilot/programs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          organisation_id: orgId.trim(),
          name: name.trim(),
          target_nps: targetNps,
          max_users: maxUsers,
        }),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(text || `HTTP ${res.status}`);
      }
      setOpen(false);
      setName("");
      setOrgId("");
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger {...({ asChild: true } as any)}>
        <Button size="sm">
          <Plus className="mr-2 size-4" />
          创建项目
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新建 Pilot 项目</DialogTitle>
          <DialogDescription>招募试用客户并配置目标.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="name">项目名</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme Q3 Pilot"
              maxLength={120}
            />
          </div>
          <div>
            <Label htmlFor="org">组织 ID</Label>
            <Input
              id="org"
              value={orgId}
              onChange={(e) => setOrgId(e.target.value)}
              placeholder="uuid"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="nps">目标 NPS</Label>
              <Input
                id="nps"
                type="number"
                min={-100}
                max={100}
                value={targetNps}
                onChange={(e) => setTargetNps(Number(e.target.value))}
              />
            </div>
            <div>
              <Label htmlFor="users">最大用户</Label>
              <Input
                id="users"
                type="number"
                min={1}
                max={500}
                value={maxUsers}
                onChange={(e) => setMaxUsers(Number(e.target.value))}
              />
            </div>
          </div>
          {error && <p className="text-sm text-rose-600">{error}</p>}
        </div>
        <DialogFooter>
          <DialogClose {...({ asChild: true } as any)}>
            <Button variant="ghost" disabled={submitting}>
              取消
            </Button>
          </DialogClose>
          <Button onClick={submit} disabled={submitting}>
            {submitting ? "创建中..." : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default AdminDashboard;