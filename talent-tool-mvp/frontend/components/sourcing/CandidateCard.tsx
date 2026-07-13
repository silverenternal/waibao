"use client";

import * as React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  MATCH_DIMENSIONS,
  inviteCandidate,
  type SourcedCandidate,
} from "@/lib/api-sourcing";

export interface CandidateCardProps {
  candidate: SourcedCandidate;
  jobTitle?: string;
  onInvited?: (candidateId: string) => void;
}

function scoreColor(v: number): string {
  if (v >= 80) return "bg-emerald-500";
  if (v >= 60) return "bg-blue-500";
  if (v >= 40) return "bg-amber-500";
  return "bg-slate-400";
}

/**
 * 主动 sourcing 候选人卡片 — 5 维度评分 + 一键邀请面试 (T3002).
 */
export function CandidateCard({ candidate, jobTitle, onInvited }: CandidateCardProps) {
  const [inviting, setInviting] = React.useState(false);
  const [invited, setInvited] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const invite = async () => {
    setInviting(true);
    setError(null);
    try {
      await inviteCandidate(candidate.id, { job_title: jobTitle });
      setInvited(true);
      onInvited?.(candidate.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "邀请失败");
    } finally {
      setInviting(false);
    }
  };

  const initials = candidate.name.slice(0, 2);

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start gap-3">
          <Avatar className="h-12 w-12">
            {candidate.avatar_url && <AvatarImage src={candidate.avatar_url} alt={candidate.name} />}
            <AvatarFallback>{initials}</AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <a
                href={candidate.profile_url ?? "#"}
                target="_blank"
                rel="noreferrer"
                className="font-semibold text-slate-900 hover:underline truncate"
              >
                {candidate.name}
              </a>
              <Badge variant="outline" className="shrink-0 text-xs">
                {candidate.source}
              </Badge>
            </div>
            {candidate.headline && (
              <p className="text-sm text-slate-500 truncate">{candidate.headline}</p>
            )}
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-400">
              {candidate.location && <span>📍 {candidate.location}</span>}
              {candidate.company && <span>🏢 {candidate.company}</span>}
              {typeof candidate.years_experience === "number" && (
                <span>💼 {candidate.years_experience} 年</span>
              )}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-2xl font-bold text-slate-900">{candidate.match.overall}</div>
            <div className="text-xs text-slate-400">综合分</div>
          </div>
        </div>

        {/* 5 维度评分 */}
        <div className="grid grid-cols-5 gap-2">
          {MATCH_DIMENSIONS.map((d) => {
            const v = candidate.match[d.key];
            return (
              <div key={d.key} className="text-center">
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full ${scoreColor(v)}`}
                    style={{ width: `${Math.max(0, Math.min(100, v))}%` }}
                  />
                </div>
                <div className="mt-1 text-[11px] text-slate-500">{d.label}</div>
                <div className="text-[11px] font-medium text-slate-700">{Math.round(v)}</div>
              </div>
            );
          })}
        </div>

        {candidate.skills.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {candidate.skills.slice(0, 8).map((s) => (
              <Badge key={s} variant="secondary" className="text-xs">
                {s}
              </Badge>
            ))}
          </div>
        )}

        {candidate.reasons.length > 0 && (
          <ul className="text-xs text-slate-500 space-y-0.5">
            {candidate.reasons.slice(0, 3).map((r, i) => (
              <li key={i}>· {r}</li>
            ))}
          </ul>
        )}

        <div className="flex items-center justify-between pt-1">
          <span className="text-xs text-slate-400">
            {candidate.followers} followers · {candidate.public_repos} repos
          </span>
          <Button size="sm" onClick={invite} disabled={inviting || invited}>
            {invited ? "已邀请 ✓" : inviting ? "邀请中…" : "一键邀请面试"}
          </Button>
        </div>
        {error && <p className="text-xs text-rose-500">{error}</p>}
      </CardContent>
    </Card>
  );
}
