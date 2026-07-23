"use client";

/**
 * T6106 — Match result card (硬条件匹配结果卡).
 *
 * Renders one candidate↔role hard-condition match result produced by the
 * T6105 HardConditionFilter. 甲方合同要求 4 sections:
 *
 *   1. 分数  — 0-100 progress bar (绿 ≥75 / 黄 50-74 / 红 <50)
 *   2. 理由  — match_reasons (技能匹配 5/5, 学历满足, 薪资符合…)
 *   3. 缺口  — skill_gaps (缺 K8s 经验, 英语 B2 以下…)
 *   4. 风险  — risks (到岗不确定 / 薪资期望偏高…)
 *
 * 甲方要求 "不淘汰只排序": 即便有缺口/风险也照常展示, 用颜色与标签
 * 让 HR 一眼看出哪些是硬伤. passed_hard=false 时顶部加一条 "硬条件未达标"
 * 提示条, 但卡片仍保留.
 */
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Markdown } from "@/components/shared";

export interface HardConditionDetail {
  name: string;
  satisfied: boolean;
  detail: Record<string, unknown>;
}

export interface MatchResultItem {
  candidate_id?: string | null;
  role_id?: string | null;
  match_score: number; // 0-100
  match_reasons: string[];
  skill_gaps: string[];
  risks: string[];
  hard_conditions?: Record<string, HardConditionDetail>;
  high_priority?: Record<string, number>;
  passed_hard?: boolean;
  /** 可选: 候选人展示名 (列表场景由上游补充) */
  candidate_name?: string;
  candidate_title?: string;
}

export interface MatchResultCardProps {
  result: MatchResultItem;
  rank?: number;
  onView?: (candidateId: string) => void;
}

type ScoreTone = "green" | "amber" | "rose";

function scoreTone(score: number): ScoreTone {
  if (score >= 75) return "green";
  if (score >= 50) return "amber";
  return "rose";
}

const TONE_PROGRESS: Record<ScoreTone, string> = {
  green: "[&>*]:bg-emerald-500",
  amber: "[&>*]:bg-amber-500",
  rose: "[&>*]:bg-rose-500",
};

const TONE_TEXT: Record<ScoreTone, string> = {
  green: "text-emerald-600",
  amber: "text-amber-600",
  rose: "text-rose-600",
};

const TONE_LABEL: Record<ScoreTone, string> = {
  green: "匹配度高",
  amber: "匹配度中",
  rose: "匹配度低",
};

export function MatchResultCard({
  result: r,
  rank,
  onView,
}: MatchResultCardProps) {
  const tone = scoreTone(r.match_score);
  const passedHard = r.passed_hard ?? true;

  // 从 hard_conditions 提取 "技能匹配 X/Y" 兜底展示 (若 reasons 为空)
  const skillDetail = r.hard_conditions?.skill?.detail as
    | { matched?: unknown[]; required?: unknown[] }
    | undefined;
  const matchedN = skillDetail?.matched?.length ?? 0;
  const requiredN = skillDetail?.required?.length ?? 0;

  return (
    <Card
      className={`h-full transition hover:shadow-md ${
        passedHard ? "hover:border-emerald-300" : "border-amber-300"
      }`}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="flex flex-wrap items-center gap-2 text-base">
              {rank != null && (
                <Badge variant="secondary" className="font-normal">
                  #{rank}
                </Badge>
              )}
              <span className="truncate">
                {r.candidate_name || "候选人"}
              </span>
              {r.candidate_title && (
                <span className="text-sm font-normal text-slate-500">
                  {r.candidate_title}
                </span>
              )}
            </CardTitle>
            {!passedHard && (
              <p className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-amber-600">
                ⚠ 硬条件未达标 (仍保留, 供参考)
              </p>
            )}
          </div>
          <div className="shrink-0 text-right">
            <div className={`text-2xl font-bold ${TONE_TEXT[tone]}`}>
              {r.match_score}
              <span className="text-xs text-slate-400">/100</span>
            </div>
            <p className={`text-[11px] ${TONE_TEXT[tone]}`}>
              {TONE_LABEL[tone]}
            </p>
          </div>
        </div>

        {/* 分数 progress */}
        <div className="mt-2">
          <Progress
            value={r.match_score}
            aria-label={`匹配分数 ${r.match_score}`}
            className={TONE_PROGRESS[tone]}
          />
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* 理由 */}
        <Section title="匹配理由" tone="emerald">
          {r.match_reasons.length > 0 ? (
            <ul className="list-disc space-y-0.5 pl-4 text-sm text-slate-600">
              {r.match_reasons.map((reason, i) => (
                <li key={i}>
                  <Markdown size="sm">{reason}</Markdown>
                </li>
              ))}
            </ul>
          ) : requiredN > 0 ? (
            <p className="text-sm text-slate-500">
              技能匹配 {matchedN}/{requiredN}
            </p>
          ) : (
            <p className="text-sm text-slate-400">综合画像相近</p>
          )}
        </Section>

        {/* 缺口 */}
        <Section title="能力缺口" tone="amber">
          {r.skill_gaps.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {r.skill_gaps.map((g, i) => (
                <Badge key={i} variant="outline" className="text-amber-700">
                  {g}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">无明显缺口</p>
          )}
        </Section>

        {/* 风险 */}
        <Section title="风险提示" tone="rose">
          {r.risks.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {r.risks.map((risk, i) => (
                <Badge key={i} variant="destructive">
                  {risk}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">无风险标记</p>
          )}
        </Section>

        {onView && r.candidate_id && (
          <div className="pt-1">
            <button
              type="button"
              onClick={() => onView(r.candidate_id!)}
              className="text-sm text-sky-600 hover:underline"
            >
              查看候选人 →
            </button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Section({
  title,
  tone,
  children,
}: {
  title: string;
  tone: "emerald" | "amber" | "rose";
  children: React.ReactNode;
}) {
  const toneClass: Record<typeof tone, string> = {
    emerald: "text-emerald-600",
    amber: "text-amber-600",
    rose: "text-rose-600",
  };
  return (
    <div>
      <p className={`mb-1 text-xs font-medium ${toneClass[tone]}`}>{title}</p>
      {children}
    </div>
  );
}
