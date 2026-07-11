"use client";

/**
 * ReactionBar — T608
 *
 * 表情回应条: 显示已存在的 emoji + 当前用户是否有该反应.
 * 上方 emoji 选择器可点 +, 选择 emoji 切换(后端 toggle).
 *
 * Props:
 *   - reactions: [{emoji, user_id, message_id}]
 *   - currentUserId
 *   - onToggle(emoji)
 *
 * 设计:
 *   - 紧凑布局: 第一行是已有的 emoji 计数 + 已选状态环
 *   - hover 时显示 [+ ] 添加按钮, 弹出 emoji quick-picker
 */

import * as React from "react";
import { SmilePlus } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { RoomReaction } from "@/lib/api-rooms";

const QUICK_EMOJI = ["+1", "heart", "tada", "eyes", "fire", "thinking", "sparkles", "rocket"];

interface ReactionBarProps {
  reactions: RoomReaction[];
  currentUserId: string;
  onToggle: (emoji: string) => void;
  className?: string;
}

interface GroupedReaction extends RoomReaction {
  count: number;
  mine: boolean;
}

function groupReactions(reactions: RoomReaction[], me: string): GroupedReaction[] {
  const map = new Map<string, GroupedReaction>();
  for (const r of reactions) {
    const existing = map.get(r.emoji);
    if (existing) {
      existing.count++;
      if (r.user_id === me) existing.mine = true;
    } else {
      map.set(r.emoji, { ...r, count: 1, mine: r.user_id === me });
    }
  }
  return Array.from(map.values()).sort((a, b) => b.count - a.count);
}

export function ReactionBar({ reactions, currentUserId, onToggle, className }: ReactionBarProps) {
  const grouped = React.useMemo(() => groupReactions(reactions, currentUserId), [reactions, currentUserId]);
  const [pickerOpen, setPickerOpen] = React.useState(false);

  return (
    <div className={cn("mt-1 flex flex-wrap items-center gap-1.5", className)}>
      {grouped.map((g) => (
        <button
          key={g.emoji}
          type="button"
          onClick={() => onToggle(g.emoji)}
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors",
            g.mine
              ? "border-primary/40 bg-primary/10 text-primary"
              : "border-transparent bg-muted/70 hover:bg-muted"
          )}
          aria-pressed={g.mine}
          aria-label={`${g.emoji} · ${g.count} 人`}
        >
          <span>{g.emoji}</span>
          <span className="font-medium tabular-nums">{g.count}</span>
        </button>
      ))}

      <div className="relative">
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="h-6 w-6 rounded-full"
          onClick={() => setPickerOpen((o) => !o)}
          aria-label="添加回应"
        >
          <SmilePlus className="h-3.5 w-3.5" />
        </Button>
        {pickerOpen && (
          <div className="absolute z-30 mt-1 flex gap-1 rounded-full border bg-popover p-1 shadow-md">
            {QUICK_EMOJI.map((e) => (
              <button
                key={e}
                type="button"
                onClick={() => {
                  onToggle(e);
                  setPickerOpen(false);
                }}
                className="rounded-full px-1.5 py-0.5 text-sm hover:bg-muted"
                aria-label={`添加 ${e} 表情`}
              >
                {e}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
