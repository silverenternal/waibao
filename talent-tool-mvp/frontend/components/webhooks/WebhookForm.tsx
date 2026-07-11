"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { WebhookEventPicker } from "./WebhookEventPicker";
import { webhooksApi, type WebhookRow } from "@/lib/api-webhooks";

interface Props {
  initial?: Partial<WebhookRow>;
  onSaved: (wh: WebhookRow) => void;
  onCancel: () => void;
}

export function WebhookForm({ initial, onSaved, onCancel }: Props) {
  const t = useTranslations("admin.webhooks");
  const [name, setName] = React.useState(initial?.name ?? "");
  const [url, setUrl] = React.useState(initial?.url ?? "");
  const [description, setDescription] = React.useState(
    initial?.description ?? "",
  );
  const [events, setEvents] = React.useState<string[]>(initial?.events ?? []);
  const [active, setActive] = React.useState<boolean>(initial?.active ?? true);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const [secret, setSecret] = React.useState<string | null>(
    initial?.secret ?? null,
  );

  const isEdit = Boolean(initial?.id);
  const urlValid = url.startsWith("https://");

  async function save() {
    setErr(null);
    if (!name.trim()) return setErr("name 不能为空");
    if (!urlValid)
      return setErr("URL 必须 https:// 开头");
    if (events.length === 0)
      return setErr("至少订阅一个事件");

    setBusy(true);
    try {
      const body = {
        name,
        url,
        events,
        active,
        description: description || null,
      };
      const saved = isEdit
        ? await webhooksApi.update(initial!.id!, body)
        : await webhooksApi.create(body);
      setSecret(saved.secret ?? null);
      onSaved(saved);
    } catch (e: any) {
      setErr(e?.message ?? "保存失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4 bg-white rounded-lg border p-6">
      <h2 className="text-lg font-semibold">
        {isEdit ? t("edit") : t("create")}
      </h2>

      <label className="block text-sm">
        <span className="text-slate-700">{t("nameLabel")}</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled={busy}
        />
      </label>

      <label className="block text-sm">
        <span className="text-slate-700">{t("urlLabel")}</span>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/hook"
          className={`mt-1 block w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 ${
            url.length === 0
              ? "border-slate-300 focus:ring-blue-500"
              : urlValid
                ? "border-slate-300 focus:ring-blue-500"
                : "border-red-400 focus:ring-red-500"
          }`}
          disabled={busy}
        />
        {url.length > 0 && !urlValid && (
          <span className="text-xs text-red-600 mt-1">
            URL 必须以 https:// 开头(后端强制)
          </span>
        )}
      </label>

      <div>
        <div className="text-sm text-slate-700 mb-2">{t("eventLabel")}</div>
        <WebhookEventPicker
          value={events}
          onChange={setEvents}
          disabled={busy}
        />
      </div>

      <label className="block text-sm">
        <span className="text-slate-700">{t("descriptionLabel")}</span>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled={busy}
        />
      </label>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={active}
          onChange={(e) => setActive(e.target.checked)}
          disabled={busy}
        />
        <span>{t("statusActive")}</span>
      </label>

      {secret && (
        <div className="rounded-md bg-slate-50 border p-3">
          <div className="text-xs text-slate-500">{t("secretLabel")}</div>
          <code className="block text-sm font-mono text-slate-900 break-all">
            {secret}
          </code>
          <div className="text-xs text-amber-600 mt-1">
            保存后只显示一次,请妥善记录
          </div>
        </div>
      )}

      {err && (
        <div className="rounded-md bg-red-50 border border-red-200 p-2 text-sm text-red-700">
          {err}
        </div>
      )}

      <div className="flex gap-2 justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 rounded-md border border-slate-300 text-sm hover:bg-slate-50"
          disabled={busy}
        >
          取消
        </button>
        <button
          type="button"
          onClick={save}
          className="px-4 py-2 rounded-md bg-blue-600 text-white text-sm hover:bg-blue-700 disabled:opacity-50"
          disabled={busy || !urlValid || events.length === 0 || !name.trim()}
        >
          {busy ? "..." : isEdit ? t("save") : t("create")}
        </button>
      </div>
    </div>
  );
}

export default WebhookForm;
