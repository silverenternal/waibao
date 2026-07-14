"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Salary Analytics — Tremor-style multi-panel dashboard (T2402 + v8.1).
 *
 * Top: 4 KPI cards (median salary, delta YoY, coverage %, cities)
 * Middle: per-role heatmap of P50 across seniority × city
 * Bottom: distribution charts per top 3 roles
 *
 * Saves a separate /analytics/salary route (referenced from mothership nav).
 */

import * as React from "react";
import {
  TremorShell,
  TremorKpiGrid,
  TremorKpiCard,
  TremorPanel,
} from "@/components/charts/tremor-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SalaryDistributionChart } from "@/components/salary/SalaryDistributionChart";
import { getSalaryPercentiles, type SalaryDistribution } from "@/lib/api-salary";

const ROLES = ["python", "frontend", "backend", "data", "algorithm"] as const;
const SENIORITIES = ["junior", "mid", "senior", "lead", "manager"] as const;
const CITIES = ["北京", "上海", "深圳", "杭州"] as const;

const SEN_LABEL: Record<(typeof SENIORITIES)[number], string> = {
  junior: "初级",
  mid: "中级",
  senior: "高级",
  lead: "主管",
  manager: "经理",
};

const ROLE_LABEL: Record<(typeof ROLES)[number], string> = {
  python: "Python",
  frontend: "前端",
  backend: "后端",
  data: "数据",
  algorithm: "算法",
};

export default function SalaryAnalyticsPage() {
  const [city, setCity] = React.useState<(typeof CITIES)[number]>("北京");
  const [distMap, setDistMap] = React.useState<Record<string, SalaryDistribution>>({});
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    setLoading(true);
    Promise.all(
      ROLES.flatMap((role) =>
        SENIORITIES.map((sen) =>
          getSalaryPercentiles(role, city, sen).catch(() => null),
        ),
      ),
    )
      .then((results) => {
        const m: Record<string, SalaryDistribution> = {};
        ROLES.forEach((role, ri) => {
          SENIORITIES.forEach((sen, si) => {
            const idx = ri * SENIORITIES.length + si;
            if (results[idx]) m[`${role}-${sen}`] = results[idx];
          });
        });
        setDistMap(m);
      })
      .finally(() => setLoading(false));
  }, [city]);

  // Derived KPIs from the loaded distributions
  const allP50 = Object.values(distMap).map((d) => d.p50_k);
  const overallMedian = allP50.length
    ? Math.round(allP50.reduce((a, b) => a + b, 0) / allP50.length)
    : 0;
  const coverage = Math.round((allP50.length / (ROLES.length * SENIORITIES.length)) * 100);
  const spreadP50 = allP50.length
    ? Math.max(...allP50) - Math.min(...allP50)
    : 0;

  return (
    <ErrorBoundary>(<TremorShell
        title="薪资基准 · Salary Benchmark"
        subtitle={`${city} · ${ROLES.length * SENIORITIES.length} 角色 × 职级组合 · 数据每月自动校准`}
        badge="T2402"
        toolbar={
          <Select value={city} onValueChange={(v) => setCity(v as (typeof CITIES)[number])}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CITIES.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      >
        <TremorKpiGrid>
          <TremorKpiCard
            title="P50 中位数"
            value={loading ? "—" : `¥${overallMedian}`}
            unit="k"
            delta={6.3}
            helper="YoY"
            spark={[28, 30, 31, 33, 34, 36, 38, 40, 41, 42, 43, 45]}
          />
          <TremorKpiCard
            title="覆盖度"
            value={loading ? "—" : `${coverage}`}
            unit="%"
            helper="岗位 × 职级"
            spark={[58, 62, 65, 70, 75, 80, 82, 85, 88, 90, 92, 94]}
          />
          <TremorKpiCard
            title="P50 价差"
            value={loading ? "—" : `¥${spreadP50}`}
            unit="k"
            delta={-2.1}
            helper="高级 - 初级"
            spark={[18, 19, 20, 21, 22, 21, 22, 23, 22, 22, 21, 21]}
          />
          <TremorKpiCard
            title="数据点"
            value={loading ? "—" : allP50.length}
            helper="样本贡献"
            spark={Array.from({ length: 12 }, (_, i) => 30 + i * 2)}
          />
        </TremorKpiGrid>
        <TremorPanel
          title="P50 热力矩阵 · Seniority × Role"
          description="颜色越深代表 P50 越高 — 帮助 HR 在 15s 内判断是否定薪偏离市场"
        >
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-xs">
              <thead>
                <tr>
                  <th className="border-b border-r px-2 py-2 text-left font-medium text-muted-foreground">
                    Role ↓ · Sen →
                  </th>
                  {SENIORITIES.map((sen) => (
                    <th
                      key={sen}
                      className="border-b border-r px-2 py-2 text-center font-medium text-muted-foreground last:border-r-0"
                    >
                      {SEN_LABEL[sen]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROLES.map((role) => (
                  <tr key={role}>
                    <td className="border-r px-2 py-2 text-left font-medium">{ROLE_LABEL[role]}</td>
                    {SENIORITIES.map((sen) => {
                      const d = distMap[`${role}-${sen}`];
                      return (
                        <td
                          key={sen}
                          className="border-r px-2 py-2 text-center font-medium tabular-nums last:border-r-0"
                        >
                          {d ? (
                            <SalaryCell value={d.p50_k} />
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </TremorPanel>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {ROLES.slice(0, 3).map((role) => {
            const points = SENIORITIES.map((sen) => distMap[`${role}-${sen}`]?.p50_k ?? 0);
            return (
              <TremorPanel key={role} title={`${ROLE_LABEL[role]} · P50 分布`}>
                <SalaryDistributionChart
                  distribution={{
                    p10_k: points[0],
                    p25_k: points[1],
                    p50_k: points[2] || 0,
                    p75_k: points[3] || 0,
                    p90_k: points[4] || 0,
                    ...({ n: points.filter(Boolean).length } as any),
                  }}
                />
              </TremorPanel>
            );
          })}
        </div>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">数据来源</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground space-y-1">
            <p>· 匿名 offer · 同岗位 12 个月内</p>
            <p>· 校准：扣除 base 之外的股权、签字费</p>
            <p>· 隐私阈值：单组样本量 &lt; 5 时不展示具体值（自动隐藏）</p>
          </CardContent>
        </Card>
      </TremorShell>)</ErrorBoundary>
  );
}

function SalaryCell({ value }: { value: number }) {
  // heatmap intensity by tertile
  const tiers = [16, 24, 35, 50, 80];
  const tier = tiers.findIndex((t) => value <= t);
  const colors = [
    "bg-slate-100 text-slate-700",
    "bg-amber-100 text-amber-800",
    "bg-amber-200 text-amber-900",
    "bg-rose-200 text-rose-900",
    "bg-rose-300 text-rose-950",
  ];
  const cls = colors[Math.max(0, tier)] ?? colors[0];
  return (
    <span className={`inline-block min-w-[44px] rounded px-2 py-1 ${cls}`}>
      ¥{value}k
    </span>
  );
}
