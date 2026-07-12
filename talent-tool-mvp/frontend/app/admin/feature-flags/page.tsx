"use client";

/**
 * v6.0 T2103 — Admin / Feature Flags page.
 *
 * Layout:
 *   - Header (title + "new flag" form)
 *   - Grid of FlagCard (one per flag)
 *   - Footer audit-log preview
 *
 * Live refresh on `feature_flag.changed` from the EventBus SSE stream.
 */

import * as React from "react";
import { FlagCard, FlagOverride, FlagRecord } from "@/components/feature-flags/FlagCard";
import { useEventBus } from "@/hooks/use-event";
import { invalidateFeatureFlagCache } from "@/hooks/use-feature-flag";

interface AuditEntry {
  id: number;
  flag_name: string;
  action: string;
  actor?: string | null;
  created_at: string;
}

async function api(path: string, init?: RequestInit): Promise<any> {
  const r = await fetch(path, {
    credentials: "include",
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  if (r.status === 204) return null;
  return r.json();
}

export default function FeatureFlagsAdminPage(): JSX.Element {
  const [flags, setFlags] = React.useState<FlagRecord[]>([]);
  const [overrides, setOverrides] = React.useState<Record<string, FlagOverride[]>>({});
  const [audit, setAudit] = React.useState<AuditEntry[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const [savingName, setSavingName] = React.useState<string | null>(null);
  const [newName, setNewName] = React.useState("");
  const [newDesc, setNewDesc] = React.useState("");

  const bus = useEventBus?.();

  const reload = React.useCallback(async () => {
    try {
      const [list, auditRows] = await Promise.all([
        api("/api/admin/feature-flags"),
        api("/api/admin/feature-flags/audit?limit=50"),
      ]);
      setFlags(list || []);
      setAudit(auditRows || []);
      // Fetch overrides per flag in parallel
      const pairs = await Promise.all(
        (list || []).map(async (f: FlagRecord) => {
          try {
            const detail = await api(
              `/api/admin/feature-flags/${encodeURIComponent(f.name)}`
            );
            return [f.name, detail.overrides || []] as const;
          } catch {
            return [f.name, []] as const;
          }
        })
      );
      setOverrides(Object.fromEntries(pairs));
    } catch (e: any) {
      setError(String(e?.message || e));
    }
  }, []);

  React.useEffect(() => {
    reload();
  }, [reload]);

  // Live updates — bus may be undefined in tests.
  React.useEffect(() => {
    if (!bus) return;
    const unsub = bus.subscribe?.("feature_flag.changed", () => {
      invalidateFeatureFlagCache();
      reload();
    });
    return () => {
      try {
        unsub?.();
      } catch {
        /* ignore */
      }
    };
  }, [bus, reload]);

  const handleSave = async (name: string, patch: Partial<FlagRecord>) => {
    setSavingName(name);
    try {
      await api(`/api/admin/feature-flags/${encodeURIComponent(name)}`, {
        method: "PUT",
        body: JSON.stringify({ name, ...patch }),
      });
      invalidateFeatureFlagCache(name);
      await reload();
    } finally {
      setSavingName(null);
    }
  };

  const handleAddOverride = async (name: string, payload: Omit<FlagOverride, "id" | "flag_name">) => {
    await api(`/api/admin/feature-flags/${encodeURIComponent(name)}/override`, {
      method: "POST",
      body: JSON.stringify({ flag_name: name, ...payload }),
    });
    invalidateFeatureFlagCache(name);
    await reload();
  };

  const handleRemoveOverride = async (name: string, ov: FlagOverride) => {
    const params = new URLSearchParams();
    if (ov.user_id) params.set("user_id", ov.user_id);
    if (ov.org_id) params.set("org_id", ov.org_id);
    await api(
      `/api/admin/feature-flags/${encodeURIComponent(name)}/override?${params.toString()}`,
      { method: "DELETE" }
    );
    invalidateFeatureFlagCache(name);
    await reload();
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete flag ${name}?`)) return;
    await api(`/api/admin/feature-flags/${encodeURIComponent(name)}`, { method: "DELETE" });
    invalidateFeatureFlagCache(name);
    await reload();
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    await api(`/api/admin/feature-flags/${encodeURIComponent(newName.trim())}`, {
      method: "PUT",
      body: JSON.stringify({
        name: newName.trim(),
        description: newDesc,
        rollout_percent: 0,
        enabled: false,
      }),
    });
    setNewName("");
    setNewDesc("");
    invalidateFeatureFlagCache();
    await reload();
  };

  return (
    <main className="mx-auto max-w-6xl p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Feature Flags</h1>
        <p className="mt-1 text-sm text-slate-500">
          v6.0 T2103 — manage rollout, overrides and audit log.
        </p>
      </header>

      <section className="mb-6 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">新建 flag</h2>
        <div className="flex flex-col gap-2 md:flex-row">
          <input
            type="text"
            placeholder="flag name (snake_case)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="flex-1 rounded-md border border-slate-200 px-3 py-1.5 text-sm"
          />
          <input
            type="text"
            placeholder="description"
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            className="flex-1 rounded-md border border-slate-200 px-3 py-1.5 text-sm"
          />
          <button
            type="button"
            disabled={!newName.trim()}
            onClick={handleCreate}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            创建
          </button>
        </div>
      </section>

      {error && (
        <div className="mb-4 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {error}
        </div>
      )}

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {flags.map((f) => (
          <FlagCard
            key={f.name}
            flag={f}
            overrides={overrides[f.name] || []}
            saving={savingName === f.name}
            onSave={(patch) => handleSave(f.name, patch)}
            onAddOverride={(p) => handleAddOverride(f.name, p)}
            onRemoveOverride={(ov) => handleRemoveOverride(f.name, ov)}
            onDelete={() => handleDelete(f.name)}
          />
        ))}
        {flags.length === 0 && (
          <div className="col-span-full rounded-md bg-slate-50 p-6 text-center text-sm text-slate-500">
            还没有 flag — 在上方新建一个。
          </div>
        )}
      </section>

      <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">Audit log</h2>
        {audit.length === 0 ? (
          <p className="text-xs text-slate-500">暂无记录</p>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="py-1">time</th>
                <th className="py-1">flag</th>
                <th className="py-1">action</th>
                <th className="py-1">actor</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((row) => (
                <tr key={row.id} className="border-t border-slate-100">
                  <td className="py-1 text-slate-500">
                    {new Date(row.created_at).toLocaleString()}
                  </td>
                  <td className="py-1 font-mono text-slate-700">{row.flag_name}</td>
                  <td className="py-1 text-slate-700">{row.action}</td>
                  <td className="py-1 text-slate-500">{row.actor || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}