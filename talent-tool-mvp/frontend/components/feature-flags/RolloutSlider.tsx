"use client";

/**
 * v6.0 T2103 — RolloutSlider.
 *
 * Accessible range input with snap-to presets (0/10/25/50/100) and live
 * bucket estimate. Used by FlagCard and admin pages.
 */

import * as React from "react";

export interface RolloutSliderProps {
  value: number;
  onChange: (next: number) => void;
  min?: number;
  max?: number;
  step?: number;
  presets?: number[];
  label?: string;
}

const DEFAULT_PRESETS = [0, 10, 25, 50, 100];

export function RolloutSlider(props: RolloutSliderProps): JSX.Element {
  const {
    value,
    onChange,
    min = 0,
    max = 100,
    step = 1,
    presets = DEFAULT_PRESETS,
    label = "Rollout %",
  } = props;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-slate-700">{label}</span>
        <span className="font-mono text-slate-900" data-testid="rollout-value">
          {value}%
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-2 w-full cursor-pointer appearance-none rounded bg-slate-200 accent-slate-900"
        aria-label={label}
      />
      <div className="flex items-center gap-1">
        {presets.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onChange(p)}
            className={`rounded-full px-2 py-0.5 text-xs ${
              value === p
                ? "bg-slate-900 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {p}%
          </button>
        ))}
      </div>
    </div>
  );
}