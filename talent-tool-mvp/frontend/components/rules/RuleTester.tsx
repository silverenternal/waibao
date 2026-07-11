"use client";

import * as React from "react";
import { rulesApi } from "@/lib/api-rules";

interface Props {
  ruleId: string;
  defaultContext?: Record<string, unknown>;
}

/**
 * 规则回放测试器 (T804).
 * 输入 JSON context,显示是否命中 + 条件 trace + 动作执行结果.
 */
export function RuleTester({ ruleId, defaultContext }: Props) {
  const [ctx, setCtx] = React.useState(
    JSON.stringify(defaultContext ?? { rate: 0.5, window: "7d" }, null, 2),
  );
  const [dryRun, setDryRun] = React.useState(true);
  const [result, setResult] = React.useState<{
    matched: boolean;
    condition_trace: Array<Record<string, unknown>>;
    actions_executed: Array<Record<string, unknown>>;
    duration_ms: number;
    error: string | null;
  } | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  async function run() {
    setErr(null);
    setBusy(true);
    setResult(null);
    try {
      const parsed = JSON.parse(ctx || "{}");
      const r = await rulesApi.test(ruleId, parsed, dryRun);
      setResult(r);
    } catch (e: any) {
      setErr(e?.message ?? "测试失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border bg-white p-4 space-y-3">
      <h3 className="font-semibold text-sm">回放测试</h3>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-[11px] text-slate-600 mb-1">
            Context (JSON)
          </label>
          <textarea
            value={ctx}
            onChange={(e) => setCtx(e.target.value)}
            rows={8}
            className="w-full font-mono text-[11px] rounded border-slate-300 border p-2"
          />
        </div>
        <div>
          <label className="block text-[11px] text-slate-600 mb-1">
            结果
          </label>
          <div className="rounded border bg-slate-50 p-2 text-[11px] min-h-[8rem]">
            {!result && !err && <div className="text-slate-500">尚未运行</div>}
            {err && <div className="text-red-600">{err}</div>}
            {result && (
              <div className="space-y-2">
                <div>
                  <span className="text-slate-500">命中:</span>{" "}
                  <b
                    className={result.matched ? "text-emerald-700" : "text-red-700"}
                  >
                    {result.matched ? "是" : "否"}
                  </b>
                  <span className="ml-3 text-slate-500">
                    耗时 {result.duration_ms}ms
                  </span>
                  {result.error && (
                    <span className="ml-2 text-red-600">{result.error}</span>
                  )}
                </div>
                {result.condition_trace.length > 0 && (
                  <div>
                    <div className="text-slate-500">条件 trace:</div>
                    <pre className="font-mono text-[10px] bg-white p-1 rounded">
                      {JSON.stringify(result.condition_trace, null, 2)}
                    </pre>
                  </div>
                )}
                {result.actions_executed.length > 0 && (
                  <div>
                    <div className="text-slate-500">动作执行:</div>
                    <pre className="font-mono text-[10px] bg-white p-1 rounded">
                      {JSON.stringify(result.actions_executed, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center justify-between">
        <label className="text-xs flex items-center gap-2">
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
          />
          Dry Run (不真正发送通知/建单)
        </label>
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="px-3 py-1.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? "运行中..." : "运行"}
        </button>
      </div>
    </div>
  );
}
