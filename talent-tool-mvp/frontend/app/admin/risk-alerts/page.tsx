"use client";

/**
 * v11.0 T6110 — Admin risk-alert dashboard.
 *
 * Admins/HR see ONLY the redacted risk_level + reason (+ matched-keyword
 * category hint + ticket id) — never the user's raw private conversation.
 * That invariant is enforced server-side (the risk_alerts table has no
 * verbatim-text column and is RLS-gated); this page simply renders what the
 * redacted API returns.
 *
 * Server contract:
 *   GET /api/admin/risk-alerts?risk_level=&organisation_id=&limit=
 */
import * as React from "react";
import { AlertTriangle, Heart, Loader2, RefreshCw, ShieldAlert } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RiskAlertBadge } from "@/components/safety/RiskAlertBadge";
import { listRiskAlerts, SELF_HARM_HOTLINE, type RiskAlert, type RiskLevel } from "@/lib/api-safety";

const RULE_LABEL: Record<string, string> = {
  self_harm: "自伤风险",
  labour_dispute: "劳动争议",
};

export default function RiskAlertsAdminPage() {
  const [alerts, setAlerts] = React.useState<RiskAlert[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [riskFilter, setRiskFilter] = React.useState<RiskLevel | "">("");

  const fetchAlerts = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listRiskAlerts(riskFilter ? { risk_level: riskFilter } : undefined);
      setAlerts(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [riskFilter]);

  React.useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const criticalCount = alerts.filter((a) => a.risk_level === "critical").length;
  const highCount = alerts.filter((a) => a.risk_level === "high").length;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <ShieldAlert className="h-6 w-6 text-rose-600" />
            风险提醒
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            出于隐私保护,这里只展示风险等级与原因,不包含任何原始对话内容。
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchAlerts} disabled={loading}>
          <RefreshCw className={cn("mr-1 h-4 w-4", loading && "animate-spin")} />
          刷新
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Card className="border-rose-200 dark:border-rose-900">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-rose-700 dark:text-rose-300">
              紧急 (自伤风险)
            </CardTitle>
            <Heart className="h-4 w-4 text-rose-600" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{criticalCount}</div>
            <p className="text-xs text-muted-foreground">
              心理援助热线 {SELF_HARM_HOTLINE}
            </p>
          </CardContent>
        </Card>
        <Card className="border-amber-200 dark:border-amber-900">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-amber-700 dark:text-amber-300">
              高 (劳动争议)
            </CardTitle>
            <AlertTriangle className="h-4 w-4 text-amber-600" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{highCount}</div>
            <p className="text-xs text-muted-foreground">转 HR / 法务工单</p>
          </CardContent>
        </Card>
      </div>

      {/* Filter */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">筛选:</span>
        {(["", "critical", "high"] as const).map((lvl) => (
          <Button
            key={lvl || "all"}
            size="sm"
            variant={riskFilter === lvl ? "default" : "outline"}
            onClick={() => setRiskFilter(lvl as RiskLevel | "")}
          >
            {lvl === "" ? "全部" : lvl === "critical" ? "紧急" : "高"}
          </Button>
        ))}
      </div>

      {error ? (
        <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>
      ) : null}

      {/* List */}
      {loading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" /> 加载中…
        </div>
      ) : alerts.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            暂无风险提醒。
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {alerts.map((a) => (
            <Card key={a.id} className={cn(a.risk_level === "critical" && "border-rose-200 dark:border-rose-900")}>
              <CardContent className="flex flex-col gap-2 py-4">
                <div className="flex items-center justify-between gap-2">
                  <RiskAlertBadge rule={a.rule} risk_level={a.risk_level} reason={a.reason} />
                  <span className="text-xs text-muted-foreground">
                    {new Date(a.created_at).toLocaleString("zh-CN")}
                  </span>
                </div>
                <p className="text-sm">{a.reason}</p>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>用户: {a.user_id.slice(0, 8)}…</span>
                  <span>类别: {RULE_LABEL[a.rule] || a.rule}</span>
                  {a.matched_keywords.length > 0 ? (
                    <span>关键词类目: {a.matched_keywords.join("、")}</span>
                  ) : null}
                  {a.ticket_id ? <span>工单: #{a.ticket_id.slice(0, 8)}</span> : null}
                  <span>已通知 HR: {a.notified ? "是" : "否"}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
