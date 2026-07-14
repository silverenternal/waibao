"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v6.0 T2105 — Workflow editor page (per-workflow route).
 *
 * Layout:
 *   [NodePalette] | [WorkflowCanvas] | [NodeConfig]
 *
 * Top toolbar: save / validate / run / load-template.
 * Bottom: live execution monitor.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";

import { NodePalette } from "@/components/workflow/NodePalette";
import {
  CanvasEdge,
  CanvasNode,
  WorkflowCanvas,
} from "@/components/workflow/WorkflowCanvas";
import { NodeConfig } from "@/components/workflow/NodeConfig";
import { WorkflowRunMonitor } from "@/components/workflow/WorkflowRunMonitor";
import {
  RunRecord,
  TemplateSummary,
  WorkflowDefinition,
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

function ensurePositions(def: WorkflowDefinition): CanvasNode[] {
  return (def.nodes || []).map((n, idx) => ({
    ...n,
    position: (n as unknown as CanvasNode).position ?? {
      x: 60 + (idx % 4) * 240,
      y: 60 + Math.floor(idx / 4) * 130,
    },
  }));
}

export default function WorkflowEditorPage(): React.JSX.Element {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const workflowId = Number(params.id);

  const [record, setRecord] = React.useState<WorkflowRecord | null>(null);
  const [nodes, setNodes] = React.useState<CanvasNode[]>([]);
  const [edges, setEdges] = React.useState<CanvasEdge[]>([]);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [definitionName, setDefinitionName] = React.useState("workflow");
  const [run, setRun] = React.useState<RunRecord | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [validation, setValidation] =
    React.useState<{ valid: boolean; errors: string[];
                     warnings: string[] } | null>(null);
  const [saving, setSaving] = React.useState(false);

  const loadWorkflow = React.useCallback(async () => {
    try {
      const wf = await api<WorkflowRecord>(`/api/workflows/${workflowId}`);
      setRecord(wf);
      setDefinitionName(wf.name);
      const def = wf.definition || {} as WorkflowDefinition;
      setNodes(ensurePositions(def));
      setEdges((def.edges || []) as CanvasEdge[]);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [workflowId]);

  React.useEffect(() => {
    if (!Number.isNaN(workflowId) && workflowId > 0) {
      void loadWorkflow();
    }
  }, [workflowId, loadWorkflow]);

  const buildDefinition = (): WorkflowDefinition => ({
    name: definitionName,
    version: record?.version || "1.0",
    description: record?.description || "",
    start_node: nodes[0]?.id ?? null,
    variables: record?.definition?.variables || {},
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.type,
      config: n.config,
      next_nodes: edges.filter((e) => e.from_node === n.id)
                       .map((e) => e.to_node),
    })),
    edges: edges.map((e) => ({
      from_node: e.from_node,
      to_node: e.to_node,
      condition: e.condition ?? null,
    })),
  });

  const onSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const body = {
        name: definitionName,
        description: record?.description || "",
        version: record?.version || "1.0",
        category: record?.category || null,
        is_template: record?.is_template || false,
        created_by: record?.created_by || null,
        nodes: nodes.map((n) => ({
          id: n.id, type: n.type, config: n.config,
          next_nodes: edges.filter((e) => e.from_node === n.id)
                           .map((e) => e.to_node),
        })),
        edges: edges.map((e) => ({
          from_node: e.from_node, to_node: e.to_node,
          condition: e.condition ?? null,
        })),
        start_node: nodes[0]?.id ?? null,
        variables: record?.definition?.variables || {},
      };
      const saved = await api<WorkflowRecord>(`/api/workflows`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setRecord(saved);
      setValidation(null);
      router.push(`/admin/workflows/${saved.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const onValidate = async () => {
    setError(null);
    try {
      const result = await api<{ valid: boolean; errors: string[];
                                  warnings: string[] }>(
        `/api/workflows/${workflowId}/validate`,
        { method: "POST",
          body: JSON.stringify({
            name: definitionName,
            nodes: nodes.map((n) => ({
              id: n.id, type: n.type, config: n.config,
              next_nodes: [],
            })),
            edges: edges.map((e) => ({
              from_node: e.from_node, to_node: e.to_node,
              condition: e.condition ?? null,
            })),
            start_node: nodes[0]?.id ?? null,
          }) },
      );
      setValidation(result);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const onRun = async () => {
    setError(null);
    try {
      const r = await api<RunRecord>(
        `/api/workflows/${workflowId}/run`,
        { method: "POST",
          body: JSON.stringify({ input: { demo: true } }) },
      );
      setRun(r);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const onResume = async (decision: string) => {
    if (!run) return;
    setError(null);
    try {
      const r = await api<RunRecord>(`/api/workflows/runs/${run.run_id}/resume`,
        { method: "POST",
          body: JSON.stringify({ decision }) });
      setRun(r);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const onCancel = async () => {
    if (!run) return;
    try {
      const r = await api<RunRecord>(`/api/workflows/runs/${run.run_id}/cancel`,
        { method: "POST" });
      setRun(r);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const loadTemplate = async (name: string) => {
    try {
      const tpl = await api<TemplateSummary>(
        `/api/workflows/templates/${name}`);
      setDefinitionName(tpl.name);
      setNodes(ensurePositions(tpl.definition));
      setEdges((tpl.definition.edges || []) as CanvasEdge[]);
      setRun(null);
      setValidation(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const selectedNode = nodes.find((n) => n.id === selectedId) || null;
  const activeSet = React.useMemo(
    () => new Set(run?.nodes_executed || []),
    [run?.nodes_executed],
  );

  return (
    <ErrorBoundary>(<div className="flex h-screen flex-col bg-slate-50">
        <header className="flex items-center justify-between border-b bg-white px-4 py-2">
          <div className="flex items-center gap-2">
            <button onClick={() => router.push("/admin/workflows")}
                    className="text-sm text-slate-500 hover:underline">
              ← Workflows
            </button>
            <h1 className="text-base font-semibold text-slate-800">
              {record?.name || `Workflow #${workflowId}`}
            </h1>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <select
              value=""
              onChange={(e) => e.target.value &&
                       void loadTemplate(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1 text-xs"
            >
              <option value="">Load template…</option>
              {["onboarding", "interview_pipeline", "resume_scoring",
                "bias_review", "ticket_sla"].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
            <button onClick={onValidate}
                    className="rounded bg-slate-200 px-3 py-1 text-xs font-bold hover:bg-slate-300">
              Validate
            </button>
            <button onClick={onRun}
                    data-testid="run-workflow"
                    className="rounded bg-emerald-600 px-3 py-1 text-xs font-bold text-white hover:bg-emerald-700">
              ▶ Run
            </button>
            <button onClick={onSave} disabled={saving}
                    className="rounded bg-indigo-600 px-3 py-1 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-50">
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </header>
        {error ? (
          <div className="bg-rose-100 px-4 py-2 text-xs text-rose-700">
            {error}
          </div>
        ) : null}
        {validation ? (
          <div className={
            (validation.valid ? "bg-emerald-50 text-emerald-700"
                               : "bg-rose-50 text-rose-700") +
            " px-4 py-2 text-xs"
          }>
            {validation.valid
              ? `Validation passed (${validation.warnings.length} warnings)`
              : `Validation failed: ${validation.errors.join("; ")}`}
          </div>
        ) : null}
        <div className="flex flex-1 overflow-hidden">
          <NodePalette />
          <main className="flex-1">
            <WorkflowCanvas
              nodes={nodes}
              edges={edges}
              selectedNodeId={selectedId}
              onSelect={setSelectedId}
              onAddNode={(n, position) => setNodes([
                ...nodes,
                { ...n, position } as CanvasNode,
              ])}
              onMoveNode={(id, position) => setNodes(
                nodes.map((n) => n.id === id ? { ...n, position } : n))}
              onConnect={(from, to, condition) => setEdges([
                ...edges, { from_node: from, to_node: to, condition }])}
              onDeleteNode={(id) => {
                setNodes(nodes.filter((n) => n.id !== id));
                setEdges(edges.filter((e) =>
                  e.from_node !== id && e.to_node !== id));
                if (selectedId === id) setSelectedId(null);
              }}
              activeNodeIds={activeSet}
            />
          </main>
          <NodeConfig
            node={selectedNode}
            onChange={(next) => setNodes(
              nodes.map((n) => n.id === selectedId ? { ...n, ...next,
                position: n.position } : n))}
            onClose={() => setSelectedId(null)}
          />
        </div>
        <footer className="border-t bg-white p-3">
          <WorkflowRunMonitor
            run={run}
            onResume={onResume}
            onCancel={onCancel}
          />
        </footer>
      </div>)</ErrorBoundary>
  );
}