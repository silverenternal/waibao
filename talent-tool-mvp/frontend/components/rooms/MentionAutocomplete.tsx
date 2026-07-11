"use client";

/**
 * MentionAutocomplete — T608
 *
 * @ 触发的成员选择弹层.
 *
 * 使用 cmdk-like 自实现: 监听 keyword 变化, 上下方向键移动高亮, Enter 选择,
 * 选中后用 formatMention() 插入到 composer 的 content.
 */

import * as React from "react";
import { AtSign, User as UserIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import type { RoomMember } from "@/lib/api-rooms";

export interface MentionUser {
  id: string;
  name?: string | null;
  role?: string;
}

interface MentionAutocompleteProps {
  /** 是否显示 (composer 检测到 @ 触发). */
  open: boolean;
  /** 用户列表 (room members 或组织成员). */
  members: (RoomMember | MentionUser)[];
  /** 当前输入 query (去掉 @ 后剩余部分). */
  query: string;
  /** 选中回调 (返回完整 mention 文本, 用于替换光标前的那段). */
  onSelect: (userId: string, fullHandle: string) => void;
  /** 标记坐标 (定位弹层). */
  position?: { top: number; left: number };
  /** 高亮 id (父组件可控, 键盘导航). */
  activeId?: string | null;
  /** 父组件接管键盘事件时使用. */
  onActiveChange?: (id: string | null) => void;
  className?: string;
}

function userName(u: RoomMember | MentionUser): string {
  if ("user_id" in u) return (u as RoomMember).user_id;
  return (u as MentionUser).name || (u as MentionUser).id;
}

function userId(u: RoomMember | MentionUser): string {
  if ("user_id" in u) return (u as RoomMember).user_id;
  return (u as MentionUser).id;
}

function userRole(u: RoomMember | MentionUser): string {
  if ("role" in u && typeof (u as RoomMember).role === "string") {
    return (u as RoomMember).role;
  }
  return ((u as MentionUser).role as string) ?? "member";
}

export function MentionAutocomplete({
  open,
  members,
  query,
  onSelect,
  activeId,
  onActiveChange,
  className,
}: MentionAutocompleteProps) {
  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return members.slice(0, 8);
    return members
      .filter((m) => {
        const id = userId(m).toLowerCase();
        const name = userName(m).toLowerCase();
        return id.includes(q) || name.includes(q);
      })
      .slice(0, 8);
  }, [members, query]);

  if (!open) return null;
  if (filtered.length === 0) {
    return (
      <div
        className={cn(
          "absolute z-50 w-56 rounded-md border bg-popover p-2 text-xs text-muted-foreground shadow-md",
          className
        )}
        role="listbox"
      >
        没有匹配的成员
      </div>
    );
  }

  const active = activeId ?? userId(filtered[0]);

  return (
    <div
      className={cn(
        "absolute z-50 w-56 max-h-56 overflow-y-auto rounded-md border bg-popover shadow-md",
        className
      )}
      role="listbox"
    >
      <ul className="p-1 text-sm">
        {filtered.map((m) => {
          const id = userId(m);
          const isActive = id === active;
          return (
            <li key={id}>
              <button
                type="button"
                onMouseEnter={() => onActiveChange?.(id)}
                onClick={() => onSelect(id, `@${id}`)}
                className={cn(
                  "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left",
                  isActive ? "bg-primary/10 text-primary" : "hover:bg-muted"
                )}
                role="option"
                aria-selected={isActive}
              >
                <AtSign className="h-3.5 w-3.5 opacity-60" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium">
                    {userName(m)}
                  </div>
                  <div className="truncate text-[10px] text-muted-foreground">
                    {userRole(m)}
                  </div>
                </div>
                <UserIcon className="h-3.5 w-3.5 opacity-40" />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * 给定内容 + 光标位置 + 用户 ID, 返回插入 @<UUID> 后:
 * - newContent: 替换后的整段文本
 * - newCursor: 新的光标位置 (mention 之后)
 */
export function insertMentionAtCursor(
  content: string,
  cursor: number,
  userId: string
): { newContent: string; newCursor: number } {
  // 检查 cursor 前的字符是否是 @ 或空白
  let start = cursor;
  while (start > 0 && /[\w@-]/.test(content[start - 1])) {
    start--;
  }
  const mention = `@${userId} `;
  const before = content.slice(0, start);
  const after = content.slice(cursor);
  const newContent = before + mention + after;
  return { newContent, newCursor: (before + mention).length };
}

/** 给定 keyword, 返回是否命中 mention 触发态. */
export interface MentionTriggerState {
  active: boolean;
  query: string;
  start: number; // @ 字符位置
  end: number; // 当前光标位置
}

export function detectMentionTrigger(content: string, cursor: number): MentionTriggerState {
  // 从 cursor 向左扫描直到遇到 @ 或 空白
  let i = cursor;
  while (i > 0) {
    const ch = content[i - 1];
    if (ch === "@") {
      // 只有当 @ 前是 空白/开头 才算 trigger
      const prev = i - 2 >= 0 ? content[i - 2] : " ";
      if (/[\s\n，。,]/.test(prev) || i === 1) {
        return { active: true, query: content.slice(i, cursor), start: i - 1, end: cursor };
      }
      return { active: false, query: "", start: -1, end: -1 };
    }
    if (/\s/.test(ch)) {
      return { active: false, query: "", start: -1, end: -1 };
    }
    i--;
  }
  return { active: false, query: "", start: -1, end: -1 };
}
