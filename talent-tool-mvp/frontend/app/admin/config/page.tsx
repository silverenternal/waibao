"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Admin / Config Center (v6.0 T2102)
 *
 * Visualises all (scope, key) configuration rows from
 *   GET /api/admin/config
 *
 * Live-refreshes on `config.changed` events from the EventBus SSE stream.
 *
 * Panels:
 *   - Sidebar tree (scope → key) — click selects a row
 *   - ConfigEditor pane — value, value_type, description, comment, save
 *   - ConfigHistory drawer — version diff + rollback
 */

import * as React from "react";
import { useEventBus } from "@/hooks/use-event";

interface ConfigRecord {
  id?: number;
  scope: string;
  key: string;
  value: any;
  version: number;
  value_type: string;
  description?: string | null;
  updated_by?: string | null;
  updated_at?: string | null;
}

const SCOPES = ["system", "org", "agent", "feature"];

async function apiGet(path: string): Promise<any> {
  const r = await fetch(path, { credentials: "include" });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

async function apiPut(path: string, body: any): Promise<any> {
  const r = await fetch(path, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

async function apiPost(path: string, body: any): Promise<any> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

export default function AdminConfigCenterPage() {
  const [items, setItems] = React.useState<ConfigRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [scopeFilter, setScopeFilter] = React.useState<string | "">("");
  const [selected, setSelected] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    try {
      setLoading(true);
      const data = (await apiGet(
        scopeFilter ? `/api/admin/config?scope=${scopeFilter}` : "/api/admin/config",
      )) as ConfigRecord[];
      setItems(data);
      setError(null);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }, [scopeFilter]);

  React.useEffect(() => {
    load();
  }, [load]);

  // Live-refresh on config.changed events
  const { connected } = useEventBus(["config.changed"]);
  React.useEffect(() => {
    if (connected) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected]);

  // Group by scope
  const grouped = React.useMemo(() => {
    const out: Record<string, ConfigRecord[]> = {};
    for (const it of items) {
      if (!out[it.scope]) out[it.scope] = [];
      out[it.scope].push(it);
    }
    return out;
  }, [items]);

  const selectedRecord = items.find((i) => `${i.scope}/${i.key}` === selected);

  return (
    <ErrorBoundary>(<div className="container mx-auto p-6">
        <header className="mb-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Config Center</h1>
            <p className="text-sm text-slate-500">
              Live, version-controlled runtime configuration.{" "}
              {connected ? (
                <span className="text-emerald-500">● SSE live</span>
              ) : (
                <span className="text-slate-400">○ SSE offline</span>
              )}
            </p>
          </div>
          <div>
            <select
              value={scopeFilter}
              onChange={(e) => setScopeFilter(e.target.value)}
              className="rounded border px-2 py-1 text-sm"
            >
              <option value="">All scopes</option>
              {SCOPES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </header>
        {error && (
          <div className="mb-4 rounded border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </div>
        )}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[280px_1fr]">
          <aside className="rounded border p-3">
            {loading ? (
              <p className="text-sm text-slate-400">Loading…</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {SCOPES.map((scope) => {
                  const rows = grouped[scope] ?? [];
                  if (rows.length === 0) return null;
                  return (
                    <li key={scope}>
                      <p className="font-mono text-xs uppercase text-slate-500">
                        {scope}
                      </p>
                      <ul className="mt-1 space-y-1">
                        {rows.map((r) => (
                          <li key={`${r.scope}/${r.key}`}>
                            <button
                              type="button"
                              onClick={() => setSelected(`${r.scope}/${r.key}`)}
                              className={
                                "w-full rounded px-2 py-1 text-left hover:bg-slate-100 " +
                                (selected === `${r.scope}/${r.key}` ? "bg-slate-200" : "")
                              }
                            >
                              {r.key}
                              <span className="ml-1 text-xs text-slate-400">
                                v{r.version}
                              </span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    </li>
                  );
                })}
              </ul>
            )}
          </aside>

          <main>
            {selectedRecord ? (
              <ConfigEditor record={selectedRecord} onSaved={load} />
            ) : (
              <div className="rounded border p-6 text-sm text-slate-400">
                Select a key on the left to edit.
              </div>
            )}
          </main>
        </div>
      </div>)</ErrorBoundary>
  );
}

interface ConfigEditorProps {
  record: ConfigRecord;
  onSaved: () => void;
}

function ConfigEditor({ record, onSaved }: ConfigEditorProps) {
  const [raw, setRaw] = React.useState(() => JSON.stringify(record.value, null, 2));
  const [valueType, setValueType] = React.useState(record.value_type);
  const [description, setDescription] = React.useState(record.description ?? "");
  const [comment, setComment] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [history, setHistory] = React.useState<any[]>([]);

  React.useEffect(() => {
    setRaw(JSON.stringify(record.value, null, 2));
    setValueType(record.value_type);
    setDescription(record.description ?? "");
    setComment("");
    setError(null);
    apiGet(`/api/admin/config/${record.scope}/${record.key}/history`)
      .then(setHistory)
      .catch(() => setHistory([]));
  }, [record.scope, record.key, record.version]);

  const onSave = async () => {
    setSaving(true);
    setError(null);
    let parsed: any;
    try {
      parsed = valueType === "string"
        ? raw
        : valueType === "number"
        ? Number(raw)
        : valueType === "boolean"
        ? raw === "true"
        : valueType === "array"
        ? (typeof raw === "string" ? JSON.parse(raw) : raw)
        : (typeof raw === "string" ? JSON.parse(raw) : raw);
    } catch (e: any) {
      setError(`Could not parse value: ${e.message}`);
      setSaving(false);
      return;
    }
    try {
      await apiPut(`/api/admin/config/${record.scope}/${record.key}`, {
        value: parsed,
        value_type: valueType,
        description: description || null,
        changed_by: "admin",
        comment: comment || null,
      });
      onSaved();
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setSaving(false);
    }
  };

  const rollback = async (toVersion: number) => {
    setSaving(true);
    setError(null);
    try {
      await apiPost(`/api/admin/config/${record.scope}/${record.key}/rollback`, {
        to_version: toVersion,
        changed_by: "admin",
      });
      onSaved();
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded border p-4">
        <header className="mb-3">
          <h2 className="text-lg font-semibold">
            {record.scope}.<span className="text-slate-500">{record.key}</span>
          </h2>
          <p className="text-xs text-slate-500">
            v{record.version} • last edited by {record.updated_by ?? "—"} •{" "}
            {record.updated_at ? new Date(record.updated_at).toLocaleString() : ""}
          </p>
        </header>

        <div className="mb-2">
          <label className="text-xs uppercase text-slate-500">Value Type</label>
          <select
            value={valueType}
            onChange={(e) => setValueType(e.target.value)}
            className="ml-2 rounded border px-2 py-0.5 text-sm"
          >
            <option value="json">json</option>
            <option value="string">string</option>
            <option value="number">number</option>
            <option value="boolean">boolean</option>
            <option value="array">array</option>
          </select>
        </div>

        <label className="mb-1 block text-xs uppercase text-slate-500">Value</label>
        <textarea
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          className="block w-full rounded border bg-slate-50 p-2 font-mono text-sm"
          rows={12}
        />

        <label className="mb-1 mt-3 block text-xs uppercase text-slate-500">Description</label>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="block w-full rounded border px-2 py-1 text-sm"
        />

        <label className="mb-1 mt-3 block text-xs uppercase text-slate-500">Change comment</label>
        <input
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Why are you changing this?"
          className="block w-full rounded border px-2 py-1 text-sm"
        />

        {error && (
          <p className="mt-2 rounded bg-rose-50 px-2 py-1 text-sm text-rose-700">
            {error}
          </p>
        )}

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            disabled={saving}
            onClick={onSave}
            className="rounded bg-emerald-600 px-3 py-1 text-sm text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      <ConfigHistory scope={record.scope} keyName={record.key} history={history} onRollback={rollback} />
    </div>
  );
}

interface HistoryProps {
  scope: string;
  keyName: string;
  history: any[];
  onRollback: (version: number) => void;
}

function ConfigHistory({ scope, keyName, history, onRollback }: HistoryProps) {
  return (
    <div className="rounded border p-4">
      <h3 className="mb-2 font-semibold">Version History</h3>
      {history.length === 0 ? (
        <p className="text-sm text-slate-400">No history yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-slate-500">
              <th className="p-1">Version</th>
              <th className="p-1">Operation</th>
              <th className="p-1">By</th>
              <th className="p-1">When</th>
              <th className="p-1">Comment</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {history.map((h) => (
              <tr key={h.id} className="border-t">
                <td className="p-1 font-mono">v{h.version}</td>
                <td className="p-1">{h.operation}</td>
                <td className="p-1">{h.changed_by ?? "—"}</td>
                <td className="p-1">
                  {h.changed_at ? new Date(h.changed_at).toLocaleString() : ""}
                </td>
                <td className="p-1">{h.comment ?? ""}</td>
                <td className="p-1 text-right">
                  <button
                    type="button"
                    onClick={() => onRollback(h.version)}
                    className="rounded border px-2 py-0.5 text-xs hover:bg-slate-100"
                  >
                    Rollback
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
