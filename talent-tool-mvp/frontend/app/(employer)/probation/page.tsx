"use client";

import * as React from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fetchTeamProbation, type TeamProbation } from "@/lib/api-probation";

const SAMPLE_ORG_ID = "demo-org";

/**
 * 试用期员工列表 (HR/经理视角).
 */
export default function ProbationListPage() {
  const [data, setData] = React.useState<TeamProbation | null>(null);
  const [loading, setLoading] = React.useState(false);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchTeamProbation(SAMPLE_ORG_ID));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  if (loading && !data) {
    return <div className="container mx-auto p-6 text-slate-500">加载中…</div>;
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">试用期员工</h1>
        <button className="text-sm text-blue-600 hover:underline" onClick={refresh}>
          刷新
        </button>
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Object.entries(data.stats).map(([k, v]) => (
            <Card key={k}>
              <CardContent className="pt-4">
                <p className="text-xs text-slate-500 uppercase">{k}</p>
                <p className="text-2xl font-bold mt-1">{v}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {data && (
        <Card>
          <CardHeader>
            <CardTitle>员工列表 ({data.employees.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-slate-500">
                  <th className="py-2">员工</th>
                  <th>入职日期</th>
                  <th>状态</th>
                  <th>最近评分</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.employees.map((emp) => (
                  <tr key={emp.id} className="border-b hover:bg-slate-50">
                    <td className="py-2 font-medium">{emp.name}</td>
                    <td>{emp.hire_date}</td>
                    <td>
                      <div className="flex gap-1">
                        {emp.tags.map((t) => (
                          <Badge
                            key={t}
                            variant={
                              t === "confirmed"
                                ? "default"
                                : t === "at_risk"
                                  ? "destructive"
                                  : "secondary"
                            }
                          >
                            {t}
                          </Badge>
                        ))}
                      </div>
                    </td>
                    <td>{emp.latest_score?.toFixed(2) ?? "-"}</td>
                    <td>
                      <Link
                        href={`/probation/${emp.id}`}
                        className="text-blue-600 hover:underline text-xs"
                      >
                        查看
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
