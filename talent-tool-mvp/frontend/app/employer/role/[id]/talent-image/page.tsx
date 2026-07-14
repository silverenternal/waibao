"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Employer-side Talent Image page (T602).
 *
 * Loads the role's persisted employer clarification row via
 * `GET /api/clarification/role/{role_id}` and renders the four blocks:
 *
 *   ┌─ Header (role id + refresh) ──────────────────────┐
 *   ├─ ConsensusScore + StakeholderMatrix            ┐
 *   ├─ TalentImageCard                              │ top half
 *   ├─ EmployerContradictionList                    ┘
 *   ├─ Follow-up questions                                 │
 *   └─ Needs list (explicit / implicit / must / nice)      bottom half
 *
 * The "重新综合" button triggers a POST back to the synthesize endpoint
 * with the persisted contributor_inputs — letting the agent re-evaluate
 * without requiring users to resubmit every form.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Loader2,
  RefreshCcw,
  Users,
  AlertCircle,
  Sparkles,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

import {
  employerClarificationApi,
  normaliseList,
  type EmployerClarification,
  type FollowUpQuestion,
} from "@/lib/api-clarification";

import { TalentImageCard } from "@/components/mothership/TalentImageCard";
import { ConsensusScore } from "@/components/mothership/ConsensusScore";
import { StakeholderMatrix } from "@/components/mothership/StakeholderMatrix";
import { EmployerContradictionList } from "@/components/mothership/EmployerContradictionList";
import { FollowUpQuestions } from "@/components/FollowUpQuestions";

const REFRESH_MS = 60_000;

