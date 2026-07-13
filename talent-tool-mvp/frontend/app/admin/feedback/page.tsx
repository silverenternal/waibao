"use client";

/**
 * v8.0 T3902 — Admin Feedback Dashboard.
 *
 * - List user feedback (filtered by type / priority / status)
 * - Trend chart (daily counts + critical/high ratio)
 * - Click row to update status (open / triaged / in_progress / resolved / closed)
 *
 * Server contract: GET/POST /api/feedback/v2/{list,trend,{id}/status}.
 */

import * as React from "react";
import {
  AlertCircle,
  Bug,
  CheckCircle2,
  Clock,
  Filter,
  Inbox,
  Lightbulb,
  Loader2,
  MessageSquare,
  Search,
  Star,
  XCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

interface FeedbackRecord {
  id: string;
  type: string;
  category: string;
  priority: string;
  rating?: number | null;
  title?: string | null;
  comment: string;
  page?: string | null;
  feature?: string | null;
  user_id?: string | null;
  tenant_id?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  status: string;
}

interface ListResponse {
  data: FeedbackRecord[];
  total: number;
  by_type: Record<string, number>;
  by_priority: Record<string, number>;
  by_category: Record<string, number>;
}

interface TrendResponse {
  days: number;
  buckets: Array<{ date: string; total: number; critical: number; high: number }>;
  top_categories: Array<{ category: string; count: number }>;
}

const TYPE_ICON: Record<string, React.ReactNode> = {
  rating: <Star className="h-3.5 w-3.5" />,
  bug: <Bug className="h-3.5 w-3.5" />,
  feature: <Lightbulb className="h-3.5 w-3.5" />,
  experience: <MessageSquare className="h-3.5 w-3.5" />,
  performance: <AlertCircle className="h-3.5 w-3.5" />,
};

const PRIORITY_STYLES: Record<string, string> = {
  critical: "bg-rose-100 text-rose-800",
  high: "bg-amber-100 text-amber-800",
  medium: "bg-sky-100 text-sky-800",
  low: "bg-slate-100 text-slate-700",
};

const STATUS_STYLES: Record<string, string> = {
  open: "bg-amber-50 text-amber-700 border-amber-200",
  triaged: "bg-sky-50 text-sky-700 border-sky-200",
  in_progress: "bg-indigo-50 text-indigo-700 border-indigo-200",
  resolved: "bg-emerald-50 text-emerald-700 border-emerald-200",
  closed: "bg-slate-100 text-slate-600 border-slate-200",
};

export default function FeedbackAdminPage() {
  const [list, setList] = React.useState<ListResponse | null>(null);
  const [trend, setTrend] = React.useState<TrendResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [filterType, setFilterType] = React.useState<string>("");
  const [filterPriority, setFilterPriority] = React.useState<string>("");
  const [search, setSearch] = React.useState("");

  const fetchAll = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filterType) params.set("type", filterType);
      if (filterPriority) params.set("priority", filterPriority);
      const listRes = await fetch(`/api/feedback/v2/list?${params.toString()}`, {
        credentials: "include",
      });
      if (!listRes.ok) throw new Error(`HTTP ${listRes.status}`);
      const listData = await listRes.json();
      setList(listData);
      const trendRes = await fetch("/api/feedback/v2/trend?days=14", { credentials: "include" });
      if (trendRes.ok) {
        setTrend(await trendRes.json());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [filterType, filterPriority]);

  React.useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const updateStatus = async (id: string, status: string) => {
    try {
      const res = await fetch(`/api/feedback/v2/${id}/status?status=${status}`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : "更新失败");
    }
  };

  const filteredData = (list?.data ?? []).filter((f) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (
      (f.comment || "").toLowerCase().includes(s) ||
      (f.title || "").toLowerCase().includes(s) ||
      (f.feature || "").toLowerCase().includes(s) ||
      (f.user_id || "").toLowerCase().includes(s)
    );
  });

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900">
            <Inbox className="h-5 w-5 text-indigo-500" /> 用户反馈
          </h1>
          <p className="text-sm text-slate-600">统一入口收集, 自动归类, 趋势可视化</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <Input
              placeholder="搜索评论 / 功能 / 用户"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-8 w-56 pl-7 text-sm"
            />
          </div>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="h-8 rounded-md border border-slate-200 bg-white px-2 text-sm"
          >
            <option value="">全部类型</option>
            <option value="rating">评分</option>
            <option value="bug">Bug</option>
            <option value="feature">建议</option>
            <option value="experience">体验</option>
            <option value="performance">性能</option>
          </select>
          <select
            value={filterPriority}
            onChange={(e) => setFilterPriority(e.target.value)}
            className="h-8 rounded-md border border-slate-200 bg-white px-2 text-sm"
          >
            <option value="">全部优先级</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <Button size="sm" variant="outline" onClick={fetchAll} disabled={loading}>
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Filter className="h-3.5 w-3.5" />}
            刷新
          </Button>
        </div>
      </header>

      {error && (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          <XCircle className="mr-1 inline h-3.5 w-3.5" /> {error}
        </div>
      )}

      {/* Summary cards */}
      {list && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label="总数" value={list.total} />
          <Stat label="Bug" value={list.by_type.bug ?? 0} />
          <Stat label="建议" value={list.by_type.feature ?? 0} />
          <Stat label="Critical" value={list.by_priority.critical ?? 0} />
          <Stat label="High" value={list.by_priority.high ?? 0} />
        </div>
      )}

      {/* Trend */}
      {trend && trend.buckets.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">14 天趋势</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex h-24 items-end gap-1">
              {trend.buckets.map((b) => {
                const max = Math.max(...trend.buckets.map((x) => x.total), 1);
                const h = (b.total / max) * 100;
                return (
                  <div key={b.date} className="flex flex-1 flex-col items-center gap-1">
                    <div
                      className="w-full rounded-t bg-sky-400"
                      style={{ height: `${h}%`, minHeight: "2px" }}
                      title={`${b.date}: ${b.total}`}
                    />
                    <span className="text-[10px] text-slate-500">
                      {b.date.slice(5)}
                    </span>
                  </div>
                );
              })}
            </div>
            {trend.top_categories.length > 0 && (
              <div className="mt-3 text-xs text-slate-500">
                TOP 类别:{" "}
                {trend.top_categories
                  .map((c) => `${c.category} (${c.count})`)
                  .join(" · ")}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* List */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">反馈列表 ({filteredData.length})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {loading ? (
            <p className="text-sm text-slate-500">加载中...</p>
          ) : filteredData.length === 0 ? (
            <p className="text-sm text-slate-500">无反馈</p>
          ) : (
            filteredData.map((f) => (
              <FeedbackRow key={f.id} item={f} onUpdate={updateStatus} />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-xl font-semibold text-slate-900">{value}</div>
    </div>
  );
}

function FeedbackRow({
  item,
  onUpdate,
}: {
  item: FeedbackRecord;
  onUpdate: (id: string, status: string) => void;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="outline" className="flex items-center gap-1">
          {TYPE_ICON[item.type] ?? <MessageSquare className="h-3.5 w-3.5" />}
          {item.type}
        </Badge>
        <Badge className={PRIORITY_STYLES[item.priority] ?? "bg-slate-100 text-slate-700"}>
          {item.priority}
        </Badge>
        <span className="text-slate-500">{item.category}</span>
        {item.rating !== null && item.rating !== undefined && (
          <span className="flex items-center gap-0.5 text-amber-500">
            <Star className="h-3 w-3 fill-current" /> {item.rating}/5
          </span>
        )}
        <span className="ml-auto text-slate-500">{item.created_at}</span>
      </div>
      {item.title && <div className="mt-1 text-sm font-medium text-slate-900">{item.title}</div>}
      <p className="mt-1 text-sm text-slate-700">{item.comment}</p>
      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        {item.page && <span>页面: {item.page}</span>}
        {item.feature && <span>· 功能: {item.feature}</span>}
        {item.user_id && <span>· 用户: {item.user_id.slice(0, 8)}</span>}
      </div>
      <div className="mt-2 flex items-center gap-1">
        <Badge
          variant="outline"
          className={STATUS_STYLES[item.status] ?? "bg-slate-100 text-slate-600"}
        >
          {item.status}
        </Badge>
        {item.status !== "resolved" && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onUpdate(item.id, "resolved")}
            className="h-6 text-xs"
          >
            <CheckCircle2 className="h-3 w-3" /> 标为已解决
          </Button>
        )}
        {item.status !== "triaged" && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onUpdate(item.id, "triaged")}
            className="h-6 text-xs"
          >
            <Clock className="h-3 w-3" /> 待分诊
          </Button>
        )}
        {item.status !== "closed" && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onUpdate(item.id, "closed")}
            className="h-6 text-xs"
          >
            关闭
          </Button>
        )}
      </div>
    </div>
  );
}
