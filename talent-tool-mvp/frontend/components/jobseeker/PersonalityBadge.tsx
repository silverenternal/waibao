"use client";

/**
 * v9.1 — Jobseeker shared subcomponents: PersonalityBadge
 *
 * 性格 / 偏好 / MBTI 风格的徽章，仪表盘、报告卡片、推荐理由中复用。
 * 既可当 inline 小徽章（无 description），也可点击展开 tooltip / popover。
 *
 * 特性：
 *  - 强类型 trait: { code, label, description? }
 *  - 通用：4 个 tone variant + 可选 description
 *  - 响应式：在小屏自动 ellipsis
 *  - 可访问：role="img" + aria-label；带 description 时 role="button" 可触发 onClick
 */

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Info, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

export type PersonalityTone =
  | "neutral"
  | "analyst"
  | "diplomat"
  | "sentinel"
  | "explorer";

export interface PersonalityTrait {
  /** 代码，如 "INTJ" / "A1" */
  code: string;
  /** 中文/英文标签，如 "建筑师" */
  label: string;
  /** 详细描述（可选） */
  description?: string;
  /** 主题色调 */
  tone?: PersonalityTone;
}

const badgeStyles = cva(
  [
    "inline-flex max-w-full items-center gap-2 rounded-full border px-2.5 py-1",
    "text-xs font-medium transition-colors",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
  ],
  {
    variants: {
      size: {
        default: "h-7 text-xs",
        sm: "h-6 px-2 py-0.5 text-[11px]",
        lg: "h-9 px-3 py-1.5 text-sm",
      },
      interactive: {
        true: "cursor-pointer hover:opacity-90 active:scale-[0.98]",
        false: "",
      },
    },
    defaultVariants: {
      size: "default",
      interactive: false,
    },
  }
);

const TONE_STYLE: Record<PersonalityTone, string> = {
  neutral: "bg-slate-500/10 text-slate-700 border-slate-300/60",
  analyst: "bg-indigo-500/10 text-indigo-700 border-indigo-300/60",
  diplomat: "bg-emerald-500/10 text-emerald-700 border-emerald-300/60",
  sentinel: "bg-sky-500/10 text-sky-700 border-sky-300/60",
  explorer: "bg-amber-500/10 text-amber-700 border-amber-300/60",
};

const TONE_DOT: Record<PersonalityTone, string> = {
  neutral: "bg-slate-400",
  analyst: "bg-indigo-500",
  diplomat: "bg-emerald-500",
  sentinel: "bg-sky-500",
  explorer: "bg-amber-500",
};

export interface PersonalityBadgeProps
  extends VariantProps<typeof badgeStyles> {
  /** 性格信息 */
  trait: PersonalityTrait;
  /** 是否显示 description icon（hover 提示或点击回调由 onSelect 控制） */
  showDescription?: boolean;
  /** 点击/键盘触发回调（携带 trait） */
  onSelect?: (trait: PersonalityTrait) => void;
  /** 仅渲染 code 字符（紧凑显示） */
  codeOnly?: boolean;
  /** 自定义 className */
  className?: string;
  /** 自定义 id */
  id?: string;
  /** 自定义 test id */
  "data-testid"?: string;
}

export function PersonalityBadge({
  trait,
  showDescription = false,
  onSelect,
  codeOnly = false,
  size,
  className,
  ...props
}: PersonalityBadgeProps) {
  const { code, label, description, tone = "neutral" } = trait;
  const trigger = onSelect;
  const isInteractive = Boolean(trigger);
  const role = isInteractive ? "button" : "img";
  const ariaLabel = description
    ? `${label}（${code}）— ${description}`
    : `${label}（${code}）`;

  const content = (
    <>
      <span
        aria-hidden="true"
        className={cn("h-2 w-2 shrink-0 rounded-full", TONE_DOT[tone])}
      />
      {codeOnly ? (
        <span className="truncate font-semibold tracking-wide">{code}</span>
      ) : (
        <span className="truncate">
          <span className="font-semibold tracking-wide">{code}</span>
          <span className="mx-1 text-muted-foreground">·</span>
          <span className="text-muted-foreground">{label}</span>
        </span>
      )}
      {showDescription && description ? (
        <span
          aria-hidden="true"
          className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-background/60 text-muted-foreground"
        >
          <Info className="h-3 w-3" />
        </span>
      ) : null}
    </>
  );

  const handleClick = () => {
    if (trigger) trigger(trait);
  };
  const handleKeyDown = (e: React.KeyboardEvent<HTMLSpanElement>) => {
    if (isInteractive && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      if (trigger) trigger(trait);
    }
  };

  return (
    <span
      role={role}
      tabIndex={isInteractive ? 0 : undefined}
      aria-label={ariaLabel}
      title={description}
      onClick={isInteractive ? handleClick : undefined}
      onKeyDown={isInteractive ? handleKeyDown : undefined}
      {...props}
      className={cn(
        badgeStyles({ size, interactive: isInteractive }),
        TONE_STYLE[tone],
        className
      )}
    >
      {content}
    </span>
  );
}

/**
 * 多枚 PersonalityBadge 的轻量组合（仪表盘"性格合集"用），自动换行 + 间距。
 */
export interface PersonalityBadgeGroupProps {
  traits: PersonalityTrait[];
  size?: VariantProps<typeof badgeStyles>["size"];
  showDescription?: boolean;
  onSelect?: (trait: PersonalityTrait) => void;
  className?: string;
  /** 顶部小图标 */
  icon?: React.ReactNode;
  /** 顶部标题 */
  title?: string;
}

export function PersonalityBadgeGroup({
  traits,
  size = "default",
  showDescription = false,
  onSelect,
  className,
  icon,
  title,
}: PersonalityBadgeGroupProps) {
  return (
    <div className={cn("space-y-2", className)}>
      {title ? (
        <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          {icon ?? <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
          {title}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-1.5">
        {traits.map((t) => (
          <PersonalityBadge
            key={`${t.code}-${t.tone ?? "neutral"}`}
            trait={t}
            size={size}
            showDescription={showDescription}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}

export default PersonalityBadge;
