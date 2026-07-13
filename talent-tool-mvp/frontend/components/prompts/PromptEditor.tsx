"use client";

/**
 * T2704: Prompt v2 — editor component.
 *
 * Used by both the list page (creating a new version) and the detail
 * page (editing an existing version before activation).
 */

import * as React from "react";

import type { PromptVersion } from "./types";

export interface PromptEditorProps {
  initial?: Partial<PromptVersion>;
  onSubmit: (values: {
    name: string;
    agent: string;
    content: string;
    description?: string;
    variables?: string[];
    tags?: string[];
    traffic_pct?: number;
    status?: PromptVersion["status"];
  }) => Promise<void> | void;
  submitLabel?: string;
  readOnly?: boolean;
}

export default function PromptEditor({
  initial,
  onSubmit,
  submitLabel = "Save draft",
  readOnly = false,
}: PromptEditorProps): React.JSX.Element {
  const [name, setName] = React.useState(initial?.name ?? "");
  const [agent, setAgent] = React.useState(initial?.agent ?? "default");
  const [content, setContent] = React.useState(initial?.content ?? "");
  const [description, setDescription] = React.useState(initial?.description ?? "");
  const [variablesText, setVariablesText] = React.useState(
    (initial?.variables ?? []).join(", "),
  );
  const [tagsText, setTagsText] = React.useState(
    (initial?.tags ?? []).join(", "),
  );
  const [trafficPct, setTrafficPct] = React.useState(initial?.traffic_pct ?? 0);
  const [status, setStatus] = React.useState<PromptVersion["status"]>(
    initial?.status ?? "draft",
  );
  const [busy, setBusy] = React.useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await onSubmit({
        name,
        agent,
        content,
        description,
        variables: variablesText.split(",").map((s) => s.trim()).filter(Boolean),
        tags: tagsText.split(",").map((s) => s.trim()).filter(Boolean),
        traffic_pct: Number(trafficPct) || 0,
        status,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <label className="text-sm md:col-span-2">
          <span className="block font-medium mb-1">Name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={readOnly}
            required
            className="w-full border rounded px-2 py-1 text-sm bg-background"
            placeholder="resume_screener"
          />
        </label>
        <label className="text-sm">
          <span className="block font-medium mb-1">Agent</span>
          <input
            value={agent}
            onChange={(e) => setAgent(e.target.value)}
            disabled={readOnly}
            className="w-full border rounded px-2 py-1 text-sm bg-background"
          />
        </label>
      </div>

      <label className="text-sm block">
        <span className="block font-medium mb-1">Content (use {`{{var}}`} for variables)</span>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          disabled={readOnly}
          rows={10}
          className="w-full border rounded px-2 py-1 text-sm font-mono bg-background"
          placeholder="You are a recruiter. Consider candidate {{name}} for {{role}}…"
        />
      </label>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="text-sm">
          <span className="block font-medium mb-1">Variables (comma-separated)</span>
          <input
            value={variablesText}
            onChange={(e) => setVariablesText(e.target.value)}
            disabled={readOnly}
            className="w-full border rounded px-2 py-1 text-sm bg-background"
          />
        </label>
        <label className="text-sm">
          <span className="block font-medium mb-1">Tags (comma-separated)</span>
          <input
            value={tagsText}
            onChange={(e) => setTagsText(e.target.value)}
            disabled={readOnly}
            className="w-full border rounded px-2 py-1 text-sm bg-background"
          />
        </label>
      </div>

      <label className="text-sm block">
        <span className="block font-medium mb-1">Description</span>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={readOnly}
          className="w-full border rounded px-2 py-1 text-sm bg-background"
        />
      </label>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
        <label className="text-sm">
          <span className="block font-medium mb-1">Traffic %</span>
          <input
            type="number"
            min={0}
            max={100}
            value={trafficPct}
            onChange={(e) => setTrafficPct(Number(e.target.value) || 0)}
            disabled={readOnly}
            className="w-full border rounded px-2 py-1 text-sm bg-background"
          />
        </label>
        <label className="text-sm">
          <span className="block font-medium mb-1">Status</span>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as PromptVersion["status"])}
            disabled={readOnly}
            className="w-full border rounded px-2 py-1 text-sm bg-background"
          >
            <option value="draft">draft</option>
            <option value="active">active</option>
            <option value="retired">retired</option>
          </select>
        </label>
        <button
          type="submit"
          disabled={readOnly || busy}
          className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium disabled:opacity-50"
        >
          {busy ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}