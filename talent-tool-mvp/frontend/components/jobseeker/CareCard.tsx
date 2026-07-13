"use client";

/**
 * v9.1 — Jobseeker shared subcomponents: CareCard
 *
 * 通用关怀 / 提示卡片，用于求职者仪表盘的情绪关怀、健康提醒、休眠召回等场景。
 * 不依赖 i18n：所有文案由调用方传入（保持组件通用、可复用）。
 *
 * 特性：
 *  - 强类型 props（tone、items、dismiss、action 等变体均显式）
 *  - 可访问：`role="region"` + `aria-label`，关闭按钮带 `aria-label`
 *  - 响应式：`flex-col` 默认纵向，移动端友好
 *  - 不依赖业务合约，可单独 Storybook 预览
 */

import * as React from "react";
import { ArrowRight, Heart, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type CareCardTone = "info" | "success" | "warning" | "danger" | "calm";

export interface CareCardItem {
  /** 唯一 id，用作 React key */
  id: string;
  /** 可选图标（React node） */
  icon?: React.ReactNode;
  /** 主要文案 */
  title: string;
  /** 副文案/说明 */
  description?: string;
  /** 行尾的小标签 */
  tags?: string[];
}

export interface CareCardProps {
  /** 卡片顶部标题（同时用于 aria-label） */
  title: string;
  /** 顶部副文案 */
  description?: string;
  /** 主题色，影响背景/边框/图标色 */
  tone?: CareCardTone;
  /** 列表项（可选） */
  items?: CareCardItem[];
  /** 顶部小徽章 */
  badge?: { label: string; tone?: "default" | "secondary" | "outline" };
  /** 顶部图标，缺省时按 tone 选择兜底图标 */
  icon?: React.ReactNode;
  /** CTA 按钮文案 */
  actionLabel?: string;
  /** CTA 点击回调 */
  onAction?: () => void;
  /** 是否可关闭（显示右上角 ×） */
  dismissible?: boolean;
  /** 关闭回调 */
  onDismiss?: () => void;
  /** 自定义 className */
  className?: string;
  /** 自定义内容（渲染在 items 之后、CTA 之前） */
  children?: React.ReactNode;
}

const TONE_BORDER: Record<CareCardTone, string> = {
  info: "border-sky-200/70 bg-sky-50/40 dark:bg-sky-950/20",
  success: "border-emerald-200/70 bg-emerald-50/40 dark:bg-emerald-950/20",
  warning: "border-amber-200/70 bg-amber-50/40 dark:bg-amber-950/20",
  danger: "border-rose-200/70 bg-rose-50/40 dark:bg-rose-950/20",
  calm: "border-indigo-200/70 bg-indigo-50/40 dark:bg-indigo-950/20",
};

const TONE_ICON: Record<CareCardTone, string> = {
  info: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
  success: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  warning: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  danger: "bg-rose-500/15 text-rose-600 dark:text-rose-400",
  calm: "bg-indigo-500/15 text-indigo-600 dark:text-indigo-400",
};

export function CareCard({
  title,
  description,
  tone = "calm",
  items,
  badge,
  icon,
  actionLabel,
  onAction,
  dismissible = false,
  onDismiss,
  className,
  children,
}: CareCardProps) {
  const fallbackIcon =
    tone === "danger" ? <Heart className="h-5 w-5" aria-hidden="true" /> : null;
  const renderedIcon = icon ?? fallbackIcon;

  return (
    <Card
      role="region"
      aria-label={title}
      className={cn("border", TONE_BORDER[tone], className)}
    >
      <CardContent className="space-y-3 p-4">
        <header className="flex items-start gap-3">
          {renderedIcon ? (
            <span
              aria-hidden="true"
              className={cn(
                "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
                TONE_ICON[tone]
              )}
            >
              {renderedIcon}
            </span>
          ) : null}
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold leading-tight">{title}</h3>
              {badge ? (
                <Badge variant={badge.tone ?? "secondary"} className="text-xs">
                  {badge.label}
                </Badge>
              ) : null}
            </div>
            {description ? (
              <p className="text-xs text-muted-foreground leading-relaxed">
                {description}
              </p>
            ) : null}
          </div>
          {dismissible ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="关闭关怀卡片"
              onClick={onDismiss}
              className="-mt-1 -mr-1 shrink-0"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Button>
          ) : null}
        </header>

        {items && items.length > 0 ? (
          <ul className="space-y-2">
            {items.map((item) => (
              <li
                key={item.id}
                className="flex items-start gap-3 rounded-md bg-background/60 p-2"
              >
                {item.icon ? (
                  <span
                    aria-hidden="true"
                    className="mt-0.5 shrink-0 text-muted-foreground"
                  >
                    {item.icon}
                  </span>
                ) : null}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium leading-snug">{item.title}</p>
                  {item.description ? (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {item.description}
                    </p>
                  ) : null}
                </div>
                {item.tags && item.tags.length > 0 ? (
                  <div className="flex shrink-0 flex-wrap gap-1">
                    {item.tags.map((t) => (
                      <Badge
                        key={t}
                        variant="outline"
                        className="text-[10px] font-normal"
                      >
                        {t}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}

        {children}

        {actionLabel && onAction ? (
          <div className="flex justify-end pt-1">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={onAction}
              className="gap-1 text-primary hover:text-primary"
            >
              {actionLabel}
              <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default CareCard;
