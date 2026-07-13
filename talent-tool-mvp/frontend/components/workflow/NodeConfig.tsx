"use client";

/**
 * v6.0 T2105 — Node config side panel.
 *
 * Lets the operator edit the JSON `config` of the currently selected node.
 * Edits are kept as a structured key/value editor rather than free-form JSON
 * to keep the surface approachable for non-engineers; an "Advanced" toggle
 * exposes the raw JSON for power users.
 */

import * as React from "react";

import type { WorkflowNode } from "./types";

interface NodeConfigProps {
  node: WorkflowNode | null;
  onChange: (next: WorkflowNode) => void;
  onClose: () => void;
}

interface KVPair {
  key: string;
  value: string;
}

function pairsFromObject(obj: Record<string, unknown>): KVPair[] {
  return Object.entries(obj).map(([k, v]) => ({
    key: k,
    value: typeof v === "object" ? JSON.stringify(v) : String(v ?? ""),
  }));
}

function objectFromPairs(pairs: KVPair[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const { key, value } of pairs) {
    if (!key) continue;
    try {
      out[key] = JSON.parse(value);
    } catch {
      out[key] = value;
    }
  }
  return out;
}

export function NodeConfig(props: NodeConfigProps): React.JSX.Element {
  const [advanced, setAdvanced] = React.useState(false);
  const [json, setJson] = React.useState<string>("{}");
  const [pairs, setPairs] = React.useState<KVPair[]>([]);

  React.useEffect(() => {
    if (!props.node) return;
    setJson(JSON.stringify(props.node.config, null, 2));
    setPairs(pairsFromObject(props.node.config));
  }, [props.node?.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (!props.node) {
    return (
      <aside className="w-72 border-l bg-white p-3 text-sm text-slate-500">
        <p>Select a node to edit its configuration.</p>
      </aside>
    );
  }

  const node = props.node;

  const updateConfig = (cfg: Record<string, unknown>) => {
    props.onChange({ ...node, config: cfg });
  };

  const updatePair = (idx: number, patch: Partial<KVPair>) => {
    const next = pairs.slice();
    next[idx] = { ...next[idx], ...patch };
    setPairs(next);
    updateConfig(objectFromPairs(next));
  };

  const addPair = () => {
    const next = [...pairs, { key: "", value: "" }];
    setPairs(next);
  };

  const removePair = (idx: number) => {
    const next = pairs.slice();
    next.splice(idx, 1);
    setPairs(next);
    updateConfig(objectFromPairs(next));
  };

  const applyJson = () => {
    try {
      const parsed = JSON.parse(json || "{}");
      updateConfig(parsed);
      setPairs(pairsFromObject(parsed));
    } catch (err) {
      window.alert(`Invalid JSON: ${(err as Error).message}`);
    }
  };

  return (
    <aside className="flex w-80 flex-col gap-3 overflow-y-auto border-l bg-white p-3 text-sm">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-700">
          {node.id} <span className="ml-1 text-xs uppercase text-slate-400">
            {node.type}
          </span>
        </h3>
        <button onClick={props.onClose}
                className="text-xs text-slate-400 hover:text-slate-700">
          ✕
        </button>
      </div>

      <label className="text-xs font-medium text-slate-600">
        Node ID
        <input
          value={node.id}
          onChange={(e) => props.onChange({ ...node, id: e.target.value })}
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
        />
      </label>

      <label className="text-xs font-medium text-slate-600">
        Type
        <select
          value={node.type}
          onChange={(e) => props.onChange({
            ...node,
            type: e.target.value as WorkflowNode["type"],
          })}
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
        >
          {["trigger", "agent", "condition", "action",
             "delay", "human"].map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </label>

      <div>
        <div className="mb-1 flex items-center justify-between">
          <h4 className="text-xs font-semibold text-slate-600">Config</h4>
          <button
            onClick={() => setAdvanced((v) => !v)}
            className="text-[11px] text-indigo-600 hover:underline"
          >
            {advanced ? "Simple" : "Advanced"}
          </button>
        </div>
        {advanced ? (
          <div>
            <textarea
              value={json}
              onChange={(e) => setJson(e.target.value)}
              onBlur={applyJson}
              className="h-40 w-full rounded border border-slate-300 p-2 font-mono text-xs"
            />
            <button
              onClick={applyJson}
              className="mt-1 rounded bg-indigo-600 px-2 py-1 text-xs font-bold text-white"
            >
              Apply JSON
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {pairs.map((p, idx) => (
              <div key={idx} className="flex gap-1">
                <input
                  value={p.key}
                  onChange={(e) => updatePair(idx, { key: e.target.value })}
                  placeholder="key"
                  className="w-1/3 rounded border border-slate-200 px-1 py-0.5 text-xs"
                />
                <input
                  value={p.value}
                  onChange={(e) => updatePair(idx, { value: e.target.value })}
                  placeholder="value"
                  className="flex-1 rounded border border-slate-200 px-1 py-0.5 text-xs"
                />
                <button
                  onClick={() => removePair(idx)}
                  className="rounded bg-rose-100 px-1 text-rose-700"
                  aria-label="remove"
                >
                  ✕
                </button>
              </div>
            ))}
            <button
              onClick={addPair}
              className="mt-1 rounded bg-slate-200 px-2 py-0.5 text-xs hover:bg-slate-300"
            >
              + add field
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}