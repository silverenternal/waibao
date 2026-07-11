"use client";

/**
 * ProfileCard — visual summary of the candidate's synthesised profile.
 *
 * Sections (top → bottom):
 *   1. Avatar + name + headline (Location · Seniority · Availability)
 *   2. Profile-synthesis one-liner (when the agent has produced one)
 *   3. Skill cloud — explicit skills (front of mind) and implicit traits
 *   4. Value orientation + career interests
 *
 * Skills are pulled from `profile_synthesis.explicit_skills` /
 * `implicit_traits` / `value_orientation` / `career_interests` — the LLM
 * may emit either plain strings or `{value, confidence, ...}` objects,
 * so we normalise them through `normaliseList()`.
 */

import * as React from "react";
import {
  Briefcase,
  Compass,
  Heart,
  MapPin,
  Sparkles,
  Timer,
  User2,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  normaliseList,
  type CandidateClarification,
  type NormalisedItem,
  type ProfileSynthesis,
} from "@/lib/api-clarification";
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const SENIORITY_LABEL: Record<string, string> = {
  junior: "初级",
  mid: "中级",
  senior: "高级",
  lead: "资深",
  principal: "专家",
};

const AVAILABILITY_LABEL: Record<string, string> = {
  immediate: "立即到岗",
  "1_month": "1 个月内",
  "3_months": "3 个月内",
  not_looking: "暂不跳槽",
};

function summaryText(s: ProfileSynthesis | undefined): string | null {
  const raw = s?.summary;
  if (!raw) return null;
  if (typeof raw === "string") return raw;
  if (typeof raw === "object" && raw !== null) {
    const obj = raw as unknown as Record<string, unknown>;
    const v = (obj.value ?? obj.text) as string | undefined;
    return v ?? null;
  }
  return null;
}

function confidenceTone(c: number | undefined): string {
  if (c == null) return "bg-slate-100 text-slate-600";
  if (c >= 0.8) return "bg-emerald-100 text-emerald-700";
  if (c >= 0.55) return "bg-amber-100 text-amber-700";
  return "bg-rose-100 text-rose-700";
}

export interface ProfileCardProps {
  /** Basic identity. When `profile_synthesis` exists we still show this header. */
  name: string;
  headline?: string | null;
  avatarUrl?: string | null;
  location?: string | null;
  seniority?: string | null;
  availability?: string | null;
  /** Full clarification row — drives the rest of the card. */
  clarification?: CandidateClarification | null;
  /** Optional override for the overall confidence score shown in the footer. */
  confidenceScore?: number | null;
  /** Last synthesised timestamp (ISO) shown in the footer. */
  lastSynthesizedAt?: string | null;
  className?: string;
}

