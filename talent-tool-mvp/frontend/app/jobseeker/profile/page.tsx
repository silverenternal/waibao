"use client";

/**
 * 综合画像页 (T202).
 *
 * Layout (top → bottom):
 *   ┌─ Header (name + 重新综合) ─────────────────────────┐
 *   ├─ Left column (lg:col-span-2) ─────  Right column ─┤
 *   │  ProfileCompleteness             ContradictionList │
 *   │  ProfileCard                                        │
 *   │  NeedsList                                          │
 *   │  FollowUpQuestions                                  │
 *   └─────────────────────────────────────────────────────┘
 *
 * Data flow:
 *   1. On mount → fetch /api/users/me + /api/clarification/my-profile
 *   2. "重新综合" → POST /api/clarification/synthesize, then refetch the row
 *   3. FollowUp answer → optimistic mark + persist as a journal entry so
 *      the next synth pass absorbs it.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  RefreshCcw,
  Sparkles,
  Loader2,
  AlertCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import {
  clarificationApi,
  type CandidateClarification,
  type FollowUpQuestion,
} from "@/lib/api-clarification";

type ProfileFieldStatus = "filled" | "empty" | "weak";
interface ProfileField {
  key: string;
  label: string;
  hint: string;
  status: ProfileFieldStatus;
  weight: number;
}
import type { User } from "@/contracts/canonical";
import {
  ProfileCompleteness,
} from "@/components/ProfileCompleteness";
import { ProfileCard } from "@/components/ProfileCard";
import { NeedsList } from "@/components/NeedsList";
import { ContradictionList } from "@/components/ContradictionBadge";
import { FollowUpQuestions } from "@/components/FollowUpQuestions";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type Status = "loading" | "ready" | "empty" | "error";

export default function ProfilePage() {
  const router = useRouter();
  const [me, setMe] = React.useState<User | null>(null);
  const [clarification, setClarification] =
    React.useState<CandidateClarification | null>(null);
  const [status, setStatus] = React.useState<Status>("loading");
  const [error, setError] = React.useState<string | null>(null);
  const [resynthesizing, setResynthesizing] = React.useState(false);

  const load = React.useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const [user, row] = await Promise.all([
        api.users.me().catch(() => null),
        clarificationApi.myProfile().catch(() => ({} as CandidateClarification)),
      ]);
      setMe(user);
      setClarification(row && Object.keys(row).length > 0 ? row : null);
      setStatus(row && Object.keys(row).length > 0 ? "ready" : "empty");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
      setStatus("error");
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  async function handleResynthesize() {
    setResynthesizing(true);
    try {
      await clarificationApi.synthesize();
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "综合失败");
    } finally {
      setResynthesizing(false);
    }
  }

  async function handleAnswerFollowUp(
    question: FollowUpQuestion,
    answer: string,
    index: number,
  ) {
    // Optimistic update so the card collapses immediately.
    setClarification((prev) => {
      if (!prev) return prev;
      const next = [...(prev.follow_up_questions ?? [])];
      next[index] = { ...next[index]!, answered: true, answer };
      return { ...prev, follow_up_questions: next };
    });

    // Persist the answer as a journal entry so the next synthesize pass
    // picks it up. Failures are surfaced as a toast (the optimistic state
    // stays since the user can still see what they wrote).
    try {
      const token =
        typeof window !== "undefined"
          ? window.localStorage.getItem("sb_token") ?? ""
          : "";
      await fetch("/api/journal", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          content: `[追问回答] ${question.question}\n${answer}`,
          mood_score: 0,
        }),
      });
    } catch {
      /* swallow — the answer is already visible inline */
    }
  }

  const fullName =
    me ? `${me.first_name ?? ""} ${me.last_name ?? ""}`.trim() || me.email : "我";

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      {/* Header */}
      <header className="sticky top-0 z-20 border-b bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => router.push("/jobseeker")}
              aria-label="返回"
            >
              <ArrowLeft className="size-4" />
            </Button>
            <div>
              <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
                <Sparkles className="size-5 text-violet-500" />
                我的综合画像
              </h1>
              <p className="text-xs text-muted-foreground">
                智能体综合 简历 · 日记 · 对话 · 情绪 多源数据
              </p>
            </div>
          </div>

          <Button
            onClick={handleResynthesize}
            disabled={resynthesizing || status === "loading"}
            className="gap-2"
          >
            {resynthesizing ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCcw className="size-4" />
            )}
            {resynthesizing ? "综合中..." : "重新综合"}
          </Button>
        </div>
      </header>

      {/* Body */}
      <main className="mx-auto max-w-6xl px-6 py-6">
        {status === "loading" && <LoadingState />}
        {status === "error" && <ErrorState message={error} onRetry={load} />}

        {(status === "ready" || status === "empty") && (
          <div className="grid gap-6 lg:grid-cols-3">
            {/* Left column */}
            <div className="space-y-6 lg:col-span-2">
              <ProfileCompleteness
                fields={buildCompletenessFields(me, clarification)}
                title="档案完整度"
              />

              <ProfileCard
                name={fullName}
                headline={me?.email ?? null}
                location={null}
                seniority={null}
                availability={null}
                clarification={clarification}
                lastSynthesizedAt={clarification?.last_synthesized_at ?? null}
              />

              <NeedsList
                must_haves={clarification?.must_haves}
                nice_to_haves={clarification?.nice_to_haves}
                deal_breakers={clarification?.deal_breakers}
              />
            </div>

            {/* Right column */}
            <div className="space-y-6">
              <FollowUpQuestions
                questions={clarification?.follow_up_questions ?? []}
                onAnswer={handleAnswerFollowUp}
              />

              <ContradictionList
                contradictions={clarification?.conflict_flags ?? []}
              />

              <ReflectionCard clarification={clarification} />
            </div>
          </div>
        )}

        {status === "empty" && <EmptyState onSynthesize={handleResynthesize} />}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-blocks
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        加载画像中...
      </CardContent>
    </Card>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string | null;
  onRetry: () => void;
}) {
  return (
    <Card className="border-rose-200 bg-rose-50/60">
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <AlertCircle className="size-8 text-rose-500" />
        <p className="text-sm text-rose-700">{message ?? "加载失败,请稍后再试。"}</p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          重试
        </Button>
      </CardContent>
    </Card>
  );
}

