"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import * as React from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { webhooksApi, type WebhookRow } from "@/lib/api-webhooks";
import { WebhookForm } from "@/components/webhooks/WebhookForm";

export default function WebhookDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id;
  const [wh, setWh] = React.useState<WebhookRow | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!id) return;
    webhooksApi
      .get(id)
      .then(setWh)
      .catch((e) => setErr(e?.message ?? "加载失败"));
  }, [id]);

  if (!id) return null;
  if (err) return <div className="p-8 text-red-600">{err}</div>;
  if (!wh) return <div className="p-8 text-slate-500">加载中…</div>;

  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 max-w-3xl">
        <div className="mb-4 text-sm text-slate-500">
          <Link href="/mothership/admin/webhooks" className="hover:underline">
            ← 返回列表
          </Link>
        </div>
        <h1 className="text-2xl font-semibold mb-4">{wh.name}</h1>
        <WebhookForm
          initial={{ ...wh }}
          onSaved={(saved) => {
            setWh(saved);
            router.refresh();
          }}
          onCancel={() => router.push("/mothership/admin/webhooks")}
        />
      </div>)</ErrorBoundary>
  );
}
