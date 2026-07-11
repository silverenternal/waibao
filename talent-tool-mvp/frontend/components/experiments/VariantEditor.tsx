/**
 * VariantEditor (T805): 编辑/新增 variant 的内联表单.
 */
"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import type { VariantPayload } from "@/lib/api-ab";

interface VariantEditorProps {
  variants: VariantPayload[];
  onChange: (variants: VariantPayload[]) => void;
  builtins?: string[];
  readOnly?: boolean;
}

export function VariantEditor({ variants, onChange, readOnly }: VariantEditorProps) {
  const add = () => {
    onChange([...variants, { name: `variant_${variants.length + 1}`, weight: 0, config: {} }]);
  };
  const remove = (idx: number) => {
    if (variants.length <= 2) return;
    const next = variants.filter((_, i) => i !== idx);
    onChange(next);
  };
  const update = (idx: number, patch: Partial<VariantPayload>) => {
    const next = variants.map((v, i) => (i === idx ? { ...v, ...patch } : v));
    onChange(next);
  };

  const totalWeight = variants.reduce((s, v) => s + v.weight, 0);

  return (
    <div className="space-y-3">
      {variants.map((v, idx) => {
        const pct = totalWeight > 0 ? (v.weight / totalWeight) * 100 : 0;
        return (
          <Card key={`${v.name}-${idx}`}>
            <CardContent className="pt-4 grid grid-cols-12 gap-3 items-end">
              <div className="col-span-5 space-y-1">
                <Label className="text-xs">Name</Label>
                <Input
                  value={v.name}
                  disabled={readOnly}
                  onChange={(e) => update(idx, { name: e.target.value })}
                  placeholder="control"
                />
              </div>
              <div className="col-span-4 space-y-1">
                <Label className="text-xs">Weight</Label>
                <Input
                  type="number"
                  min={0}
                  max={10000}
                  value={v.weight}
                  disabled={readOnly}
                  onChange={(e) => update(idx, { weight: Number(e.target.value) })}
                />
              </div>
              <div className="col-span-2 text-xs text-muted-foreground text-right">
                {pct.toFixed(1)}%
              </div>
              <div className="col-span-1">
                {!readOnly && variants.length > 2 && (
                  <Button variant="ghost" size="sm" onClick={() => remove(idx)}>
                    ×
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
      {!readOnly && variants.length < 8 && (
        <Button variant="outline" size="sm" onClick={add}>
          + Add variant
        </Button>
      )}
      <p className="text-xs text-muted-foreground">
        Total weight {totalWeight}. Distribution is calculated as weighted share.
      </p>
    </div>
  );
}