function EmptyState({ onSynthesize }: { onSynthesize: () => void }) {
  return (
    <Card className="mt-6 border-dashed">
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <Sparkles className="size-8 text-violet-400" />
        <h3 className="text-base font-medium">还没有画像数据</h3>
        <p className="max-w-sm text-sm text-muted-foreground">
          点击下方按钮,智能体会综合你的简历、日记、对话和情绪,生成第一份画像和真实需求清单。
        </p>
        <Button onClick={onSynthesize} className="mt-2 gap-2">
          <Sparkles className="size-4" />
          生成我的画像
        </Button>
      </CardContent>
    </Card>
  );
}

function ReflectionCard({
  clarification,
}: {
  clarification: CandidateClarification | null;
}) {
  // The reflection payload is currently only attached to the synthesize
  // response (`synthesis.reflection`). When the row is persisted, only the
  // structured fields survive — so this card stays neutral unless the row
  // carries reflection data (future-proofing).
  const issues = React.useMemo(() => {
    const r = (clarification as unknown as { reflection?: { issues?: string[] } })
      ?.reflection;
    return r?.issues ?? [];
  }, [clarification]);

  if (issues.length === 0) return null;

  return (
    <Card>
      <CardContent className="space-y-2 pt-4">
        <h4 className="text-sm font-medium text-foreground">智能体反思</h4>
        <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
          {issues.map((it, i) => (
            <li key={i}>{it}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Translate the persisted clarification row into the `ProfileField[]`
 * shape that `ProfileCompleteness` expects.
 */
function buildCompletenessFields(
  user: User | null,
  clarification: CandidateClarification | null,
): ProfileField[] {
  const hasSynthesis = !!clarification?.profile_synthesis?.summary;
  const hasMustHaves = (clarification?.must_haves ?? []).length > 0;
  const hasDealBreakers = (clarification?.deal_breakers ?? []).length > 0;
  const hasSkills =
    Array.isArray(clarification?.profile_synthesis?.explicit_skills) &&
    (clarification?.profile_synthesis?.explicit_skills?.length ?? 0) > 0;
  const openQuestions = (clarification?.follow_up_questions ?? []).filter(
    (q) => !q.answered,
  ).length;

  const completeness = clarification?.info_completeness ?? 0;

  function tier(filled: boolean, weak = false): "filled" | "empty" | "weak" {
    if (filled) return "filled";
    return weak ? "weak" : "empty";
  }

  return [
    {
      key: "identity",
      label: "基础信息",
      hint: user?.email ? `${user.email}` : "未填写邮箱",
      status: tier(!!user?.email && !!user?.first_name),
      weight: 1,
    },
    {
      key: "summary",
      label: "画像总结",
      hint: hasSynthesis
        ? "智能体已经综合出核心结论"
        : "点击「重新综合」让智能体生成",
      status: tier(hasSynthesis, completeness > 0.2 && !hasSynthesis),
      weight: 2,
    },
    {
      key: "skills",
      label: "技能云",
      hint: hasSkills ? "已识别显性技能" : "上传简历可自动提取",
      status: tier(hasSkills, !hasSkills && completeness > 0.4),
      weight: 2,
    },
    {
      key: "must_haves",
      label: "必须满足的需求",
      hint: hasMustHaves ? "已列出核心需求" : "继续对话,智能体会逐步识别",
      status: tier(hasMustHaves, !hasMustHaves && completeness > 0.3),
      weight: 2,
    },
    {
      key: "deal_breakers",
      label: "明确不能接受",
      hint: hasDealBreakers ? "已识别底线" : "聊聊绝对不能妥协的事",
      status: tier(hasDealBreakers, false),
      weight: 1.5,
    },
    {
      key: "follow_ups",
      label: "智能体追问",
      hint:
        openQuestions > 0
          ? `还有 ${openQuestions} 个待回答`
          : "暂无追问",
      status: tier(openQuestions === 0, openQuestions > 0),
      weight: 1,
    },
  ];
}