export default function RoleTalentImagePage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const roleId = params?.id ?? "";

  const [row, setRow] = React.useState<EmployerClarification | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [resyncing, setResyncing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    if (!roleId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await employerClarificationApi.roleClarification(roleId);
      setRow((resp && Object.keys(resp).length > 0 ? resp : null) as EmployerClarification | null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载画像失败");
    } finally {
      setLoading(false);
    }
  }, [roleId]);

  React.useEffect(() => {
    load();
    const id = window.setInterval(() => load(), REFRESH_MS);
    return () => window.clearInterval(id);
  }, [load]);

  async function handleResynthesize() {
    if (!roleId) return;
    setResyncing(true);
    try {
      const inputs = row?.contributor_inputs ?? {};
      await employerClarificationApi.synthesizeEmployer({
        role_id: roleId,
        brief: inputs.brief,
        spec: inputs.spec,
        compliance: inputs.compliance,
        policy: inputs.policy,
      });
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "重新综合失败");
    } finally {
      setResyncing(false);
    }
  }

  return (
    <ErrorBoundary>(<div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
        <header className="sticky top-0 z-20 border-b bg-white/80 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => router.push("/employer")}
                aria-label="返回"
              >
                <ArrowLeft className="size-4" />
              </Button>
              <div>
                <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
                  <Users className="size-5 text-violet-500" />
                  岗位人才画像
                </h1>
                <p className="text-xs text-muted-foreground">
                  Role ID · <span className="font-mono">{roleId || "—"}</span>
                </p>
              </div>
            </div>
            <Button
              onClick={handleResynthesize}
              disabled={resyncing || loading || !roleId}
              className="gap-2"
            >
              {resyncing ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <RefreshCcw className="size-4" />
              )}
              {resyncing ? "综合中..." : "重新综合"}
            </Button>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-6">
          {loading && <LoadingState />}

          {error && !loading && (
            <ErrorState message={error} onRetry={load} />
          )}

          {!loading && !error && (
            <div className="space-y-6">
              {/* Top row: consensus + matrix */}
              <div className="grid gap-6 lg:grid-cols-2">
                <ConsensusScore
                  score={row?.consensus_score ?? null}
                  caption={
                    row?.last_synthesized_at
                      ? `综合 ${new Date(row.last_synthesized_at).toLocaleString(
                          "en-GB",
                          { dateStyle: "medium", timeStyle: "short" },
                        )}`
                      : "等待首次综合"
                  }
                />
                <StakeholderMatrix
                  stances={deriveStances(row)}
                />
              </div>

              {/* Profile card */}
              <TalentImageCard clarification={row} />

              {/* Conflicts */}
              <EmployerContradictionList conflicts={row?.conflicts} />

              {/* Follow-ups + needs list */}
              <div className="grid gap-6 lg:grid-cols-2">
                <FollowUpQuestions
                  questions={(row?.follow_up_questions ?? []) as FollowUpQuestion[]}
                  onAnswer={(q, a) => {
                    // Optimistic toggle.
                    setRow((prev) =>
                      prev
                        ? {
                            ...prev,
                            follow_up_questions: (prev.follow_up_questions ?? []).map(
                              (qq, idx) =>
                                qq.question === q.question
                                  ? { ...qq, answered: true, answer: a }
                                  : qq,
                            ),
                          }
                        : prev,
                    );
                  }}
                />
                <NeedsCard row={row} />
              </div>

              {!row && (
                <Card className="border-dashed">
                  <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
                    <Sparkles className="size-8 text-violet-400" />
                    <p className="text-sm text-slate-600">
                      还没有该岗位的画像数据。
                    </p>
                    <p className="max-w-md text-xs text-slate-500">
                      老板请先填写人才框架,部门负责人请提交 JD 细节,智能体会
                      自动汇总三方意见。
                    </p>
                    <Button size="sm" onClick={handleResynthesize}>
                      触发首次综合
                    </Button>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </main>
      </div>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// Sub-blocks
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex items-center gap-2 py-12 text-sm text-slate-500">
        <Loader2 className="size-4 animate-spin text-blue-500" />
        加载画像中…
      </CardContent>
    </Card>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Card className="border-rose-200 bg-rose-50/60">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-sm text-rose-700">
        <AlertCircle className="size-5" />
        <span>{message}</span>
        <Button variant="outline" size="sm" onClick={onRetry}>
          重试
        </Button>
      </CardContent>
    </Card>
  );
}

function NeedsCard({ row }: { row: EmployerClarification | null }) {
  const explicit = normaliseList(row?.explicit_requirements).map((n) => n.text);
  const implicit = normaliseList(row?.implicit_requirements).map((n) => n.text);
  const must = normaliseList(row?.must_haves).map((n) => n.text);
  const nice = normaliseList(row?.nice_to_haves).map((n) => n.text);
  const groups: Array<{ label: string; items: string[]; color: string }> = [
    {
      label: "必须满足",
      items: must,
      color: "bg-rose-100 text-rose-700 border-rose-200",
    },
    {
      label: "明确要求",
      items: explicit,
      color: "bg-blue-100 text-blue-700 border-blue-200",
    },
    {
      label: "隐性诉求",
      items: implicit,
      color: "bg-violet-100 text-violet-700 border-violet-200",
    },
    {
      label: "最好具备",
      items: nice,
      color: "bg-emerald-100 text-emerald-700 border-emerald-200",
    },
  ];
  const total = groups.reduce((acc, g) => acc + g.items.length, 0);
  if (total === 0) return null;
  return (
    <Card>
      <CardContent className="space-y-3 py-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <Sparkles className="size-4 text-blue-500" />
          真实需求归纳
          <span className="ml-auto rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
            共 {total} 项
          </span>
        </h3>
        <div className="space-y-2.5">
          {groups.map((g) => (
            <section key={g.label}>
              <h4 className="text-xs font-medium text-slate-500">{g.label}</h4>
              <ul className="mt-1 flex flex-wrap gap-1.5">
                {g.items.map((t, i) => (
                  <li
                    key={i}
                    className={cn(
                      "rounded-full border px-2 py-0.5 text-[11px]",
                      g.color,
                    )}
                  >
                    {t}
                  </li>
                ))}
                {g.items.length === 0 && (
                  <li className="text-[11px] text-slate-400">—</li>
                )}
              </ul>
            </section>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// Re-export to keep tree-shaking happy.
export { cn };

// ---------------------------------------------------------------------------
// Helpers — keep in-file to avoid sprawling the api module
// ---------------------------------------------------------------------------

import { deriveStakeholderStances } from "@/lib/api-clarification";

function deriveStances(row: EmployerClarification | null) {
  return deriveStakeholderStances(row);
}
