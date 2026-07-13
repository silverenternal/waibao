"use client";

/**
 * v9.1 — Jobseeker shared subcomponents: QuickActions
 *
 * 仪表盘用的快速操作网格。每一项是一个 icon + label 的可点击块，
 * 支持 columns 决定栅格数，移动端默认纵向堆叠。
 *
 * 特性：
 *  - 强类型：actions 数组每一项强制 id/label/icon
 *  - 通用：可以是按钮或 a 链接（href），或纯回调（onClick）
 *  - 响应式：2/3/4 列自适应移动端
 *  - 可访问：列表语义 + aria-label
 */

import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { ArrowUpRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface QuickAction {
  /** 唯一 id */
  id: string;
  /** 按钮文案 */
  label: string;
  /** lucide-react 图标组件 */
  icon: LucideIcon;
  /** 副文案，可选 */
  description?: string;
  /** 右上角的小徽章（提示有新内容等） */
  badge?: string;
  /** 链接（如有，渲染为 <a>） */
  href?: string;
  /** 点击回调（无 href 时使用） */
  onClick?: (id: string) => void;
  /** 禁用 */
  disabled?: boolean;
}

export interface QuickActionsProps {
  /** 行动列表 */
  actions: QuickAction[];
  /** 列数，移动端自动 2 列；桌面下：columns=2 → 2 列，=4 → 4 列 */
  columns?: 2 | 3 | 4;
  /** 顶部标题 */
  title?: string;
  /** 整个区块 aria-label，缺省 = title 或 "快速操作" */
  ariaLabel?: string;
  /** 自定义 className */
  className?: string;
}

const GRID: Record<NonNullable<QuickActionsProps["columns"]>, string> = {
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-2 sm:grid-cols-3",
  4: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4",
};

export function QuickActions({
  actions,
  columns = 3,
  title,
  ariaLabel,
  className,
}: QuickActionsProps) {
  const regionLabel = ariaLabel ?? title ?? "快速操作";

  return (
    <section aria-label={regionLabel} className={cn("space-y-3", className)}>
      {title ? (
        <h2 className="text-base font-semibold leading-tight">{title}</h2>
      ) : null}
      <ul className={cn("grid gap-2", GRID[columns])} role="list">
        {actions.map((action) => (
          <li key={action.id}>
            <QuickActionButton action={action} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function QuickActionButton({ action }: { action: QuickAction }) {
  const { id, label, icon: Icon, description, badge, href, onClick, disabled } =
    action;

  const content = (
    <>
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground transition-colors group-hover:bg-primary/10 group-hover:text-primary">
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{label}</span>
          {badge ? (
            <Badge variant="secondary" className="text-[10px] font-normal">
              {badge}
            </Badge>
          ) : null}
        </span>
        {description ? (
          <span className="mt-0.5 block truncate text-xs text-muted-foreground">
            {description}
          </span>
        ) : null}
      </span>
      <ArrowUpRight
        className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60 transition-colors group-hover:text-primary"
        aria-hidden="true"
      />
    </>
  );

  const baseClass = cn(
    "group flex w-full items-center gap-3 rounded-lg border border-border bg-background p-3 text-left",
    "transition-colors hover:border-primary/40 hover:bg-muted/40",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
    disabled && "pointer-events-none opacity-50"
  );

  if (href && !disabled) {
    return (
      <a
        href={href}
        aria-label={label}
        className={cn(baseClass, "no-underline")}
        data-quick-action-id={id}
      >
        {content}
      </a>
    );
  }

  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={() => onClick?.(id)}
      className={baseClass}
      data-quick-action-id={id}
    >
      {content}
    </button>
  );
}

export default QuickActions;
