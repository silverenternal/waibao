"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  activateCandidate,
  previewActivation,
  type SleepyCandidate,
} from "@/lib/api-rediscovery";

export interface SleepyCandidateCardProps {
  candidate: SleepyCandidate;
  onActivated?: (candidateId: string) => void;
}

/**
 * 沉睡候选人卡片 — 显示潜力 + 推荐原因 + 一键激活.
 */
export function SleepyCandidateCard({ candidate, onActivated }: SleepyCandidateCardProps) {
  const [strategy, setStrategy] = React.useState("standard");
  const [preview, setPreview] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [activated, setActivated] = React.useState(false);

  const potential = candidate.rediscover_potential;
  const potentialColor =
    potential >= 0.7
      ? "bg-emerald-500 text-white"
      : potential >= 0.5
        ? "bg-amber-500 text-white"
        : "bg-slate-400 text-white";

  const handlePreview = async () => {
    const r = await previewActivation(candidate.id);
    setPreview(r.preview_message);
    setStrategy(r.suggested_strategy);
  };

  const handleActivate = async () => {
    setBusy(true);
    try {
      await activateCandidate(candidate.id, {
        strategy,
        channel: "im",
        message: preview ?? undefined,
      });
      setActivated(true);
      onActivated?.(candidate.id);
    } catch (e) {
      console.error(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{candidate.name}</CardTitle>
          <span className={`px-2 py-1 rounded text-xs font-medium ${potentialColor}`}>
            潜力 {Math.round(potential * 100)}%
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex flex-wrap gap-3 text-xs text-slate-600">
          <span>沉睡 {candidate.dormant_days} 天</span>
          {candidate.city && <span>· {candidate.city}</span>}
          {candidate.seniority && <span>· {candidate.seniority}</span>}
          {candidate.salary_expect && (
            <span>· 期望 ¥{(candidate.salary_expect / 1000).toFixed(0)}k</span>
          )}
        </div>
        {candidate.skills.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {candidate.skills.slice(0, 5).map((s) => (
              <span
                key={s}
                className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-xs"
              >
                {s}
              </span>
            ))}
          </div>
        )}
        <p className="text-xs text-slate-600 leading-relaxed">{candidate.reason}</p>
        {candidate.recommended_roles.length > 0 && (
          <div className="bg-emerald-50 rounded p-2 space-y-1">
            <p className="text-xs font-medium text-emerald-700">推荐职位:</p>
            {candidate.recommended_roles.slice(0, 2).map((r) => (
              <p key={r.role_id} className="text-xs text-emerald-700">
                · {r.title} (匹配 {Math.round(r.score * 100)}%)
              </p>
            ))}
          </div>
        )}

        {preview && (
          <div className="bg-slate-50 rounded p-2 text-xs text-slate-700 whitespace-pre-line">
            {preview}
          </div>
        )}

        <div className="flex items-center gap-2 pt-1">
          <label className="text-xs text-slate-500">策略:</label>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="text-xs rounded border border-slate-300 px-2 py-1"
          >
            <option value="conservative">保守</option>
            <option value="standard">标准</option>
            <option value="aggressive">激进</option>
          </select>
          <Button size="sm" variant="outline" onClick={handlePreview}>
            预览
          </Button>
          <Button size="sm" disabled={busy || activated} onClick={handleActivate}>
            {activated ? "已激活" : busy ? "发送中…" : "激活"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
