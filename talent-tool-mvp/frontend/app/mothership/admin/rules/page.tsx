"use client";

import * as React from "react";
import Link from "next/link";
import { rulesApi, type BuiltinTrigger, type RuleRow } from "@/lib/api-rules";
import { RuleEditor } from "@/components/rules/RuleEditor";

export default function RulesListPage() {
  const [list, setList] = React.useState<RuleRow[] | null>(null);
  const [triggers, setTriggers] = React.useState<BuiltinTrigger[]>([]);
  const [creating, setCreating] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  async function load() {
    try {
      const [rows, tg] = await Promise.all([
        rulesApi.list(),
        rulesApi.triggers(),
      ]);
      setList(rows);
      setTriggers(tg.triggers);
    } catch (e: any) {
      setErr(e?.message ?? "加载失败");
    }
  }
  React.useEffect(() => {
    load();
  }, []);

  async function remove(r: RuleRow) {
    if (!confirm(`删除规则 "${r.name}"?`)) return;
    try {
      await rulesApi.remove(r.id);
      await load();
    } catch (e: any) {
      setErr(e?.message ?? "删除失败");
    }
  }

  return (
    <div className="container mx-auto p-6 max-w-5xl">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">自动化规则</h1>
          <p className="text-sm text-slate-500 mt-1">
            可视化编辑触发器 + 条件 + 动作,失败不影响业务。
          </p>
        </div>
        <button
          onClick={() => setCreating((c) => !c)}
          className="px-3 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700"
        >
          {creating ? "取消" : "+ 新建规则"}
        </button>
      </header>

      {err && (
        <div className="mb-4 rounded-md bg-red-50 border border-red-200 p-2 text-sm text-red-700">
          {err}
        </div>
      )}

      {creating && (
        <div className="mb-6 rounded-lg border bg-white p-5">
          <RuleEditor
            triggers={triggers}
            onSubmit={async (body) => {
              await rulesApi.create(body);
              setCreating(false);
              await load();
            }}
            submitLabel="创建规则"
          />
        </div>
      )}

      {list === null && <div className="text-slate-500">加载中...</div>}

      {list && list.length === 0 && !creating && (
        <div className="rounded-md border border-dashed bg-white p-12 text-center text-slate-500">
          还没有规则。
        </div>
      )}

      {list && list.length > 0 && (
        <div className="space-y-3">
          {list.map((r) => (
            <div
              key={r.id}
              className="rounded-lg border bg-white p-4 flex items-start justify-between gap-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{r.name}</span>
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      r.enabled
                        ? "bg-green-100 text-green-700"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {r.enabled ? "启用" : "暂停"}
                  </span>
                  <span className="px-2 py-0.5 rounded text-xs bg-blue-50 text-blue-700 font-mono">
                    {r.trigger}
                  </span>
                </div>
                {r.description && (
                  <div className="text-xs text-slate-500 mt-1">
                    {r.description}
                  </div>
                )}
                <div className="text-[11px] text-slate-500 mt-2">
                  触发 {r.trigger_count} 次 · 冷却 {r.cooldown_seconds}s
                </div>
              </div>
              <div className="flex flex-col gap-2 items-end">
                <Link
                  href={`/mothership/admin/rules/${r.id}`}
                  className="px-2 py-1 text-xs border rounded hover:bg-slate-50"
                >
                  编辑 / 测试
                </Link>
                <button
                  onClick={() => remove(r)}
                  className="px-2 py-1 text-xs border rounded text-red-600 hover:bg-red-50"
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
