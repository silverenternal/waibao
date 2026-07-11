/**
 * Cost dashboard admin page (T806).
 *
 * 展示:总成本 / per-provider / per-tenant / 日趋势 / cache 命中率.
 */
"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { CostByProviderChart } from "@/components/cost/CostByProviderChart";
import { CostByTenantTable } from "@/components/cost/CostByTenantTable";
import { CacheHitRateGauge } from "@/components/cost/CacheHitRateGauge";
import { DailyCostTrend } from "@/components/cost/DailyCostTrend";
import {
  costApi,
  type CacheStats,
  type CostSummary,
  type TenantCost,
} from "@/lib/api-cost";

const SINCE_OPTIONS = [
  { value: "1", label: "Last 24h" },
  { value: "7", label: "Last 7d" },
  { value: "30", label: "Last 30d" },
  { value: "90", label: "Last 90d" },
];

export default function CostDashboardPage() {
  const [sinceDays, setSinceDays] = React.useState(30);
  const [tenantFilter, setTenantFilter] = React.useState<string>("all");
  const [summary, setSummary] = React.useState<CostSummary | null>(null);
  const [cacheStats, setCacheStats] = React.useState<CacheStats | null>(null);
  const [tenants, setTenants] = React.useState<TenantCost[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  const refresh = React.useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const tenantId = tenantFilter === "all" ? undefined : tenantFilter;
      const [s, c, t] = await Promise.all([
        costApi.getSummary(tenantId, sinceDays),
        costApi.getCacheStats(),
        costApi.getByTenant(sinceDays),
      ]);
      setSummary(s);
      setCacheStats(c);
      setTenants(t);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, [sinceDays, tenantFilter]);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  // Auto refresh every 60s for active dashboard
  React.useEffect(() => {
    const timer = setInterval(refresh, 60_000);
    return () => clearInterval(timer);
  }, [refresh]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Cost Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            LLM cost aggregated by tenant / provider / model. Persisted to Supabase
            within ~30 seconds of each call.
          </p>
        </div>
        <div className="flex items-end gap-3 flex-wrap">
          <div className="space-y-1">
            <Label className="text-xs">Since</Label>
            <Select value={String(sinceDays)} onValueChange={(v) => v && setSinceDays(Number(v))}>
              <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
              <SelectContent>
                {SINCE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Tenant</Label>
            <Select value={tenantFilter} onValueChange={(v) => v && setTenantFilter(v)}>
              <SelectTrigger className="w-44">
                <SelectValue placeholder="All tenants" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                {(tenants || []).map((t) => (
                  <SelectItem key={t.tenant_id} value={t.tenant_id}>
                    {t.tenant_id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button variant="outline" onClick={refresh} disabled={loading}>
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <Card>
          <CardContent className="text-sm text-destructive py-3">{error}</CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SummaryTile
          label="Total Cost"
          value={summary ? `$${summary.total_cost_usd.toFixed(2)}` : "—"}
          sub={`Last ${sinceDays}d`}
          loading={loading}
        />
        <SummaryTile
          label="Providers Active"
          value={summary ? summary.by_provider.length.toString() : "—"}
          sub="Distinct providers"
          loading={loading}
        />
        <SummaryTile
          label="Tenants Active"
          value={summary ? summary.by_tenant.length.toString() : "—"}
          sub="Distinct tenants"
          loading={loading}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {cacheStats ? (
          <CacheHitRateGauge stats={cacheStats} />
        ) : (
          <Skeleton className="h-72" />
        )}
        {summary ? (
          <CostByProviderChart data={summary.by_provider} />
        ) : (
          <Skeleton className="h-72 lg:col-span-2" />
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {summary ? (
          <div className="lg:col-span-2">
            <DailyCostTrend data={summary.daily_trend} />
          </div>
        ) : (
          <Skeleton className="h-72 lg:col-span-2" />
        )}
        {summary ? (
          <CostByTenantTable data={summary.by_tenant} />
        ) : (
          <Skeleton className="h-72" />
        )}
      </div>
    </div>
  );
}

function SummaryTile({
  label,
  value,
  sub,
  loading,
}: {
  label: string;
  value: string;
  sub?: string;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading && !value ? (
          <Skeleton className="h-10 w-32" />
        ) : (
          <>
            <div className="text-2xl font-mono">{value}</div>
            {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
          </>
        )}
      </CardContent>
    </Card>
  );
}
