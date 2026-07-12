"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Briefcase, MapPin, Banknote, Clock } from "lucide-react";
import type { JobMatch } from "@/lib/types";

interface SubscriptionMatchProps {
  matches: JobMatch[];
  subscriptionName: string;
  loading?: boolean;
}

export function SubscriptionMatchList({
  matches,
  subscriptionName,
  loading,
}: SubscriptionMatchProps) {
  if (loading) {
    return (
      <Card>
        <CardContent className="py-6 text-sm text-muted-foreground">
          Searching for matches…
        </CardContent>
      </Card>
    );
  }
  if (matches.length === 0) {
    return (
      <Card>
        <CardContent className="py-6 text-sm text-muted-foreground">
          No matching jobs yet for &quot;{subscriptionName}&quot;. We&apos;ll notify you
          when something appears.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Briefcase className="h-4 w-4" /> {matches.length} new matches for{" "}
          &quot;{subscriptionName}&quot;
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {matches.map((m) => (
          <MatchItem key={m.id} job={m} />
        ))}
      </CardContent>
    </Card>
  );
}

function MatchItem({ job }: { job: JobMatch }) {
  return (
    <div className="rounded-md border p-3 hover:bg-muted/40 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-medium truncate">
            {job.title}{" "}
            <span className="text-muted-foreground font-normal">@ {job.company}</span>
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground mt-1">
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" /> {job.city || "—"}
            </span>
            {job.salary_max > 0 && (
              <span className="inline-flex items-center gap-1">
                <Banknote className="h-3 w-3" /> {job.currency}{" "}
                {Math.round(job.salary_min).toLocaleString()}-
                {Math.round(job.salary_max).toLocaleString()}
              </span>
            )}
            {job.remote_policy && (
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3 w-3" /> {job.remote_policy}
              </span>
            )}
          </div>
          {job.reasons?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {job.reasons.slice(0, 3).map((r, i) => (
                <Badge key={i} variant="secondary" className="text-[10px]">
                  {r}
                </Badge>
              ))}
            </div>
          )}
        </div>
        <div className="text-right shrink-0">
          <div className="text-lg font-semibold text-emerald-600">
            {(job.score * 100).toFixed(0)}
          </div>
          <div className="text-[10px] uppercase text-muted-foreground">score</div>
        </div>
      </div>
    </div>
  );
}