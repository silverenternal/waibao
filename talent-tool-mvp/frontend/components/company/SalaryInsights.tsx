"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface SalaryInsightsProps {
  salary: {
    company_id: string;
    median_k: number;
    p25_k?: number | null;
    p75_k?: number | null;
    sample_size: number;
    currency: string;
    by_role: Record<string, number>;
    last_updated?: string | null;
  } | null;
  loading?: boolean;
}

export function SalaryInsights({ salary, loading }: SalaryInsightsProps) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-400 text-sm">加载薪资中…</CardContent>
      </Card>
    );
  }

  if (!salary) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-500 text-sm">暂无薪资数据</CardContent>
      </Card>
    );
  }

  const symbol = salary.currency === "CNY" ? "¥" : salary.currency === "USD" ? "$" : "";
  const roleEntries = Object.entries(salary.by_role || {}).sort(
    (a, b) => b[1] - a[1]
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">薪资洞察</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold text-amber-600">
            {symbol}
            {salary.median_k.toFixed(1)}k
          </span>
          <span className="text-sm text-slate-500">月薪中位数</span>
        </div>
        <div className="text-xs text-slate-500">
          基于 {salary.sample_size.toLocaleString()} 份样本 · 更新于{" "}
          {salary.last_updated?.slice(0, 10) ?? "-"}
        </div>

        {salary.p25_k != null && salary.p75_k != null && (
          <div className="text-xs">
            <span className="text-slate-500">区间: </span>
            <span className="font-medium">
              {symbol}
              {salary.p25_k.toFixed(1)}k - {symbol}
              {salary.p75_k.toFixed(1)}k
            </span>
          </div>
        )}

        {roleEntries.length > 0 && (
          <div className="space-y-1 pt-2 border-t">
            <div className="text-xs font-medium text-slate-700 mb-1">按岗位:</div>
            {roleEntries.map(([role, k]) => (
              <div key={role} className="flex justify-between text-xs">
                <span className="text-slate-600">{role}</span>
                <span className="font-medium">
                  {symbol}
                  {Number(k).toFixed(1)}k
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}