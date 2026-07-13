"use client";

/**
 * v9.1 — Jobseeker shared subcomponents: ProactiveBanner
 *
 * 仪表盘顶部的「主动推送」通知横幅，用于召回、状态变化、新功能上线提示。
 * 通用：标题、副文案、CTA、关闭按钮全部由调用方控制。
 *
 * 特性：
 *  - 强类型 tone / 自定义 icon / 可关闭
 *  - 通用 props：不依赖业务合约
 *  - 响应式：移动端纵向堆叠；>=sm 横排
 *  - 可访问：role="status" / role="alert" 可选；CTA 与关闭按钮均带 aria-label
 */

import * as React from "react";
import { X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type ProactiveBannerTone =
  | "info"
  | "success"
  | "warning"
  | "danger"
  | "calm";

export interface ProactiveBannerProps {
  /** 标题（也用于 aria-label 默认值） */
  title: string;
  /** 副文案 */
  description?: string;
  /** 可选图标；缺省时按 tone 兜底 */
  icon?: React.ReactNode;
  /** 主题色 */
  tone?: ProactiveBannerTone;
  /** CTA 文案 */
  actionLabel?: string;
  /** CTA 回调 */
  onAction?: () => void;
  /** 二级文案（次要链接） */
  secondaryLabel?: string;
  /** 二级回调 */
  onSecondary?: () => void;
  /** 右侧小徽章（如 "刚刚" / "测试中"） */
  badge?: string;
  /** 是否可关闭 */
  dismissible?: boolean;
  /** 关闭回调 */
  onDismiss?: () => void;
  /** 重要性，alert 为强提示；缺省为 status */
  importance?: "status" | "alert";
  /** 自定义 className */
  className?: string;
}

const TONE_BG: Record<ProactiveBannerTone, string> = {
  info: "border-sky-200/80 bg-sky-50/80 dark:bg-sky-950/30",
  success: "border-emerald-200/80 bg-emerald-50/80 dark:bg-emerald-950/30",
  warning: "border-amber-200/80 bg-amber-50/80 dark:bg-amber-950/30",
  danger: "border-rose-200/80 bg-rose-50/80 dark:bg-rose-950/30",
  calm: "border-indigo-200/80 bg-indigo-50/80 dark:bg-indigo-950/30",
};

const TONE_ICON: Record<ProactiveBannerTone, string> = {
  info: "bg-sky-500/15 text-sky-600 dark:text-sky-300",
  success: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300",
  warning: "bg-amber-500/15 text-amber-600 dark:text-amber-300",
  danger: "bg-rose-500/15 text-rose-600 dark:text-rose-300",
  calm: "bg-indigo-500/15 text-indigo-600 dark:text-indigo-300",
};

const TONE_CTA: Record<ProactiveBannerTone, string> = {
  info: "bg-sky-500 text-white hover:bg-sky-600",
  success: "bg-emerald-500 text-white hover:bg-emerald-600",
  warning: "bg-amber-500 text-white hover:bg-amber-600",
  danger: "bg-rose-500 text-white hover:bg-rose-600",
  calm: "bg-indigo-500 text-white hover:bg-indigo-600",
};

export function ProactiveBanner({
  title,
  description,
  icon,
  tone = "info",
  actionLabel,
  onAction,
  secondaryLabel,
  onSecondary,
  badge,
  dismissible = false,
  onDismiss,
  importance = "status",
  className,
}: ProactiveBannerProps) {
  return (
    <div
      role={importance}
      aria-label={title}
      className={cn(
        "relative flex flex-col gap-3 rounded-xl border p-3 sm:flex-row sm:items-center sm:p-4",
        TONE_BG[tone],
        className
      )}
    >
      {icon ? (
        <span
          aria-hidden="true"
          className={cn(
            "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
            TONE_ICON[tone]
          )}
        >
          {icon}
        </span>
      ) : null}

      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold leading-tight">{title}</h3>
          {badge ? (
            <Badge variant="outline" className="text-[10px] font-normal">
              {badge}
            </Badge>
          ) : null}
        </div>
        {description ? (
          <p className="text-xs text-muted-foreground leading-relaxed">
            {description}
          </p>
        ) : null}
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-2 sm:flex-nowrap">
        {secondaryLabel && onSecondary ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={onSecondary}
            className="text-xs"
          >
            {secondaryLabel}
          </Button>
        ) : null}
        {actionLabel && onAction ? (
          <Button
            type="button"
            size="sm"
            onClick={onAction}
            className={cn("text-xs", TONE_CTA[tone])}
          >
            {actionLabel}
          </Button>
        ) : null}
        {dismissible ? (
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            aria-label="关闭主动推送"
            onClick={onDismiss}
            className="text-muted-foreground"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export default ProactiveBanner;
