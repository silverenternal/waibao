"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getSalaryPercentiles,
  type SalaryDistribution,
} from "@/lib/api-salary";
import { SalaryDistributionChart } from "@/components/salary/SalaryDistributionChart";

const ROLES = ["python", "frontend", "backend", "data", "algorithm"];
const SENIORITIES = ["junior", "mid", "senior", "lead", "manager"];
const CITIES = ["北京", "上海", "深圳", "杭州"];

/**
 * HR 视角: 各职级薪资分位 (T2402).
 */
export default function SalaryReportPage() {
  const [city, setCity] = React.useState("北京");
  const [distMap, setDistMap] = React.useState<Record<string, SalaryDistribution>>({});
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    setLoading(true);
    Promise.all(
      ROLES.flatMap((role) =>
        SENIORITIES.map((sen) =>
          getSalaryPercentiles(role, city, sen).catch(() => null)
        )
      )
    )
      .then((results) => {
        const m: Record<string, SalaryDistribution> = {};
        ROLES.forEach((role) => {
          SENIORITIES.forEach((sen) => {
            const idx = ROLES.indexOf(role) * SENIORITIES.length + SENIORITIES.indexOf(sen);
            if (results[idx]) m[`${role}-${sen}`] = results[idx];
          });
        });
        setDistMap(m);
      })
      .finally(() => setLoading(false));
  }, [city]);

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">薪资报告 (HR 视角)</h1>
        <select
          className="border rounded p-2"
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

      {loading && <div className="text-sm text-slate-500">加载中…</div>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {ROLES.map((role) =>
          SENIORITIES.map((sen) => {
            const key = `${role}-${sen}`;
            const d = distMap[key];
            return (
              <Card key={key}>
                <CardHeader className="pb-1">
                  <CardTitle className="text-sm">
                    {role} · {sen}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {d ? (
                    <div className="grid grid-cols-5 gap-2 text-center text-xs">
                      <div>
                        <div className="text-slate-500">P10</div>
                        <div className="font-medium">¥{d.p10_k}k</div>
                      </div>
                      <div>
                        <div className="text-slate-500">P25</div>
                        <div className="font-medium">¥{d.p25_k}k</div>
                      </div>
                      <div>
                        <div className="text-amber-700 font-bold">P50</div>
                        <div className="font-bold">¥{d.p50_k}k</div>
                      </div>
                      <div>
                        <div className="text-slate-500">P75</div>
                        <div className="font-medium">¥{d.p75_k}k</div>
                      </div>
                      <div>
                        <div className="text-slate-500">P90</div>
                        <div className="font-medium">¥{d.p90_k}k</div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs text-slate-400">无数据</div>
                  )}
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}