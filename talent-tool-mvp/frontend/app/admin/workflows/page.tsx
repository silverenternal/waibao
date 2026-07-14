"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v6.0 T2105 — Admin / Workflows page (index).
 *
 * Two columns:
 *   1. Built-in templates (read-only) — one click to create a new
 *      workflow from a template
 *   2. Custom workflows (CRUD) — list, edit, delete, run
 */

import * as React from "react";
import { useRouter } from "next/navigation";

import {
  TemplateSummary,
  WorkflowRecord,
} from "@/components/workflow/types";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    credentials: "include",
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  if (r.status === 204) return null as unknown as T;
  return r.json();
}

export default function WorkflowsAdminPage(): React.JSX.Element {
  const router = useRouter();
  const [workflows, setWorkflows] = React.useState<WorkflowRecord[]>([]);
  const [templates, setTemplates] = React.useState<TemplateSummary[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [newName, setNewName] = React.useState("");

  const reload = React.useCallback(async () => {
    try {
      const [wfs, tpls] = await Promise.all([
        api<WorkflowRecord[]>(`/api/workflows`),
        api<TemplateSummary[]>(`/api/workflows/templates`),
      ]);
      setWorkflows(wfs || []);
      setTemplates(tpls || []);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  React.useEffect(() => {
    void reload();
  }, [reload]);

  const createBlank = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await api<WorkflowRecord>(`/api/workflows`, {
        method: "POST",
        body: JSON.stringify({
          name: newName || `workflow_${Date.now()}`,
          description: "",
          nodes: [
            { id: "trigger", type: "trigger",
              config: { event: "demo.event" }, next_nodes: [] },
            { id: "end", type: "delay",
              config: { seconds: 0 }, next_nodes: [] },
          ],
          edges: [{ from_node: "trigger", to_node: "end",
                    condition: null }],
          start_node: "trigger",
          variables: {},
        }),
      });
      router.push(`/admin/workflows/${created.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const cloneFromTemplate = async (tpl: TemplateSummary) => {
    setBusy(true);
    setError(null);
    try {
      const def = tpl.definition;
      const created = await api<WorkflowRecord>(`/api/workflows`, {
        method: "POST",
        body: JSON.stringify({
          name: `${tpl.name}_${Date.now().toString(36)}`,
          description: tpl.description,
          nodes: def.nodes,
          edges: def.edges,
          start_node: def.start_node,
          variables: def.variables || {},
        }),
      });
      router.push(`/admin/workflows/${created.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const deleteWorkflow = async (id: number) => {
    if (!window.confirm(`Delete workflow #${id}?`)) return;
    try {
      await api(`/api/workflows/${id}`, { method: "DELETE" });
      await reload();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-6xl space-y-6 p-6">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-slate-800">
            Agent Composition
          </h1>
          <div className="flex items-center gap-2">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="new workflow name"
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
            <button
              onClick={createBlank} disabled={busy}
              data-testid="new-workflow"
              className="rounded bg-indigo-600 px-3 py-1 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              + New workflow
            </button>
          </div>
        </header>
        {error ? (
          <div className="rounded bg-rose-100 p-2 text-sm text-rose-700">
            {error}
          </div>
        ) : null}
        <section>
          <h2 className="mb-2 text-lg font-semibold text-slate-700">
            Built-in templates
          </h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {templates.map((tpl) => (
              <article key={tpl.name}
                       className="rounded border bg-white p-3 shadow-sm">
                <header className="flex items-center justify-between">
                  <h3 className="font-semibold text-slate-800">{tpl.name}</h3>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                    v{tpl.version}
                  </span>
                </header>
                <p className="mt-1 line-clamp-3 text-xs text-slate-500">
                  {tpl.description}
                </p>
                <dl className="mt-2 grid grid-cols-2 gap-1 text-xs text-slate-500">
                  <div>nodes: {tpl.node_count}</div>
                  <div>edges: {tpl.edge_count}</div>
                  <div>start: {tpl.start_node || "—"}</div>
                </dl>
                <button
                  onClick={() => cloneFromTemplate(tpl)}
                  disabled={busy}
                  data-testid={`clone-${tpl.name}`}
                  className="mt-3 w-full rounded bg-slate-800 px-3 py-1 text-xs font-bold text-white hover:bg-slate-900 disabled:opacity-50"
                >
                  Use template
                </button>
              </article>
            ))}
          </div>
        </section>
        <section>
          <h2 className="mb-2 text-lg font-semibold text-slate-700">
            Custom workflows
          </h2>
          {workflows.length === 0 ? (
            <p className="rounded border border-dashed border-slate-300 p-4 text-sm text-slate-500">
              No workflows yet — create one from a template or blank.
            </p>
          ) : (
            <table className="w-full rounded border bg-white text-sm shadow-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="p-2">#</th>
                  <th className="p-2">Name</th>
                  <th className="p-2">Description</th>
                  <th className="p-2">Updated</th>
                  <th className="p-2"></th>
                </tr>
              </thead>
              <tbody>
                {workflows.map((wf) => (
                  <tr key={wf.id} className="border-t">
                    <td className="p-2 text-slate-500">{wf.id}</td>
                    <td className="p-2 font-medium text-slate-800">
                      {wf.name}
                    </td>
                    <td className="p-2 text-slate-500">
                      {wf.description || "—"}
                    </td>
                    <td className="p-2 text-slate-400">
                      {wf.updated_at
                        ? new Date(wf.updated_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="space-x-2 p-2 text-right">
                      <button
                        onClick={() => router.push(
                          `/admin/workflows/${wf.id}`)}
                        className="rounded bg-indigo-600 px-2 py-0.5 text-xs font-bold text-white hover:bg-indigo-700"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => deleteWorkflow(wf.id)}
                        className="rounded bg-rose-100 px-2 py-0.5 text-xs font-bold text-rose-700 hover:bg-rose-200"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>)</ErrorBoundary>
  );
}