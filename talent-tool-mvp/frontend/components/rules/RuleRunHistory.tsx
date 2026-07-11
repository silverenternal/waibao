"use client";

import * as React from "react";
import { rulesApi, type RuleRun } from "@/lib/api-rules";

interface Props {
  ruleId: string;
}

/**
 * 规则运行历史 (T804).
 */
export function RuleRunHistory({ ruleId }: Props) {
  const [runs, setRuns] = React.useState<RuleRun[] | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    rulesApi
      .runs(ruleId, 50)
      .then((r) => !cancelled && setRuns(r))
      .catch((e) => !cancelled && setErr(e?.message ?? "加载失败"));
    return () => {
      cancelled = true;
    };
  }, [ruleId]);

  if (err)
    return <div className="text-xs text-red-600">运行历史加载失败: {err}</div>;
  if (!runs) return <div className="text-xs text-slate-500">加载中...</div>;
  if (runs.length === 0)
    return (
      <div className="rounded border border-dashed bg-white p-6 text-center text-xs text-slate-500">
        暂无运行记录
      </div>
    );

  return (
    <div className="rounded-lg border bg-white">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-slate-50 text-left">
            <th className="px-3 py-2 font-medium">时间</th>
            <th className="px-3 py-2 font-medium">命中</th>
            <th className="px-3 py-2 font-medium">耗时</th>
            <th className="px-3 py-2 font-medium">触发器</th>
            <th className="px-3 py-2 font-medium">错误</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} className="border-t">
              <td className="px-3 py-1.5 text-slate-600">
                {new Date(r.occurred_at).toLocaleString()}
              </td>
              <td className="px-3 py-1.5">
                {r.matched ? (
                  <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-700">
                    是
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                    否
                  </span>
                )}
              </td>
              <td className="px-3 py-1.5 text-slate-600">{r.duration_ms}ms</td>
              <td className="px-3 py-1.5 font-mono text-slate-700">
                {r.trigger}
              </td>
              <td className="px-3 py-1.5 text-red-600">{r.error ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
