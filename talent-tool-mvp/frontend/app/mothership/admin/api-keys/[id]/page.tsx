"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import * as React from "react";
import { use } from "react";
import Link from "next/link";
import { apiKeysAdminApi, type ApiKeyRow } from "@/lib/api-public-keys";
import { ApiKeyUsageChart } from "@/components/api-keys/ApiKeyUsageChart";

export default function ApiKeyDetailPage(props: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(props.params);
  const [row, setRow] = React.useState<ApiKeyRow | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    apiKeysAdminApi
      .get(id)
      .then(setRow)
      .catch((e) => setErr(e?.message ?? "加载失败"));
  }, [id]);

  if (err)
    return (
      <div className="container mx-auto p-6 max-w-3xl text-red-600">
        错误: {err}
        <Link
          href="/mothership/admin/api-keys"
          className="block mt-2 text-blue-600"
        >
          返回列表
        </Link>
      </div>
    );
  if (!row)
    return <div className="container mx-auto p-6 text-slate-500">加载中...</div>;

  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 max-w-3xl space-y-4">
        <Link
          href="/mothership/admin/api-keys"
          className="text-xs text-blue-600 hover:underline"
        >
          ← 返回列表
        </Link>
        <header className="rounded-lg border bg-white p-4">
          <h1 className="text-xl font-semibold">{row.name}</h1>
          <div className="mt-2 grid grid-cols-2 gap-3 text-xs">
            <div>
              <span className="text-slate-500">Key 前缀</span>
              <div className="font-mono">{row.key_prefix}…</div>
            </div>
            <div>
              <span className="text-slate-500">状态</span>
              <div>
                {row.revoked_at
                  ? `已撤销 @ ${new Date(row.revoked_at).toLocaleString()}`
                  : "启用"}
              </div>
            </div>
            <div>
              <span className="text-slate-500">速率上限</span>
              <div>{row.rate_limit_per_min} 请求/分钟</div>
            </div>
            <div>
              <span className="text-slate-500">过期时间</span>
              <div>
                {row.expires_at
                  ? new Date(row.expires_at).toLocaleString()
                  : "永不过期"}
              </div>
            </div>
            <div className="col-span-2">
              <span className="text-slate-500">Scopes</span>
              <div className="mt-1 flex flex-wrap gap-1">
                {row.scopes.map((s) => (
                  <span
                    key={s}
                    className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-[11px] font-mono"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </header>
        <ApiKeyUsageChart apiKeyId={row.id} />
        <div className="rounded-lg border bg-amber-50 border-amber-200 p-3 text-xs text-amber-900">
          为安全起见,API Key 明文只在创建瞬间返回一次,这里只能看到前缀。
          如需轮换,请撤销后新建。
        </div>
      </div>)</ErrorBoundary>
  );
}
