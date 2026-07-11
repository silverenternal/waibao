"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

export interface WeightTunerProps {
  weights: Record<string, number>;
  defaults?: Record<string, number>;
  onChange?: (weights: Record<string, number>) => void;
  onSave?: (weights: Record<string, number>) => Promise<void> | void;
  saving?: boolean;
}

/**
 * 权重调节器: 4 个维度滑块 + 自动归一化预览.
 */
const DEFAULT_DIMS = ["skill", "semantic", "experience", "culture"];
const LABELS: Record<string, string> = {
  skill: "技能匹配",
  semantic: "语义相似",
  experience: "经验契合",
  culture: "文化契合",
};

export function WeightTuner({
  weights,
  defaults,
  onChange,
  onSave,
  saving,
}: WeightTunerProps) {
  const dims = defaults ? Object.keys(defaults) : DEFAULT_DIMS;
  const [local, setLocal] = React.useState<Record<string, number>>(() => ({
    ...DEFAULT_DIMS.reduce<Record<string, number>>((acc, k) => {
      acc[k] = 0;
      return acc;
    }, {}),
    ...weights,
  }));

  React.useEffect(() => {
    setLocal((prev) => ({ ...prev, ...weights }));
  }, [weights]);

  const total = Object.values(local).reduce((s, v) => s + (Number(v) || 0), 0);
  const normalized: Record<string, number> = {};
  if (total > 0) {
    for (const [k, v] of Object.entries(local)) {
      normalized[k] = Math.round((v / total) * 10000) / 10000;
    }
  }

  const handleSlide = (k: string, v: number) => {
    const next = { ...local, [k]: v };
    setLocal(next);
    // 输出归一化结果
    const sum = Object.values(next).reduce((s, x) => s + (Number(x) || 0), 0);
    if (sum > 0 && onChange) {
      const norm: Record<string, number> = {};
      for (const [key, val] of Object.entries(next)) {
        norm[key] = Math.round((val / sum) * 10000) / 10000;
      }
      onChange(norm);
    }
  };

  const handleInput = (k: string, raw: string) => {
    const v = Number(raw);
    if (Number.isNaN(v)) return;
    handleSlide(k, Math.max(0, Math.min(1, v)));
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">匹配权重调节</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {dims.map((k) => (
          <div key={k} className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-slate-700">
                {LABELS[k] ?? k}
              </span>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={local[k] ?? 0}
                  onChange={(e) => handleInput(k, e.target.value)}
                  className="w-20 h-8 text-xs font-mono"
                />
                <Badge variant="outline" className="font-mono text-xs">
                  {(normalized[k] ?? 0).toFixed(3)}
                </Badge>
              </div>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={local[k] ?? 0}
              onChange={(e) => handleSlide(k, Number(e.target.value))}
              aria-label={LABELS[k] ?? k}
              className="w-full h-2 cursor-pointer accent-indigo-600"
            />
          </div>
        ))}

        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>总和: {total.toFixed(2)} (自动归一化)</span>
          {onSave && (
            <Button size="sm" disabled={saving} onClick={() => onSave(normalized)}>
              {saving ? "保存中…" : "保存权重"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}