"use client";

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface BiasHit {
  category: string;
  label: string;
  matched_phrase: string;
  position: number;
  severity: number;
}

interface BiasReport {
  hits: BiasHit[];
  score: number;
  recommendations: string[];
  can_submit: boolean;
}

export function BiasWarningModal({ report, onConfirm }: {
  report: BiasReport;
  onConfirm: () => void;
}) {
  const [agreed, setAgreed] = useState(false);
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg p-6 max-w-lg w-full">
        <h2 className="text-lg font-semibold mb-2">检测到 {report.hits.length} 处偏见</h2>
        <p className="text-sm text-muted-foreground mb-3">
          分项命中 → 建议替代话术(强制至少 1 处替换才可提交)
        </p>
        <ul className="space-y-2 mb-4">
          {report.hits.map((h, i) => (
            <li key={i} className="flex items-center justify-between border-l-2 border-amber-400 pl-2">
              <span className="text-sm">
                <span className="font-mono text-xs">[{h.category}]</span> 「{h.matched_phrase}」
              </span>
              <Badge variant={h.severity >= 70 ? "destructive" : "secondary"}>
                {h.severity}
              </Badge>
            </li>
          ))}
        </ul>
        {report.recommendations.length > 0 && (
          <div className="mb-4 text-sm bg-amber-50 p-3 rounded">
            <div className="font-medium mb-1">替代话术</div>
            {report.recommendations.map((r, i) => <div key={i}>· {r}</div>)}
          </div>
        )}
        <label className="flex items-center gap-2 text-sm mb-4">
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          <span>我已采用替代话术</span>
        </label>
        <div className="flex gap-2 justify-end">
          <Button variant="outline" onClick={() => history.back()}>返回修改</Button>
          <Button disabled={!agreed && !report.can_submit} onClick={onConfirm}>
            强制提交
          </Button>
        </div>
      </div>
    </div>
  );
}

export default BiasWarningModal;
