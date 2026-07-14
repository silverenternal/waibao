"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * T1702 — /admin/pilot/[id] 项目详情.
 *
 * - UsageStats (KPI + NPS 分布 + Top 痛点)
 * - 邀请用户表单 (调 /api/pilot/invite)
 * - 启动 / 结束 按钮
 * - 月度报告生成 + 下载
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Loader2,
  Mail,
  Play,
  Square,
  Download,
  RefreshCw,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { UsageStats } from "@/components/pilot/UsageStats";

interface PilotProgram {
  id: string;
  name: string;
  status: "recruiting" | "active" | "completed" | "cancelled";
  started_at: string | null;
  ended_at: string | null;
  target_nps: number;
  max_users: number;
  organisations?: { name: string } | Array<{ name: string }> | null;
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

export default function AdminPilotDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const programId = params?.id;

  const [program, setProgram] = React.useState<PilotProgram | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [actionLoading, setActionLoading] = React.useState(false);

  // 邀请表单
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState("jobseeker");
  const [inviteMsg, setInviteMsg] = React.useState<string | null>(null);

  const headers = React.useMemo(
    () => ({
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken()}`,
    }),
    [],
  );

  const fetchProgram = React.useCallback(async () => {
    if (!programId) return;
    try {
      const res = await fetch(`/api/pilot/programs/${programId}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setProgram(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "fetch failed");
    } finally {
      setLoading(false);
    }
  }, [programId]);

  React.useEffect(() => {
    fetchProgram();
  }, [fetchProgram]);

  const action = async (path: string, method: "POST" | "PATCH" = "POST", body?: unknown) => {
    setActionLoading(true);
    try {
      const res = await fetch(`/api/pilot/programs/${programId}${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(text || `HTTP ${res.status}`);
      }
      await fetchProgram();
    } catch (e) {
      setError(e instanceof Error ? e.message : `${method} ${path} failed`);
    } finally {
      setActionLoading(false);
    }
  };

  const start = () => action("/start");
  const end = () => action("/end", "POST", { final_notes: "ended from admin UI" });

  const invite = async () => {
    if (!email.trim()) return;
    setActionLoading(true);
    setInviteMsg(null);
    try {
      const res = await fetch("/api/pilot/invite", {
        method: "POST",
        headers,
        body: JSON.stringify({
          program_id: programId,
          email: email.trim().toLowerCase(),
          role,
          send_email: true,
        }),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(text || `HTTP ${res.status}`);
      }
      setInviteMsg("邀请已发送");
      setEmail("");
    } catch (e) {
      setInviteMsg(`失败: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setActionLoading(false);
    }
  };

  const downloadReport = async () => {
    setActionLoading(true);
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
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <main className="flex items-center justify-center p-12 text-muted-foreground">
        <Loader2 className="mr-2 size-4 animate-spin" />
        加载中...
      </main>
    );
  }

  if (error) {
    return (
      <main className="mx-auto max-w-3xl space-y-4 p-8">
        <p className="text-sm text-rose-700">{error}</p>
        <Button variant="ghost" onClick={() => router.push("/admin/pilot")}>
          <ArrowLeft className="mr-2 size-4" />
          返回列表
        </Button>
      </main>
    );
  }

  if (!program) return null;

  return (
    <ErrorBoundary>(<main className="mx-auto max-w-5xl space-y-6 px-4 py-8">
        <div className="flex items-center justify-between">
          <Button variant="ghost" onClick={() => router.push("/admin/pilot")}>
            <ArrowLeft className="mr-2 size-4" />
            返回
          </Button>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={fetchProgram}
              aria-label="刷新"
            >
              <RefreshCw className="size-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={downloadReport}
              disabled={actionLoading}
            >
              <Download className="mr-2 size-4" />
              下载报告
            </Button>
            {program.status === "recruiting" && (
              <Button size="sm" onClick={start} disabled={actionLoading}>
                <Play className="mr-2 size-4" />
                启动试用
              </Button>
            )}
            {program.status === "active" && (
              <Button
                size="sm"
                variant="destructive"
                onClick={end}
                disabled={actionLoading}
              >
                <Square className="mr-2 size-4" />
                结束试用
              </Button>
            )}
          </div>
        </div>
        <header>
          <h1 className="text-2xl font-semibold tracking-tight">{program.name}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {orgName(program)} · 状态 {program.status} · 目标 NPS ≥ {program.target_nps} · 上限 {program.max_users} 用户
          </p>
        </header>
        {/* KPI / Stats */}
        <UsageStats programId={programId as string} refreshMs={0} />
        {/* 邀请 */}
        <Card className="p-5">
          <h2 className="text-sm font-semibold">邀请新用户</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            邀请后会发送邮件链接,14 天内有效.
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_140px_auto]">
            <div>
              <Label htmlFor="email" className="sr-only">
                邮箱
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="alice@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="role" className="sr-only">
                角色
              </Label>
              <select
                id="role"
                className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                <option value="jobseeker">求职者</option>
                <option value="employer">雇主</option>
                <option value="observer">观察者</option>
              </select>
            </div>
            <Button onClick={invite} disabled={actionLoading || !email.trim()}>
              <Mail className="mr-2 size-4" />
              发送邀请
            </Button>
          </div>
          {inviteMsg && (
            <p
              className={`mt-2 text-xs ${
                inviteMsg.startsWith("失败") ? "text-rose-600" : "text-emerald-700"
              }`}
              role="status"
            >
              {inviteMsg}
            </p>
          )}
        </Card>
      </main>)</ErrorBoundary>
  );
}