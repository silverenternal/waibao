"use client";

/**
 * v9.1 — Jobseeker shared subcomponents: AIRecommendations
 *
 * 显示 AI 为求职者推荐的岗位/机会列表，每项附带匹配分 + 推荐理由。
 * 通用：标题/空状态文案/CTA 均由调用方传入。
 *
 * 特性：
 *  - 强类型 recommendations 数组
 *  - 通用：可选 onViewAll 与 viewAllLabel
 *  - 响应式：移动端单列；平板及以上两列
 *  - 可访问：列表 role + 卡片 role="article"
 */

import * as React from "react";
import {
  Briefcase,
  ChevronRight,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type RecommendationTone = "warm" | "career" | "growth";

export interface AIRecommendation {
  /** 唯一 id */
  id: string;
  /** 标题（如岗位名 / 机会标题） */
  title: string;
  /** 公司/机构名 */
  company?: string;
  /** 0–100 的匹配分 */
  matchScore?: number;
  /** 推荐理由（每条一行） */
  reasons: string[];
  /** 行尾标签 */
  tags?: string[];
  /** 顶部小徽章 */
  badge?: string;
  /** CTA 文案 */
  ctaLabel?: string;
  /** CTA 链接或回调 */
  onAction?: (id: string) => void;
  href?: string;
}

export interface AIRecommendationsProps {
  /** 推荐项列表 */
  recommendations: AIRecommendation[];
  /** 区块标题 */
  title?: string;
  /** 区块副标题/简介 */
  description?: string;
  /** 主题色（影响 match 分颜色 / 图标色） */
  tone?: RecommendationTone;
  /** 查看全部按钮文案 */
  viewAllLabel?: string;
  /** 查看全部回调 */
  onViewAll?: () => void;
  /** 自定义 className */
  className?: string;
  /** 空状态文案 */
  emptyTitle?: string;
  emptyDescription?: string;
}

const TONE_ACCENT: Record<RecommendationTone, string> = {
  warm: "from-amber-500/15 to-orange-500/0",
  career: "from-sky-500/15 to-indigo-500/0",
  growth: "from-emerald-500/15 to-teal-500/0",
};

const TONE_SCORE: Record<RecommendationTone, string> = {
  warm: "text-amber-500",
  career: "text-sky-500",
  growth: "text-emerald-500",
};

export function AIRecommendations({
  recommendations,
  title = "AI 为你推荐",
  description,
  tone = "career",
  viewAllLabel = "查看全部",
  onViewAll,
  className,
  emptyTitle = "暂时还没有合适的推荐",
  emptyDescription = "完善一些简历信息，我们会重新计算匹配度。",
}: AIRecommendationsProps) {
  return (
    <section
      aria-label={title}
      className={cn("space-y-3", className)}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <Sparkles
              className={cn("h-4 w-4 shrink-0", TONE_SCORE[tone])}
              aria-hidden="true"
            />
            <h2 className="truncate text-base font-semibold">{title}</h2>
          </div>
          {description ? (
            <p className="text-xs text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {onViewAll ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={onViewAll}
            className="shrink-0 gap-1"
          >
            {viewAllLabel}
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        ) : null}
      </header>

      {recommendations.length === 0 ? (
        <EmptyState title={emptyTitle} description={emptyDescription} />
      ) : (
        <ul
          role="list"
          className="grid gap-3 sm:grid-cols-2"
        >
          {recommendations.map((rec) => (
            <li key={rec.id}>
              <RecommendationCard recommendation={rec} tone={tone} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border px-4 py-10 text-center">
      <Sparkles className="mb-2 h-6 w-6 text-muted-foreground/60" aria-hidden="true" />
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 max-w-sm text-xs text-muted-foreground">{description}</p>
    </div>
  );
}

function RecommendationCard({
  recommendation,
  tone,
}: {
  recommendation: AIRecommendation;
  tone: RecommendationTone;
}) {
  const {
    id,
    title,
    company,
    matchScore,
    reasons,
    tags,
    badge,
    ctaLabel = "查看详情",
    onAction,
    href,
  } = recommendation;

  const scoreColor =
    matchScore === undefined
      ? null
      : matchScore >= 85
      ? "text-emerald-500"
      : matchScore >= 70
      ? "text-sky-500"
      : "text-muted-foreground";

  const Wrapper: React.ElementType = href ? "a" : "div";
  const wrapperProps = href
    ? { href, "aria-label": title }
    : { "aria-label": title };

  return (
    <Wrapper
      {...wrapperProps}
      data-recommendation-id={id}
      className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <Card className="relative h-full overflow-hidden transition-all hover:shadow-md">
        <div
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute inset-0 bg-gradient-to-br opacity-70",
            TONE_ACCENT[tone]
          )}
        />
        <CardContent className="relative space-y-3 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="truncate text-sm font-semibold leading-tight">
                  {title}
                </h3>
                {badge ? (
                  <Badge variant="secondary" className="text-[10px] font-normal">
                    {badge}
                  </Badge>
                ) : null}
              </div>
              {company ? (
                <p className="flex items-center gap-1 truncate text-xs text-muted-foreground">
                  <Briefcase className="h-3 w-3 shrink-0" aria-hidden="true" />
                  <span className="truncate">{company}</span>
                </p>
              ) : null}
            </div>
            {matchScore !== undefined ? (
              <div className="shrink-0 text-right">
                <p
                  className={cn(
                    "text-lg font-semibold tabular-nums leading-none",
                    scoreColor
                  )}
                  aria-label={`匹配度 ${matchScore}`}
                >
                  {matchScore}
                </p>
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  匹配度
                </p>
              </div>
            ) : null}
          </div>

          {reasons.length > 0 ? (
            <ul className="space-y-1" role="list">
              {reasons.slice(0, 3).map((reason, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-2 text-xs text-muted-foreground"
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "mt-1.5 h-1 w-1 shrink-0 rounded-full",
                      tone === "warm"
                        ? "bg-amber-400"
                        : tone === "growth"
                        ? "bg-emerald-400"
                        : "bg-sky-400"
                    )}
                  />
                  {reason}
                </li>
              ))}
            </ul>
          ) : null}

          <div className="flex items-center justify-between gap-2 pt-1">
            <div className="flex shrink-0 flex-wrap gap-1">
              {tags?.slice(0, 3).map((t) => (
                <Badge
                  key={t}
                  variant="outline"
                  className="text-[10px] font-normal"
                >
                  {t}
                </Badge>
              ))}
            </div>
            {onAction || href ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={(e) => {
                  if (href) return; // let anchor navigation happen
                  e.preventDefault();
                  onAction?.(id);
                }}
                className="h-7 gap-1 text-xs"
              >
                {ctaLabel}
                <ChevronRight className="h-3 w-3" aria-hidden="true" />
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </Wrapper>
  );
}

export default AIRecommendations;
