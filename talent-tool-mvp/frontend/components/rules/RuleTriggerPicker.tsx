"use client";

import * as React from "react";
import type { BuiltinTrigger } from "@/lib/api-rules";

interface Props {
  triggers: BuiltinTrigger[];
  value: string;
  onChange: (next: string) => void;
}

/**
 * 内置触发器下拉 (T804).
 */
export function RuleTriggerPicker({ triggers, value, onChange }: Props) {
  return (
    <div className="space-y-2">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded border-slate-300 border px-3 py-2 text-sm font-mono"
      >
        <option value="">— 选择触发器 —</option>
        {triggers.map((t) => (
          <option key={t.name} value={t.name}>
            {t.name} {t.kind === "metric" ? "(metric)" : ""}
          </option>
        ))}
      </select>
      {value && (
        <div className="rounded bg-slate-50 border border-slate-200 p-2 text-xs space-y-1">
          {(() => {
            const t = triggers.find((x) => x.name === value);
            if (!t) return null;
            return (
              <>
                <div className="text-slate-600">{t.description}</div>
                {t.example_context && (
                  <div className="text-slate-500">
                    <span className="font-semibold">样例上下文:</span>{" "}
                    <code className="font-mono text-[11px]">
                      {JSON.stringify(t.example_context)}
                    </code>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}
