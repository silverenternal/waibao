"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import * as React from "react";
import Link from "next/link";
import { apiKeysAdminApi, type ApiKeyRow } from "@/lib/api-public-keys";
import { ApiKeyForm } from "@/components/api-keys/ApiKeyForm";

export default function ApiKeysListPage() {
  const [list, setList] = React.useState<ApiKeyRow[] | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  async function load() {
    try {
      setList(await apiKeysAdminApi.list());
    } catch (e: any) {
      setErr(e?.message ?? "加载失败");
    }
  }
  React.useEffect(() => {
    load();
  }, []);

  async function revoke(row: ApiKeyRow) {
    if (!confirm(`撤销 API Key "${row.name}"?`)) return;
    setBusyId(row.id);
    try {
      await apiKeysAdminApi.revoke(row.id);
      await load();
    } catch (e: any) {
      setErr(e?.message ?? "撤销失败");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 max-w-5xl">
        <header className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold">API Keys</h1>
            <p className="text-sm text-slate-500 mt-1">
              第三方开发者通过 API Key 访问公开 API v1。
            </p>
          </div>
          <button
            onClick={() => setCreating((c) => !c)}
            className="px-3 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700"
          >
            {creating ? "取消新建" : "+ 新建 Key"}
          </button>
        </header>
        {err && (
          <div className="mb-4 rounded-md bg-red-50 border border-red-200 p-2 text-sm text-red-700">
            {err}
          </div>
        )}
        {creating && (
          <div className="mb-6">
            <ApiKeyForm
              onCancel={() => setCreating(false)}
              onSaved={() => {
                setCreating(false);
                load();
              }}
            />
          </div>
        )}
        {list === null && <div className="text-slate-500">加载中...</div>}
        {list && list.length === 0 && !creating && (
          <div className="rounded-md border border-dashed bg-white p-12 text-center text-slate-500">
            还没有 API Key。点击「新建 Key」开始。
          </div>
        )}
        {list && list.length > 0 && (
          <div className="space-y-3">
            {list.map((k) => (
              <div
                key={k.id}
                className="rounded-lg border bg-white p-4 flex items-start justify-between gap-4"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{k.name}</span>
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${
                        k.revoked_at
                          ? "bg-red-100 text-red-700"
                          : "bg-green-100 text-green-700"
                      }`}
                    >
                      {k.revoked_at ? "已撤销" : "启用"}
                    </span>
                    <span className="px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-700 font-mono">
                      {k.key_prefix}…
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {k.scopes.map((s) => (
                      <span
                        key={s}
                        className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-[11px] font-mono"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-2">
                    速率 {k.rate_limit_per_min}/min ·{" "}
                    {k.last_used_at
                      ? `上次调用 ${new Date(k.last_used_at).toLocaleString()}`
                      : "尚未调用"}
                  </div>
                </div>
                <div className="flex flex-col gap-2 items-end">
                  <Link
                    href={`/mothership/admin/api-keys/${k.id}`}
                    className="px-2 py-1 text-xs border rounded hover:bg-slate-50"
                  >
                    详情 / 用量
                  </Link>
                  {!k.revoked_at && (
                    <button
                      onClick={() => revoke(k)}
                      disabled={busyId === k.id}
                      className="px-2 py-1 text-xs border rounded text-red-600 hover:bg-red-50 disabled:opacity-50"
                    >
                      撤销
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>)</ErrorBoundary>
  );
}
