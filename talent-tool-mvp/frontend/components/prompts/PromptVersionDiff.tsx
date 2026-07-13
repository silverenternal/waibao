"use client";

/**
 * T2704: Prompt v2 — version diff viewer.
 *
 * Renders the unified diff produced by the backend (`PromptService.diff`).
 */

import * as React from "react";

import type { PromptDiff } from "./types";

export interface PromptVersionDiffProps {
  diff: PromptDiff;
  leftLabel?: string;
  rightLabel?: string;
}

export default function PromptVersionDiff({
  diff,
  leftLabel,
  rightLabel,
}: PromptVersionDiffProps): React.JSX.Element {
  const lines = diff.diff ? diff.diff.split("\n") : [];
  return (
    <div className="rounded-md border bg-muted/30 overflow-hidden">
      <div className="flex justify-between text-xs px-3 py-2 border-b bg-background">
        <span>
          {leftLabel ?? `v${diff.left.version}`}{" "}
          <span className="text-muted-foreground">({diff.left.status})</span>
        </span>
        <span>
          {rightLabel ?? `v${diff.right.version}`}{" "}
          <span className="text-muted-foreground">({diff.right.status})</span>
        </span>
      </div>
      {!diff.changed && (
        <div className="px-3 py-2 text-xs text-muted-foreground">
          No content differences.
        </div>
      )}
      <pre className="text-xs font-mono leading-5 max-h-[420px] overflow-auto">
        {lines.map((line, i) => (
          <DiffLine key={i} line={line} />
        ))}
      </pre>
      <div className="border-t px-3 py-1 text-[10px] text-muted-foreground flex justify-between">
        <span>left: {diff.size_left} chars</span>
        <span>right: {diff.size_right} chars</span>
      </div>
    </div>
  );
}

function DiffLine({ line }: { line: string }): React.JSX.Element {
  let cls = "px-3 whitespace-pre-wrap";
  if (line.startsWith("+") && !line.startsWith("+++")) {
    cls += " bg-green-500/10 text-green-700 dark:text-green-300";
  } else if (line.startsWith("-") && !line.startsWith("---")) {
    cls += " bg-red-500/10 text-red-700 dark:text-red-300";
  } else if (line.startsWith("@@")) {
    cls += " text-muted-foreground";
  } else if (line.startsWith("---") || line.startsWith("+++")) {
    cls += " font-semibold text-muted-foreground";
  }
  return <div className={cls}>{line || " "}</div>;
}