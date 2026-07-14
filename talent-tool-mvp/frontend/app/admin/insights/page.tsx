"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v8.0 T3901 — Admin Insights dashboard.
 *
 * Auto-displays:
 *   - Latest weekly report (summary, top features, 16 需求 usage)
 *   - Active anomalies (with severity badges)
 *   - User behavior insights (popular / low_usage / abandoned)
 *
 * Server contracts:
 *   - GET  /api/insights/weekly/latest   — combined weekly + anomalies + behavior
 *   - POST /api/insights/cycle           — run detector + persist anomalies
 *   - POST /api/insights/weekly/generate — trigger weekly report generation
 */

import * as React from "react";
import {
  AlertCircle,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  ChevronDown,
  FileText,
  Loader2,
  Mail,
  RefreshCw,
  Send,
  Sparkles,
  TrendingUp,
  XCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface AnomalyDict {
  type: string;
  severity: string;
  metric: string;
  current: number;
  baseline: number;
  delta_pct: number;
  message: string;
  detected_at: string;
  metadata?: Record<string, unknown>;
}

interface BehaviorInsight {
  category: string;
  feature: string;
  invocations: number;
  unique_users: number;
  last_used_at?: string | null;
  note: string;
}

interface WeeklyReportSummary {
  week_start: string;
  week_end: string;
  format: string;
  filename: string;
  size_bytes: number;
  summary: {
    total_dau: number;
    avg_dau: number;
    new_users: number;
    top_feature: string;
    top_feature_invocations: number;
    low_requirement_ids: string[];
    anomaly_count: number;
    req_count: number;
  };
  generated_at: string;
}

interface LatestResponse {
  latest_report: WeeklyReportSummary | null;
  anomalies: AnomalyDict[];
  behavior_insights: BehaviorInsight[];
  alert: { delivered: boolean; channels: string[]; count: number };
  generated_at: string;
}

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-rose-100 text-rose-800 border-rose-300",
  warning: "bg-amber-100 text-amber-800 border-amber-300",
  info: "bg-sky-100 text-sky-800 border-sky-300",
};

const CATEGORY_LABELS: Record<string, string> = {
  popular: "热门",
  low_usage: "低使用",
  abandoned: "已忽略",
};

