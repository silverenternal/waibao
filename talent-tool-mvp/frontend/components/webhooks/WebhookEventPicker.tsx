"use client";

import * as React from "react";
import { ALL_WEBHOOK_EVENTS, type WebhookEventType } from "@/lib/api-webhooks";

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

/**
 * WebhookEventPicker — multi-select event type chips.
 */
export function WebhookEventPicker({ value, onChange, disabled }: Props) {
  const selected = new Set(value);

  const toggle = (ev: WebhookEventType) => {
    if (disabled) return;
    const next = new Set(selected);
    if (next.has(ev)) next.delete(ev);
    else next.add(ev);
    onChange([...next]);
  };

  return (
    <div className="flex flex-wrap gap-2">
      {ALL_WEBHOOK_EVENTS.map((ev) => {
        const isOn = selected.has(ev);
        return (
          <button
            key={ev}
            type="button"
            disabled={disabled}
            onClick={() => toggle(ev)}
            aria-pressed={isOn}
            className={`px-2 py-1 text-xs font-medium rounded-full border transition-colors ${
              isOn
                ? "bg-blue-600 text-white border-blue-600 hover:bg-blue-700"
                : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
            } ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
          >
            {ev}
          </button>
        );
      })}
    </div>
  );
}

export default WebhookEventPicker;
