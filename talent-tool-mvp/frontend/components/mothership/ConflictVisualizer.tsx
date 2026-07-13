"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface ConflictProps {
  dimensions: Array<{
    dimension: string;
    score: number;
    variance: number;
    conflicting: boolean;
    notes: string[];
  }>;
}

export function ConflictVisualizer({ dimensions }: ConflictProps) {
  const conflicting = dimensions.filter(d => d.conflicting);

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>冲突可视化 · Conflict Visualizer</CardTitle>
        <p className="text-sm text-muted-foreground">高亮分歧维度,方便定位协商点</p>
      </CardHeader>
      <CardContent>
        {conflicting.length === 0 ? (
          <p className="text-sm text-muted-foreground">无冲突维度 🎉</p>
        ) : (
          <div className="space-y-2">
            {conflicting.map((d, i) => (
              <div key={i} className="border-l-4 border-amber-400 pl-3 py-2 bg-amber-50">
                <div className="flex items-center gap-2">
                  <Badge variant="destructive">冲突</Badge>
                  <span className="font-medium">{d.dimension}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  方差 {d.variance.toFixed(3)} · 平均分 {d.score.toFixed(2)}
                </p>
                {d.notes.length > 0 && (
                  <ul className="text-xs mt-1 list-disc pl-4">
                    {d.notes.map((n, j) => <li key={j}>{n}</li>)}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default ConflictVisualizer;