export default function InsightsPage() {
  const [data, setData] = React.useState<LatestResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [generating, setGenerating] = React.useState(false);
  const [running, setRunning] = React.useState(false);

  const fetchLatest = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/insights/weekly/latest", { credentials: "include" });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      setData(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchLatest();
  }, [fetchLatest]);

  const runCycle = async () => {
    setRunning(true);
    try {
      const res = await fetch("/api/insights/cycle", { method: "POST", credentials: "include" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const cycle = await res.json();
      setData((d) =>
        d
          ? {
              ...d,
              anomalies: cycle.anomalies,
              behavior_insights: cycle.behavior_insights,
              alert: cycle.alert,
            }
          : d,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "运行失败");
    } finally {
      setRunning(false);
    }
  };

  const generateReport = async () => {
    setGenerating(true);
    try {
      const res = await fetch("/api/insights/weekly/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ fmt: "pdf" }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result = await res.json();
      setData((d) =>
        d
          ? {
              ...d,
              latest_report: {
                week_start: result.week.split(" ~ ")[0],
                week_end: result.week.split(" ~ ")[1],
                format: result.format,
                filename: result.filename || `${result.week}.pdf`,
                size_bytes: result.size_bytes,
                summary: result.summary,
                generated_at: new Date().toISOString(),
              },
            }
          : d,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setGenerating(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-500">
        <Loader2 className="h-5 w-5 animate-spin" /> 加载中...
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
        <AlertCircle className="mr-1 inline h-4 w-4" /> {error}
      </div>
    );
  }

  const report = data?.latest_report;
  const anomalies = data?.anomalies ?? [];
  const insights = data?.behavior_insights ?? [];

  return (
    <ErrorBoundary>(<div className="space-y-6 p-6">
        <header className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900">
              <Sparkles className="h-5 w-5 text-amber-500" /> 自动洞察
            </h1>
            <p className="text-sm text-slate-600">
              周报 + 异常告警 + 用户行为 — 实时呈现 v8.0 数据驱动
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={fetchLatest}>
              <RefreshCw className="h-3.5 w-3.5" /> 刷新
            </Button>
            <Button size="sm" variant="outline" onClick={runCycle} disabled={running}>
              {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <TrendingUp className="h-3.5 w-3.5" />}
              检测
            </Button>
            <Button size="sm" onClick={generateReport} disabled={generating}>
              {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mail className="h-3.5 w-3.5" />}
              生成周报
            </Button>
          </div>
        </header>
        {/* 周报摘要 */}
        {report && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FileText className="h-4 w-4 text-sky-600" />
                最新周报
                <span className="text-xs text-slate-500">
                  {report.week_start} ~ {report.week_end}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <Stat label="总 DAU" value={report.summary.total_dau?.toLocaleString() ?? "—"} />
                <Stat label="日均 DAU" value={report.summary.avg_dau?.toLocaleString() ?? "—"} />
                <Stat label="新用户" value={report.summary.new_users?.toLocaleString() ?? "—"} />
                <Stat
                  label="最热门"
                  value={report.summary.top_feature ?? "—"}
                  sub={`${report.summary.top_feature_invocations ?? 0} 次`}
                />
              </div>
              <div className="mt-3 text-xs text-slate-500">
                <Calendar className="mr-1 inline h-3 w-3" /> 生成于 {report.generated_at}
                <span className="ml-2">
                  格式: {report.format.toUpperCase()} · {(report.size_bytes / 1024).toFixed(1)} KB
                </span>
              </div>
            </CardContent>
          </Card>
        )}
        {/* 异常告警 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-rose-500" />
              异常告警
              <Badge variant="outline">{anomalies.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {anomalies.length === 0 ? (
              <p className="flex items-center gap-1 text-sm text-slate-500">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" /> 本时段无异常
              </p>
            ) : (
              <ul className="space-y-2">
                {anomalies.map((a, i) => (
                  <li
                    key={i}
                    className={cn(
                      "rounded-md border p-2 text-sm",
                      SEVERITY_STYLES[a.severity] ?? SEVERITY_STYLES.info,
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="uppercase">
                        {a.severity}
                      </Badge>
                      <span className="font-mono text-xs">{a.type}</span>
                      <span className="ml-auto text-xs text-slate-500">{a.detected_at}</span>
                    </div>
                    <p className="mt-1">{a.message}</p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        {/* 行为洞察 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-4 w-4 text-emerald-600" />
              用户行为分析
            </CardTitle>
          </CardHeader>
          <CardContent>
            {insights.length === 0 ? (
              <p className="text-sm text-slate-500">暂无数据</p>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {(["popular", "low_usage", "abandoned"] as const).map((cat) => {
                  const items = insights.filter((i) => i.category === cat);
                  return (
                    <div
                      key={cat}
                      className="rounded-md border border-slate-200 bg-slate-50 p-3"
                    >
                      <h3 className="mb-2 text-xs font-semibold uppercase text-slate-600">
                        {CATEGORY_LABELS[cat]} ({items.length})
                      </h3>
                      {items.length === 0 ? (
                        <p className="text-xs text-slate-400">无</p>
                      ) : (
                        <ul className="space-y-1">
                          {items.slice(0, 5).map((i, idx) => (
                            <li
                              key={idx}
                              className="rounded bg-white px-2 py-1 text-xs text-slate-700"
                            >
                              <span className="font-mono">{i.feature}</span>
                              <span className="ml-2 text-slate-500">
                                {i.invocations} 次 / {i.unique_users} 人
                              </span>
                              {i.last_used_at && (
                                <span className="ml-2 text-slate-400">
                                  · {i.last_used_at.slice(0, 10)}
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
        {data?.alert?.delivered && (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
            <Send className="mr-1 inline h-3 w-3" /> 告警已通过 {data.alert.channels.join(", ")} 通道推送
          </div>
        )}
      </div>)</ErrorBoundary>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold text-slate-900">{value}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  );
}
