"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AttritionRiskCard } from "@/components/attrition/AttritionRiskCard";
import {
  getTeamRisk,
  RISK_LEVEL_COLOR,
  RISK_LEVEL_LABEL,
  type TeamRisk,
} from "@/lib/api-attrition";

const SAMPLE_ORG_ID = "demo-org";
const SAMPLE_USER_IDS = Array.from({ length: 30 }, (_, i) => `user-${i + 1}`);

/**
 * HR 离职风险 dashboard (T2403).
 *
 * 展示:
 * - 团队风险热力图 (按 risk_level 分组)
 * - 风险排行 (top-20)
 * - 一键关怀
 */
export default function AttritionDashboardPage() {
  const [data, setData] = React.useState<TeamRisk | null>(null);
  const [loading, setLoading] = React.useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const r = await getTeamRisk(SAMPLE_ORG_ID, SAMPLE_USER_IDS);
      setData(r);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    fetchData();
  }, []);

  if (loading && !data) {
    return <div className="container mx-auto p-6 text-slate-500">加载中…</div>;
  }

  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">团队离职风险</h1>
          <button
            className="text-sm text-blue-600 hover:underline"
            onClick={fetchData}
          >
            刷新
          </button>
        </div>
        {data && (
          <>
            {/* 概览 */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs text-slate-500">团队人数</div>
                  <div className="text-2xl font-bold">{data.total}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs text-rose-600">高风险</div>
                  <div className="text-2xl font-bold text-rose-600">
                    {data.high_risk}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs text-amber-600">中风险</div>
                  <div className="text-2xl font-bold text-amber-600">
                    {data.medium_risk}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs text-slate-500">平均风险</div>
                  <div className="text-2xl font-bold">
                    {(data.avg_risk_score * 100).toFixed(0)}%
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* 热力图 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">风险分布热力图</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-3">
                  {(["low", "medium", "high"] as const).map((level) => {
                    const count = level === "low"
                      ? data.low_risk
                      : level === "medium"
                        ? data.medium_risk
                        : data.high_risk;
                    const pct = data.total > 0 ? (count / data.total) * 100 : 0;
                    const heat =
                      level === "high" ? Math.min(100, pct * 2) :
                      level === "medium" ? Math.min(80, pct * 1.5) :
                      Math.min(60, pct);
                    return (
                      <div
                        key={level}
                        className={`p-4 rounded-lg border-2 ${RISK_LEVEL_COLOR[level]}`}
                        style={{ opacity: 0.4 + (heat / 100) * 0.6 }}
                      >
                        <div className="text-xs font-medium">
                          {RISK_LEVEL_LABEL[level]}
                        </div>
                        <div className="text-2xl font-bold mt-1">{count}</div>
                        <div className="text-xs mt-1">
                          {pct.toFixed(1)}%
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* 风险排行 (top-20) */}
            <div>
              <h2 className="text-lg font-semibold mb-3">风险排行 Top 20</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {data.risk_users.map((r) => (
                  <AttritionRiskCard key={r.user_id} risk={r} />
                ))}
              </div>
            </div>
          </>
        )}
      </div>)</ErrorBoundary>
  );
}