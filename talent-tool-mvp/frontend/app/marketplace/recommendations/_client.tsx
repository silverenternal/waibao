"use client";

/**
 * T6104 — Recommendations center (interactive).
 *
 * Lists the recommendations pushed to the employer's org. Each card shows
 * the 4 match sections (score / reasons / gaps / risks). Clicking 查看
 * expands the full resume + contact info inline. Accept / Reject advance
 * the lifecycle. Download (简历) is admin-only — the button is hidden for
 * non-admins (资料查看下载导出权限仅平台管理员).
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { RecommendationCard } from "@/components/marketplace/RecommendationCard";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  downloadRecommendationResume,
  getRecommendation,
  listRecommendations,
  updateRecommendationStatus,
  type RecommendationDetail,
  type RecommendationStatus,
  type RecommendationSummary,
} from "@/lib/api-recommendations";

type StatusFilter = "all" | RecommendationStatus;

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "pending", label: "待处理" },
  { value: "viewed", label: "已查看" },
  { value: "accepted", label: "已接受" },
  { value: "rejected", label: "已拒绝" },
];

export function RecommendationsClient() {
  const [status, setStatus] = useState<StatusFilter>("all");
  const [items, setItems] = useState<RecommendationSummary[]>([]);
  const [details, setDetails] = useState<Record<string, RecommendationDetail>>(
    {},
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);

  // Detect admin role from the supabase session user_metadata.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const { createClient } = await import("@/lib/supabase");
        const supabase = createClient();
        const {
          data: { user },
        } = await supabase.auth.getUser();
        const role = (user?.user_metadata as { role?: string } | null)?.role;
        if (active) setIsAdmin(role === "admin");
      } catch {
        if (active) setIsAdmin(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listRecommendations(
        status === "all" ? {} : { status },
      );
      setItems(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const handleView = useCallback(async (id: string) => {
    setBusyId(id);
    try {
      const detail = await getRecommendation(id);
      setDetails((prev) => ({ ...prev, [id]: detail }));
      // viewing may have advanced pending → viewed; refresh list status
      setItems((prev) =>
        prev.map((it) =>
          it.id === id ? { ...it, status: detail.status } : it,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载详情失败");
    } finally {
      setBusyId(null);
    }
  }, []);

  const handleStatus = useCallback(
    async (id: string, next: "accepted" | "rejected") => {
      setBusyId(id);
      try {
        const updated = await updateRecommendationStatus(id, next);
        setItems((prev) => prev.map((it) => (it.id === id ? updated : it)));
      } catch (e) {
        setError(e instanceof Error ? e.message : "操作失败");
      } finally {
        setBusyId(null);
      }
    },
    [],
  );

  const handleDownload = useCallback(async (id: string) => {
    setBusyId(id);
    try {
      const text = await downloadRecommendationResume(id);
      const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `resume_${id}.txt`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "下载失败");
    } finally {
      setBusyId(null);
    }
  }, []);

  const counts = items.reduce(
    (acc, it) => {
      acc[it.status] = (acc[it.status] ?? 0) + 1;
      return acc;
    },
    {} as Record<RecommendationStatus, number>,
  );

  return (
    <main className="container mx-auto max-w-5xl px-4 py-10">
      <header className="mb-6 space-y-1">
        <Link
          href="/marketplace"
          className="text-sm text-slate-500 hover:text-slate-700"
        >
          ← 返回市场首页
        </Link>
        <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">
          推荐中心
        </h1>
        <p className="text-sm text-slate-500">
          平台匹配成功后推送的候选人推荐。共 {items.length} 条
          {isAdmin && " · 管理员：可下载导出简历"}
        </p>
      </header>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <span className="text-sm font-medium text-slate-600">状态</span>
        <Select
          value={status}
          onValueChange={(v) => setStatus((v ?? "all") as StatusFilter)}
        >
          <SelectTrigger className="w-40" aria-label="状态筛选">
            <SelectValue placeholder="全部" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_FILTERS.map((f) => (
              <SelectItem key={f.value} value={f.value}>
                {f.label}
                {f.value !== "all" && counts[f.value]
                  ? ` (${counts[f.value]})`
                  : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          刷新
        </Button>
        {error && (
          <span className="text-xs text-rose-600" role="alert">
            {error}
          </span>
        )}
      </div>

      {/* Results */}
      {loading && items.length === 0 ? (
        <SkeletonGrid />
      ) : items.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2">
          {items.map((it) => (
            <RecommendationCard
              key={it.id}
              recommendation={details[it.id] ?? it}
              isAdmin={isAdmin}
              busy={busyId === it.id}
              onView={details[it.id] ? undefined : handleView}
              onAccept={(id) => handleStatus(id, "accepted")}
              onReject={(id) => handleStatus(id, "rejected")}
              onDownload={handleDownload}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-10 text-center text-sm text-slate-500">
          暂无推荐。匹配成功后，平台会把候选人资料推送到这里。
        </div>
      )}
    </main>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="h-64 animate-pulse rounded-xl border border-slate-200 bg-slate-100"
        />
      ))}
    </div>
  );
}
