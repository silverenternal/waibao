"use client";

/**
 * v6.0 T2105 — Live execution monitor.
 *
 * Renders the status + per-step trace of a workflow run. The monitor
 * subscribes to `workflow.node.completed` and `workflow.node.failed`
 * SSE events so the UI updates as the engine progresses.
 */

import * as React from "react";

import type { RunRecord } from "./types";

interface WorkflowRunMonitorProps {
  run: RunRecord | null;
  onResume?: (decision: string) => void;
  onCancel?: () => void;
}

const STATUS_COLOR: Record<string, string> = {
  pending: "bg-slate-200 text-slate-800",
  running: "bg-amber-100 text-amber-800",
  paused: "bg-purple-100 text-purple-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
  cancelled: "bg-slate-300 text-slate-700",
};

export function WorkflowRunMonitor(props: WorkflowRunMonitorProps): JSX.Element {
  const [decision, setDecision] = React.useState("approved");

  if (!props.run) {
    return (
      <div className="rounded border border-dashed border-slate-300 bg-slate-50 p-3 text-xs text-slate-500">
        Run a workflow to see live execution trace here.
      </div>
    );
  }

  const r = props.run;
  const statusClass = STATUS_COLOR[r.status] ?? STATUS_COLOR.pending;
  const executed = r.nodes_executed || [];

  return (
    <div className="rounded border bg-white p-3 text-sm shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <span className={"rounded px-2 py-0.5 text-xs font-bold uppercase " +
                           statusClass}>
            {r.status}
          </span>
          <span className="ml-2 text-xs text-slate-500">
            run {r.run_id.slice(0, 8)}
          </span>
        </div>
        <div className="flex gap-1">
          {r.status === "paused" && props.onResume ? (
            <>
              <input
                value={decision}
                onChange={(e) => setDecision(e.target.value)}
                className="rounded border border-slate-300 px-1 text-xs"
              />
              <button
                onClick={() => props.onResume?.(decision)}
                className="rounded bg-emerald-600 px-2 py-0.5 text-xs font-bold text-white"
              >
                Resume
              </button>
            </>
          ) : null}
          {(r.status === "running" || r.status === "paused") &&
           props.onCancel ? (
            <button
              onClick={() => props.onCancel?.()}
              className="rounded bg-rose-600 px-2 py-0.5 text-xs font-bold text-white"
            >
              Cancel
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-2 text-xs text-slate-500">
        Started {r.started_at ?? "—"} ·
        Finished {r.finished_at ?? "—"}
      </div>

      <div className="mt-2">
        <h4 className="mb-1 text-xs font-semibold text-slate-600">
          Executed nodes ({executed.length})
        </h4>
        <ol className="flex flex-wrap gap-1">
          {executed.map((id) => (
            <li
              key={id}
              className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
            >
              {id}
            </li>
          ))}
          {executed.length === 0 ? (
            <li className="text-xs italic text-slate-400">none yet</li>
          ) : null}
        </ol>
      </div>

      {r.error ? (
        <div className="mt-2 rounded bg-rose-50 p-2 text-xs text-rose-700">
          <b>Error:</b> {r.error}
        </div>
      ) : null}

      {r.output ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-semibold text-slate-600">
            Output
          </summary>
          <pre className="mt-1 max-h-40 overflow-auto rounded bg-slate-50 p-2 text-[11px]">
            {JSON.stringify(r.output, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}