export function ProfileCard({
  name,
  headline,
  avatarUrl,
  location,
  seniority,
  availability,
  clarification,
  confidenceScore,
  lastSynthesizedAt,
  className,
}: ProfileCardProps) {
  const synthesis = clarification?.profile_synthesis;
  const summary = summaryText(synthesis);

  const explicitSkills = normaliseList(synthesis?.explicit_skills);
  const implicitTraits = normaliseList(synthesis?.implicit_traits);
  const values = normaliseList(synthesis?.value_orientation);
  const interests = normaliseList(synthesis?.career_interests);

  const overallConfidence =
    confidenceScore ??
    clarification?.confidence_score ??
    null;

  const initials = React.useMemo(() => {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return "?";
    if (parts.length === 1) return parts[0]!.slice(0, 1).toUpperCase();
    return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
  }, [name]);

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="border-b">
        <div className="flex items-start gap-4">
          <Avatar size="lg" className="size-16 ring-2 ring-background shadow">
            {avatarUrl ? <AvatarImage src={avatarUrl} alt={name} /> : null}
            <AvatarFallback className="text-lg font-medium">
              {initials}
            </AvatarFallback>
          </Avatar>

          <div className="min-w-0 flex-1 space-y-1">
            <CardTitle className="flex items-center gap-2 text-lg">
              <User2 className="size-4 text-muted-foreground" />
              <span className="truncate">{name || "未命名用户"}</span>
            </CardTitle>
            {headline && (
              <p className="text-sm text-muted-foreground line-clamp-2">{headline}</p>
            )}
            <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
              {location && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="size-3" />
                  {location}
                </span>
              )}
              {seniority && (
                <span className="inline-flex items-center gap-1">
                  <Briefcase className="size-3" />
                  {SENIORITY_LABEL[seniority] ?? seniority}
                </span>
              )}
              {availability && (
                <span className="inline-flex items-center gap-1">
                  <Timer className="size-3" />
                  {AVAILABILITY_LABEL[availability] ?? availability}
                </span>
              )}
            </div>
          </div>

          {overallConfidence != null && (
            <Badge
              variant="outline"
              className={cn("shrink-0 text-[10px]", confidenceTone(overallConfidence))}
              title={`整体置信度 ${Math.round(overallConfidence * 100)}%`}
            >
              置信度 {Math.round(overallConfidence * 100)}%
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-5 pt-4">
        {summary ? (
          <div className="rounded-xl border bg-gradient-to-br from-blue-50/70 to-violet-50/60 p-4">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-blue-700">
              <Sparkles className="size-3.5" />
              智能体总结
            </div>
            <p className="text-sm leading-relaxed text-foreground/90">{summary}</p>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
            还没有画像总结 — 点击右下角"重新综合"让智能体跑一遍。
          </div>
        )}

        <SkillCloud
          title="技能云"
          icon={<Sparkles className="size-3.5 text-blue-500" />}
          items={explicitSkills}
          emptyHint="尚未提取到显性技能 — 上传简历或跟智能体聊几句。"
          accent="border-blue-200 bg-blue-50 text-blue-700"
        />

        <SkillCloud
          title="性格特质"
          icon={<Heart className="size-3.5 text-rose-500" />}
          items={implicitTraits}
          emptyHint="性格特质还没出现 — 多分享一些工作中的偏好和习惯。"
          accent="border-rose-200 bg-rose-50 text-rose-700"
        />

        {values.length > 0 && (
          <SkillCloud
            title="价值观"
            icon={<Compass className="size-3.5 text-amber-500" />}
            items={values}
            emptyHint=""
            accent="border-amber-200 bg-amber-50 text-amber-700"
          />
        )}

        {interests.length > 0 && (
          <SkillCloud
            title="职业兴趣"
            icon={<Compass className="size-3.5 text-violet-500" />}
            items={interests}
            emptyHint=""
            accent="border-violet-200 bg-violet-50 text-violet-700"
          />
        )}

        {lastSynthesizedAt && (
          <p className="pt-1 text-[10px] uppercase tracking-wide text-muted-foreground">
            最后综合 · {formatRelative(lastSynthesizedAt)}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function SkillCloud({
  title,
  icon,
  items,
  emptyHint,
  accent,
}: {
  title: string;
  icon: React.ReactNode;
  items: NormalisedItem[];
  emptyHint: string;
  accent: string;
}) {
  return (
    <section className="space-y-2">
      <h4 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {icon}
        {title}
        <span className="ml-1 text-[10px] font-normal normal-case text-muted-foreground/70">
          {items.length > 0 ? `${items.length} 项` : ""}
        </span>
      </h4>
      {items.length === 0 ? (
        emptyHint ? (
          <p className="rounded-lg border border-dashed bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            {emptyHint}
          </p>
        ) : null
      ) : (
        <ul className="flex flex-wrap gap-2">
          {items.map((item, i) => (
            <li key={`${title}-${i}-${item.text}`} className="group relative">
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium",
                  accent,
                )}
              >
                {item.text}
                {item.confidence !== undefined && (
                  <span className="opacity-60 text-[10px]">
                    {Math.round(item.confidence * 100)}%
                  </span>
                )}
              </span>
              {item.reasoning && (
                <div
                  className="pointer-events-none absolute left-1/2 top-full z-20 mt-2 hidden w-64 -translate-x-1/2 rounded-lg border bg-popover p-2 text-xs text-popover-foreground shadow-md group-hover:block"
                  role="tooltip"
                >
                  {item.reasoning}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function formatRelative(iso: string): string {
  try {
    const d = new Date(iso);
    const diff = Date.now() - d.getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return "刚刚";
    if (m < 60) return `${m} 分钟前`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h} 小时前`;
    const days = Math.floor(h / 24);
    if (days < 7) return `${days} 天前`;
    return d.toLocaleDateString("zh-CN");
  } catch {
    return iso;
  }
}