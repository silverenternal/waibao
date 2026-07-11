"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { webhooksApi, type WebhookRow } from "@/lib/api-webhooks";
import { LocaleSwitcher } from "@/components/LocaleSwitcher";
import { WebhookForm } from "@/components/webhooks/WebhookForm";

export default function WebhooksListPage() {
  const t = useTranslations("admin.webhooks");
  const [list, setList] = React.useState<WebhookRow[] | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  async function load() {
    try {
      setList(await webhooksApi.list());
    } catch (e: any) {
      setErr(e?.message ?? "加载失败");
    }
  }

  React.useEffect(() => {
    load();
  }, []);

  async function toggleActive(wh: WebhookRow) {
    setBusyId(wh.id);
    try {
      const updated = await webhooksApi.update(wh.id, { active: !wh.active });
      setList((ls) =>
        ls ? ls.map((x) => (x.id === wh.id ? { ...x, ...updated } : x)) : ls,
      );
    } catch (e: any) {
      setErr(e?.message ?? "更新失败");
    } finally {
      setBusyId(null);
    }
  }

  async function remove(wh: WebhookRow) {
    if (!confirm(`删除 webhook "${wh.name}"?`)) return;
    setBusyId(wh.id);
    try {
      await webhooksApi.remove(wh.id);
      await load();
    } catch (e: any) {
      setErr(e?.message ?? "删除失败");
    } finally {
      setBusyId(null);
    }
  }

  async function testSend(wh: WebhookRow) {
    setBusyId(wh.id);
    try {
      const r = await webhooksApi.test(wh.id, "test.ping", { source: "ui" });
      alert(
        r.ok
          ? `测试发送成功(${r.status_code})\nsignature: ${r.signature.slice(0, 32)}…`
          : `测试失败: ${r.status_code ?? "no response"}\n${r.response_body ?? ""}`,
      );
    } catch (e: any) {
      alert(`测试发送失败: ${e?.message}`);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="container mx-auto p-6 max-w-5xl">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">{t("title")}</h1>
          <p className="text-sm text-slate-500 mt-1">
            订阅业务事件,Webhook 通过 HMAC-SHA256 签名投递到你的接收端
          </p>
        </div>
        <div className="flex items-center gap-3">
          <LocaleSwitcher />
          <button
            onClick={() => setCreating((c) => !c)}
            className="px-3 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700"
          >
            {creating ? "取消新建" : t("create")}
          </button>
        </div>
      </header>

      {err && (
        <div className="mb-4 rounded-md bg-red-50 border border-red-200 p-2 text-sm text-red-700">
          {err}
        </div>
      )}

      {creating && (
        <div className="mb-6">
          <WebhookForm
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
          还没有 webhook。点击「新建 Webhook」开始。
        </div>
      )}

      {list && list.length > 0 && (
        <div className="space-y-3">
          {list.map((wh) => (
            <div
              key={wh.id}
              className="rounded-lg border bg-white p-4 flex items-start justify-between gap-4"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{wh.name}</span>
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      wh.active
                        ? "bg-green-100 text-green-700"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {wh.active ? t("statusActive") : t("statusPaused")}
                  </span>
                </div>
                <div className="text-xs text-slate-500 mt-1 font-mono break-all">
                  {wh.url}
                </div>
                <div className="text-xs text-slate-600 mt-2 flex flex-wrap gap-1">
                  {wh.events.map((e) => (
                    <span
                      key={e}
                      className="px-2 py-0.5 bg-slate-100 text-slate-700 rounded text-[11px] font-mono"
                    >
                      {e}
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex flex-col items-end gap-2">
                <div className="flex gap-2">
                  <Link
                    href={`/mothership/admin/webhooks/${wh.id}`}
                    className="px-2 py-1 text-xs border rounded hover:bg-slate-50"
                  >
                    编辑
                  </Link>
                  <Link
                    href={`/mothership/admin/webhooks/${wh.id}/deliveries`}
                    className="px-2 py-1 text-xs border rounded hover:bg-slate-50"
                  >
                    投递历史
                  </Link>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => testSend(wh)}
                    disabled={busyId === wh.id}
                    className="px-2 py-1 text-xs border rounded text-blue-700 hover:bg-blue-50 disabled:opacity-50"
                  >
                    测试发送
                  </button>
                  <button
                    onClick={() => toggleActive(wh)}
                    disabled={busyId === wh.id}
                    className="px-2 py-1 text-xs border rounded hover:bg-slate-50 disabled:opacity-50"
                  >
                    {wh.active ? "暂停" : "启用"}
                  </button>
                  <button
                    onClick={() => remove(wh)}
                    disabled={busyId === wh.id}
                    className="px-2 py-1 text-xs border rounded text-red-600 hover:bg-red-50 disabled:opacity-50"
                  >
                    删除
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
