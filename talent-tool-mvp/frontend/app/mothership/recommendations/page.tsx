"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { MetricTile } from "@/components/shared/metric-tile";
import { RecommendedCandidateList } from "@/components/RecommendedCandidate";
import { Sparkles, Search, Briefcase } from "lucide-react";
import type { RecommendedCandidate, Role } from "@/lib/types";

export default function RecommendationsPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleId, setRoleId] = useState<string>("");
  const [candidates, setCandidates] = useState<RecommendedCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const list = (await apiClient.roles.list()) as Role[] | { data: Role[] };
        setRoles(Array.isArray(list) ? list : list?.data ?? []);
      } catch (err) {
        console.error("[recommendations] roles load failed", err);
        setPageError("Failed to load roles.");
      }
    }
    load();
  }, []);

  const loadCandidates = async () => {
    if (!roleId) return;
    setLoading(true);
    try {
      const { candidates } = await apiClient.recommendations.forRole(roleId, 20);
      setCandidates(candidates);
    } catch (err) {
      console.error("[recommendations] candidates load failed", err);
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  };

  const selected = roles.find((r) => r.id === roleId);
  const avgScore =
    candidates.length > 0
      ? candidates.reduce((s, c) => s + c.overall_score, 0) / candidates.length
      : 0;
  const strong = candidates.filter((c) => c.confidence === "strong").length;

  return (
    <ErrorBoundary>(<div className="space-y-6 p-6">
        <header className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-amber-500" />
              Candidate recommendations
            </h1>
            <p className="text-sm text-muted-foreground">
              Active candidates ranked against an open role using matching v2.
            </p>
          </div>
        </header>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Select a role</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1 flex-1 min-w-[260px]">
                <Label htmlFor="role-input">Role ID</Label>
                <Input
                  id="role-input"
                  placeholder="paste role id or pick from list below"
                  value={roleId}
                  onChange={(e) => setRoleId(e.target.value)}
                />
              </div>
              <Button onClick={loadCandidates} disabled={!roleId || loading}>
                <Search className="h-4 w-4 mr-1" />
                {loading ? "Loading…" : "Recommend"}
              </Button>
            </div>

            {roles.length > 0 && (
              <div className="mt-4">
                <p className="text-xs text-muted-foreground mb-2">
                  Active roles ({roles.length})
                </p>
                <div className="flex flex-wrap gap-2">
                  {roles.slice(0, 20).map((r) => (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => setRoleId(r.id)}
                      className={`text-xs px-2 py-1 rounded-full border ${
                        r.id === roleId
                          ? "bg-blue-600 text-white border-blue-600"
                          : "bg-white text-slate-700 hover:bg-muted"
                      }`}
                    >
                      {r.title}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
        {roleId && (
          <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <MetricTile
              label="Candidates"
              value={candidates.length}
              icon={<Briefcase className="h-4 w-4" />}
              loading={loading}
            />
            <MetricTile
              label="Avg score"
              value={`${(avgScore * 100).toFixed(0)}`}
              icon={<Sparkles className="h-4 w-4" />}
              loading={loading}
            />
            <MetricTile
              label="Strong matches"
              value={strong}
              icon={<Sparkles className="h-4 w-4" />}
              loading={loading}
            />
            <MetricTile
              label="Role"
              value={selected?.title ?? "—"}
              icon={<Briefcase className="h-4 w-4" />}
            />
          </section>
        )}
        {pageError && (
          <p className="text-sm text-red-600">{pageError}</p>
        )}
        {roleId ? (
          loading ? (
            <Skeleton className="h-[400px] w-full" />
          ) : (
            <RecommendedCandidateList
              candidates={candidates}
              roleTitle={selected?.title}
            />
          )
        ) : (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              Pick a role above to see ranked candidates.
            </CardContent>
          </Card>
        )}
      </div>)</ErrorBoundary>
  );
}