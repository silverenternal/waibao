"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Briefcase,
  MapPin,
  Clock,
  Sparkles,
  ChevronRight,
} from "lucide-react";
import type { RecommendedCandidate } from "@/lib/types";

interface RecommendedCandidateListProps {
  candidates: RecommendedCandidate[];
  roleTitle?: string;
  loading?: boolean;
  onContact?: (c: RecommendedCandidate) => void;
  onView?: (c: RecommendedCandidate) => void;
}

export function RecommendedCandidateList({
  candidates,
  roleTitle,
  loading,
  onContact,
  onView,
}: RecommendedCandidateListProps) {
  if (loading) {
    return (
      <Card>
        <CardContent className="py-6 text-sm text-muted-foreground">
          Ranking candidates for {roleTitle ?? "this role"}…
        </CardContent>
      </Card>
    );
  }
  if (candidates.length === 0) {
    return (
      <Card>
        <CardContent className="py-6 text-sm text-muted-foreground text-center">
          No active candidates match this role yet. Check back later.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-amber-500" />
          Top {candidates.length} candidates
          {roleTitle ? ` for ${roleTitle}` : ""}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {candidates.map((c) => (
          <CandidateRow
            key={c.candidate_id}
            c={c}
            onContact={onContact}
            onView={onView}
          />
        ))}
      </CardContent>
    </Card>
  );
}

function CandidateRow({
  c,
  onContact,
  onView,
}: {
  c: RecommendedCandidate;
  onContact?: (c: RecommendedCandidate) => void;
  onView?: (c: RecommendedCandidate) => void;
}) {
  const initials = c.full_name
    .split(/\s+/)
    .map((s) => s[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const confidenceTone =
    c.confidence === "strong"
      ? "bg-emerald-100 text-emerald-700"
      : c.confidence === "good"
        ? "bg-blue-100 text-blue-700"
        : "bg-amber-100 text-amber-700";

  return (
    <div className="rounded-md border p-3 flex gap-3">
      <Avatar className="h-10 w-10">
        <AvatarFallback>{initials || "??"}</AvatarFallback>
      </Avatar>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-medium truncate">{c.full_name || "Anonymous"}</div>
            <div className="text-xs text-muted-foreground truncate">
              {c.headline || c.seniority || "—"}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-lg font-semibold">
              {(c.overall_score * 100).toFixed(0)}
            </div>
            <div className="text-[10px] uppercase text-muted-foreground">match</div>
          </div>
        </div>

        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground mt-1">
          {c.city && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" /> {c.city}
            </span>
          )}
          {c.seniority && (
            <span className="inline-flex items-center gap-1">
              <Briefcase className="h-3 w-3" /> {c.seniority}
            </span>
          )}
          {c.years_experience > 0 && (
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" /> {c.years_experience}y
            </span>
          )}
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${confidenceTone}`}
          >
            {c.confidence}
          </span>
        </div>

        {c.skills?.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {c.skills.slice(0, 6).map((s) => (
              <Badge key={s} variant="secondary" className="text-[10px]">
                {s}
              </Badge>
            ))}
            {c.skills.length > 6 && (
              <span className="text-[10px] text-muted-foreground">
                +{c.skills.length - 6}
              </span>
            )}
          </div>
        )}

        {c.missing_skills?.length > 0 && (
          <div className="text-[11px] text-muted-foreground mt-1">
            Missing: {c.missing_skills.slice(0, 4).join(", ")}
          </div>
        )}

        <div className="flex gap-2 mt-3">
          {onContact && (
            <Button size="sm" onClick={() => onContact(c)}>
              Intro request
              <ChevronRight className="h-3 w-3 ml-1" />
            </Button>
          )}
          {onView && (
            <Button size="sm" variant="outline" onClick={() => onView(c)}>
              View profile
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}