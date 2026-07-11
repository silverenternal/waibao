"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { webhooksApi, type WebhookDelivery } from "@/lib/api-webhooks";
import { WebhookDeliveryList } from "@/components/webhooks/WebhookDeliveryList";

export default function WebhookDeliveriesPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [list, setList] = React.useState<WebhookDelivery[] | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  async function load() {
    if (!id) return;
    try {
      setList(await webhooksApi.deliveries(id, 100));
    } catch (e: any) {
      setErr(e?.message ?? "加载失败");
    }
  }

  React.useEffect(() => {
    load();
  }, [id]);

  async function replay() {
    if (!id) return;
    try {
      const r = await webhooksApi.replay(id);
      alert(`已入队 ${r.queued} 条,稍后列表会刷新`);
      await load();
    } catch (e: any) {
      alert(`重发失败: ${e?.message}`);
    }
  }

  if (!id) return null;

  return (
    <div className="container mx-auto p-6 max-w-5xl">
      <div className="mb-4 text-sm text-slate-500">
        <Link
          href="/mothership/admin/webhooks"
          className="hover:underline"
        >
          ← 返回列表
        </Link>
      </div>
      <h1 className="text-2xl font-semibold mb-4">投递历史</h1>
      {err && (
        <div className="mb-4 rounded-md bg-red-50 border border-red-200 p-2 text-sm text-red-700">
          {err}
        </div>
      )}
      {list && (
        <WebhookDeliveryList
          deliveries={list}
          onReplayDeadLetters={replay}
        />
      )}
    </div>
  );
}
