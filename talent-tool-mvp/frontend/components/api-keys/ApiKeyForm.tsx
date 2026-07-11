"use client";

import * as React from "react";
import {
  apiKeysAdminApi,
  type ApiKeyCreated,
  type ApiKeyScope,
} from "@/lib/api-public-keys";
import { ScopeMultiSelect } from "./ScopeMultiSelect";

interface Props {
  onCancel: () => void;
  onSaved: (created: ApiKeyCreated) => void;
}

/**
 * 创建 API Key 表单 (T803).
 *
 * 关键: 返回的 plaintext 仅展示一次,关闭后无法再找回.
 */
export function ApiKeyForm({ onCancel, onSaved }: Props) {
  const [name, setName] = React.useState("");
  const [scopes, setScopes] = React.useState<ApiKeyScope[]>([
    "candidates:read",
  ]);
  const [rate, setRate] = React.useState(60);
  const [expires, setExpires] = React.useState<string>("");
  const [busy, setBusy] = React.useState(false);
  const [created, setCreated] = React.useState<ApiKeyCreated | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!name.trim()) {
      setErr("请填写 Key 名称");
      return;
    }
    if (scopes.length === 0) {
      setErr("至少选择一个 scope");
      return;
    }
    setBusy(true);
    try {
      const c = await apiKeysAdminApi.create({
        name: name.trim(),
        scopes,
        rate_limit_per_min: rate,
        expires_at: expires ? new Date(expires).toISOString() : null,
      });
      setCreated(c);
      onSaved(c);
    } catch (e: any) {
      setErr(e?.message ?? "创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.plaintext);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  }

  if (created) {
    return (
      <div className="rounded-lg border-2 border-emerald-200 bg-emerald-50 p-5">
        <h3 className="font-semibold text-emerald-900 mb-2">
          Key 已创建 - 立即保存明文
        </h3>
        <p className="text-xs text-emerald-800 mb-3">
          明文只会展示这一次。请立刻复制并妥善保管。
        </p>
        <div className="bg-white rounded p-3 flex items-center gap-2">
          <code className="flex-1 font-mono text-sm break-all select-all">
            {created.plaintext}
          </code>
          <button
            type="button"
            onClick={copy}
            className="px-3 py-1.5 bg-emerald-600 text-white text-xs rounded hover:bg-emerald-700"
          >
            {copied ? "已复制" : "复制"}
          </button>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 bg-slate-700 text-white text-xs rounded hover:bg-slate-800"
          >
            我已保存
          </button>
        </div>
      </div>
    );
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-lg border bg-white p-5 space-y-4"
    >
      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">
          Key 名称
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="例如:Production CRM"
          className="w-full rounded border-slate-300 border px-3 py-2 text-sm"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">
            每分钟速率上限
          </label>
          <input
            type="number"
            min={1}
            max={10_000}
            value={rate}
            onChange={(e) => setRate(Number(e.target.value) || 60)}
            className="w-full rounded border-slate-300 border px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">
            过期时间 (可选)
          </label>
          <input
            type="datetime-local"
            value={expires}
            onChange={(e) => setExpires(e.target.value)}
            className="w-full rounded border-slate-300 border px-3 py-2 text-sm"
          />
        </div>
      </div>

      <ScopeMultiSelect value={scopes} onChange={setScopes} />

      {err && (
        <div className="rounded bg-red-50 border border-red-200 p-2 text-xs text-red-700">
          {err}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 border rounded text-xs hover:bg-slate-50"
        >
          取消
        </button>
        <button
          type="submit"
          disabled={busy}
          className="px-3 py-1.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? "创建中..." : "创建 Key"}
        </button>
      </div>
    </form>
  );
}
