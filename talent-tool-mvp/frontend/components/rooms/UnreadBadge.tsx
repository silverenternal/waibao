"use client";

/**
 * UnreadBadge — T608
 *
 * 显示房间未读数. 0 时不渲染, 大于 99 显示 99+.
 */

import { cn } from "@/lib/utils";

interface UnreadBadgeProps {
  count: number;
  className?: string;
  size?: "xs" | "sm";
}

export function UnreadBadge({ count, className, size = "sm" }: UnreadBadgeProps) {
  if (!count || count <= 0) return null;
  const label = count > 99 ? "99+" : String(count);
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-full font-medium bg-rose-500 text-white shadow-sm",
        size === "xs" ? "h-4 min-w-4 px-1 text-[10px]" : "h-5 min-w-5 px-1.5 text-xs",
        className
      )}
      aria-label={`未读 ${count} 条`}
    >
      {label}
    </span>
  );
}
