"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  getSalaryInsights,
  type SalaryDistribution,
  type SalaryTrend,
} from "@/lib/api-salary";
import { SalaryDistributionChart } from "@/components/salary/SalaryDistributionChart";
import { SalaryTrendChart } from "@/components/salary/SalaryTrendChart";
import { MyOfferPosition } from "@/components/salary/MyOfferPosition";

const CITIES = ["北京", "上海", "深圳", "杭州", "广州", "成都"];
const ROLES = ["python", "frontend", "backend", "data", "algorithm", "product", "design"];
const SENIORITIES = ["intern", "junior", "mid", "senior", "lead"];

/**
 * 薪资洞察页 (T2402) - 求职者视角.
 *
 * 展示:
 * - 选择器 (role × city × seniority)
 * - 行业薪资分布 (箱线图)
 * - 薪资趋势 (折线图)
 * - 我的定位 (offer 在 P 几)
 */
export default function SalaryInsightsPage() {
  const [role, setRole] = React.useState("python");
  const [city, setCity] = React.useState("北京");
  const [seniority, setSeniority] = React.useState("mid");
  const [dist, setDist] = React.useState<SalaryDistribution | null>(null);
  const [trend, setTrend] = React.useState<SalaryTrend | null>(null);
  const [loading, setLoading] = React.useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const r = await getSalaryInsights(role, city, seniority);
      setDist(r.distribution);
      setTrend(r.trend);
    } catch (e) {
      setDist(null);
      setTrend(null);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    fetchData();
  }, [role, city, seniority]);

  return (
    <div className="container mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold">薪资洞察</h1>

      {/* 选择器 */}
      <Card>
        <CardContent className="p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="text-xs text-slate-500">岗位</label>
            <select
              className="w-full border rounded p-2 mt-1"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">城市</label>
            <select
              className="w-full border rounded p-2 mt-1"
              value={city}
              onChange={(e) => setCity(e.target.value)}
            >
              {CITIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">职级</label>
            <select
              className="w-full border rounded p-2 mt-1"
              value={seniority}
              onChange={(e) => setSeniority(e.target.value)}
            >
              {SENIORITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <SalaryDistributionChart distribution={dist} loading={loading} />
          <SalaryTrendChart trend={trend} loading={loading} />
        </div>
        <div>
          <MyOfferPosition
            role={role}
            city={city}
            seniority={seniority}
            defaultOfferK={dist?.p50_k ?? 25}
          />
        </div>
      </div>
    </div>
  );
}