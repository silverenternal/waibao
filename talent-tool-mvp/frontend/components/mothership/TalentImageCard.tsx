"use client";

/**
 * TalentImageCard (T602)
 *
 * Top-level card surfacing the employer-side "talent image" — the synthetic
 * profile the clarifier agent has produced for a role. Mirrors the
 * jobseeker `ProfileCard` so the two sides feel symmetric.
 *
 * Renders:
 *   - headline + summary
 *   - hard skills + soft skills chips
 *   - experience profile (key/value table)
 *   - cultural fit (key/value chips)
 *   - "last synthesised" timestamp
 *
 * Pure presentation — data flows in via props.
 */

import * as React from "react";
import {
  Sparkles,
  Wrench,
  Heart,
  Briefcase,
  Clock3,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

import { normaliseList } from "@/lib/api-clarification";
import type { EmployerClarification } from "@/lib/api-clarification";

export interface TalentImageCardProps {
  clarification: EmployerClarification | null;
  loading?: boolean;
  roleTitle?: string;
  className?: string;
}

export function TalentImageCard({
  clarification,
  loading,
  roleTitle,
  className,
}: TalentImageCardProps) {
  const image = clarification?.talent_image;
  const hardSkills = [
    ...(image?.hard_skills ?? []),
    ...(clarification?.hard_skills ?? []),
  ];
  const softSkills = [
    ...(image?.soft_skills ?? []),
    ...(clarification?.soft_skills ?? []),
  ];
  const experience = image?.experience_profile ?? clarification?.experience_profile ?? {};
  const cultural = image?.cultural_fit ?? clarification?.cultural_fit ?? {};
  const summary = (image?.summary ?? "").trim();

  if (loading) {
    return (
      <Card className={className}>
        <CardHeader>
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="mt-2 h-3 w-1/3" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <div className="flex gap-2">
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-12 rounded-full" />
            <Skeleton className="h-5 w-20 rounded-full" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!clarification) {
    return (
      <Card className={cn("border-dashed", className)}>
        <CardContent className="flex flex-col items-center gap-2 py-10 text-center text-sm text-slate-500">
          <Sparkles className="size-8 text-violet-400" />
          <p>尚未生成用人方人才画像</p>
          <p className="max-w-sm text-xs text-slate-500">
            老板 + HR + 部门负责人 三方提交完成后,智能体会自动综合。
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="size-4 text-violet-500" />
              岗位人才画像
              {roleTitle && (
                <Badge variant="outline" className="text-[10px]">
                  {roleTitle}
                </Badge>
              )}
            </CardTitle>
            <CardDescription className="mt-1 line-clamp-3">
              {summary || "智能体尚未生成总结,请补充更多岗位细节。"}
            </CardDescription>
          </div>
          {clarification.last_synthesized_at && (
            <span className="inline-flex shrink-0 items-center gap-1 text-[10px] text-slate-500">
              <Clock3 className="size-3" />
              {new Date(clarification.last_synthesized_at).toLocaleString(
                "en-GB",
                { dateStyle: "medium", timeStyle: "short" },
              )}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {hardSkills.length > 0 && (
          <SkillRow
            icon={<Wrench className="size-3.5 text-blue-500" />}
            label="硬技能"
            items={hardSkills}
            color="bg-blue-100 text-blue-700 border-blue-200"
          />
        )}
        {softSkills.length > 0 && (
          <SkillRow
            icon={<Heart className="size-3.5 text-rose-500" />}
            label="软技能"
            items={softSkills}
            color="bg-rose-100 text-rose-700 border-rose-200"
          />
        )}

        {Object.keys(experience).length > 0 && (
          <section>
            <h4 className="mb-1.5 inline-flex items-center gap-1 text-xs font-medium text-slate-600">
              <Briefcase className="size-3.5 text-emerald-500" />
              经验画像
            </h4>
            <dl className="grid gap-1 rounded-md border border-slate-200 bg-slate-50/60 p-2 text-xs sm:grid-cols-2">
              {Object.entries(experience).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-2">
                  <dt className="text-slate-500">{k}</dt>
                  <dd className="font-medium text-slate-800">{String(v)}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        {Object.keys(cultural).length > 0 && (
          <section>
            <h4 className="mb-1.5 inline-flex items-center gap-1 text-xs font-medium text-slate-600">
              <Heart className="size-3.5 text-violet-500" />
              文化匹配
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(cultural).map(([k, v]) => (
                <span
                  key={k}
                  className="rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[11px] text-violet-700"
                >
                  <span className="font-medium">{k}</span>
                  <span className="mx-1 text-violet-400">·</span>
                  <span>{String(v)}</span>
                </span>
              ))}
            </div>
          </section>
        )}
      </CardContent>
    </Card>
  );
}

function SkillRow({
  icon,
  label,
  items,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  items: string[];
  color: string;
}) {
  const list = normaliseList(items).map((n) => n.text);
  const unique = Array.from(new Set(list));
  return (
    <section>
      <h4 className="mb-1.5 inline-flex items-center gap-1 text-xs font-medium text-slate-600">
        {icon}
        {label}
      </h4>
      <div className="flex flex-wrap gap-1.5">
        {unique.map((s) => (
          <Badge key={s} variant="outline" className={color}>
            {s}
          </Badge>
        ))}
      </div>
    </section>
  );
}
