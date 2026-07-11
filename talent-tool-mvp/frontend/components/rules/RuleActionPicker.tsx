"use client";

import * as React from "react";
import type { RuleAction } from "@/lib/api-rules";

interface Props {
  value: RuleAction[];
  onChange: (next: RuleAction[]) => void;
}

const ACTION_TYPES = [
  {
    type: "notify",
    label: "通知 (notify)",
    defaults: { channel: "email", user_id: "", title: "", content: "" },
  },
  {
    type: "create_ticket",
    label: "建工单 (create_ticket)",
    defaults: { department: "ops", priority: "P3", title: "" },
  },
  {
    type: "webhook",
    label: "Webhook (webhook)",
    defaults: { event: "ticket.created" },
  },
  {
    type: "emit_event",
    label: "Emit Event (emit_event)",
    defaults: { event: "" },
  },
] as const;

/**
 * 动作编辑 (T804). 简化版:每个动作提供 type 选择 + 自由 JSON 参数.
 */
export function RuleActionPicker({ value, onChange }: Props) {
  function update(i: number, patch: Partial<RuleAction>) {
    const next = value.map((a, idx) => (idx === i ? { ...a, ...patch } : a));
    onChange(next);
  }
  function remove(i: number) {
    onChange(value.filter((_, idx) => idx !== i));
  }
  function add(type: (typeof ACTION_TYPES)[number]["type"]) {
    const def = ACTION_TYPES.find((x) => x.type === type);
    if (!def) return;
    onChange([...value, { type, ...def.defaults }]);
  }

  return (
    <div className="space-y-2">
      {value.length === 0 && (
        <div className="text-xs text-slate-500">尚未添加动作</div>
      )}
      {value.map((a, i) => (
        <div
          key={i}
          className="rounded border bg-slate-50 border-slate-200 p-2 text-xs space-y-2"
        >
          <div className="flex items-center justify-between">
            <span className="font-mono">{a.type}</span>
            <button
              type="button"
              onClick={() => remove(i)}
              className="text-red-600 hover:underline"
            >
              删除
            </button>
          </div>
          <textarea
            value={_actionParamsJson(a)}
            onChange={(e) => {
              try {
                const parsed = JSON.parse(e.target.value);
                const { type, ...rest } = parsed;
                update(i, { type: type ?? a.type, ...rest } as RuleAction);
              } catch {
                // ignore parse errors
              }
            }}
            rows={4}
            className="w-full font-mono text-[11px] rounded border-slate-300 border p-2"
          />
        </div>
      ))}
      <div className="flex gap-1 flex-wrap">
        {ACTION_TYPES.map((t) => (
          <button
            key={t.type}
            type="button"
            onClick={() => add(t.type)}
            className="px-2 py-1 text-[11px] rounded border bg-white hover:bg-blue-50"
          >
            + {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function _actionParamsJson(a: RuleAction): string {
  // 把 type 字段纳入 JSON 字符串以便编辑.
  return JSON.stringify(a, null, 2);
}
