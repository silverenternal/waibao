"use client";

import * as React from "react";
import { apiKeysAdminApi, type ApiKeyUsage } from "@/lib/api-public-keys";

interface Props {
  apiKeyId: string;
}

/**
 * 用量统计柱状图 (T803).
 *
 * 极简 SVG 实现 (避免引入额外图表库):
 * - 横轴: endpoint
 * - 纵轴: 调用次数
 */
export function ApiKeyUsageChart({ apiKeyId }: Props) {
  const [data, setData] = React.useState<ApiKeyUsage | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [days, setDays] = React.useState(7);

  React.useEffect(() => {
    let cancelled = false;
    apiKeysAdminApi
      .usage(apiKeyId, days)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setErr(e?.message ?? "加载失败"));
    return () => {
      cancelled = true;
    };
  }, [apiKeyId, days]);

  if (err)
    return <div className="text-xs text-red-600">用量加载失败: {err}</div>;
  if (!data) return <div className="text-xs text-slate-500">加载中...</div>;

  const max = Math.max(1, ...data.per_endpoint.map((b) => b.calls));
  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-sm">近 {days} 天用量</h3>
        <div className="flex items-center gap-3 text-xs text-slate-600">
          <span>
            总调用 <b>{data.total_calls}</b>
          </span>
          <span>
            成功率 <b>{(data.success_rate * 100).toFixed(1)}%</b>
          </span>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="border rounded px-1.5 py-0.5 text-xs"
          >
            <option value={1}>1d</option>
            <option value={7}>7d</option>
            <option value={30}>30d</option>
          </select>
        </div>
      </div>
      {data.per_endpoint.length === 0 ? (
        <div className="text-xs text-slate-500">暂无调用</div>
      ) : (
        <div className="space-y-2">
          {data.per_endpoint.map((b) => (
            <div key={b.endpoint} className="text-xs">
              <div className="flex items-center justify-between mb-0.5">
                <code className="font-mono text-slate-700 truncate max-w-md">
                  {b.endpoint}
                </code>
                <span className="text-slate-500">
                  {b.calls} · avg {b.avg_status.toFixed(0)}
                </span>
              </div>
              <div className="h-2 bg-slate-100 rounded overflow-hidden">
                <div
                  className="h-full bg-blue-500"
                  style={{ width: `${(b.calls / max) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
