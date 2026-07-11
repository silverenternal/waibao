"use client";

/**
 * MessageItem — T608
 *
 * 单条消息气泡:
 *   - 左: 头像 (sender_id 前两位)
 *   - 中: 用户名 + 时间 + 内容 (mention offset 高亮)
 *   - 右: 操作菜单 (编辑/删除/线程回应/置顶)
 *   - 下: ReactionBar
 *   - 线程 root 标识: 显示 thread_count + "打开线程" 按钮
 *
 * 链接预览: 简易实现 — 自动探测 http(s):// URL, 显示为可点击 link,
 *          加载链接预览图片 + 标题交给上层 ThreadPanel / MessageList 异步聚合.
 */

import * as React from "react";
import {
  MessageSquare,
  Edit3,
  Trash2,
  Pin,
  CornerDownRight,
  MoreHorizontal,
  CheckCheck,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ReactionBar } from "@/components/rooms/ReactionBar";
import { applyMentionOffsets } from "@/lib/api-rooms";
import type { RoomMessage, RoomReaction } from "@/lib/api-rooms";

interface MessageItemProps {
  message: RoomMessage;
  /** 当前用户 id, 用于显示 own / 控制菜单. */
  currentUserId: string;
  /** 缓存的 replies 线程数, undefined 表示未载入. */
  threadCount?: number;
  reactions: RoomReaction[];
  /** 该消息已撤回. */
  deleted?: boolean;
  /** @ hover 高亮 (从 MessageList 传入, 用于@提及我自己时, 应用 ring). */
  mentionsMe?: boolean;
  /** 该消息是否被 pin. */
  pinned?: boolean;
  /** 来自被标记 mention 状态. */
  onEdit?: (message: RoomMessage) => void;
  onDelete?: (message: RoomMessage) => void;
  onReact?: (emoji: string) => void;
  onReply?: (message: RoomMessage) => void;
  onOpenThread?: (message: RoomMessage) => void;
  onPin?: (message: RoomMessage) => void;
  className?: string;
}

function formatTime(iso: string) {
  const t = new Date(iso);
  const now = new Date();
  const sameDay =
    t.getFullYear() === now.getFullYear() &&
    t.getMonth() === now.getMonth() &&
    t.getDate() === now.getDate();
  return sameDay
    ? t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : `${t.getMonth() + 1}/${t.getDate()} ${t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

function renderContentWithMentions(
  content: string,
  offsets: { user_id: string; start: number; end: number }[]
) {
  if (!offsets || offsets.length === 0) {
    return renderLinks(content);
  }
  const segments = applyMentionOffsets(content, offsets);
  return (
    <>
      {segments.map((seg, i) => {
        if (seg.type === "mention") {
          return (
            <span
              key={i}
              className="font-medium text-primary underline decoration-primary/40 decoration-dotted underline-offset-2"
              data-mention-user={seg.user_id}
            >
              {seg.text}
            </span>
          );
        }
        return <React.Fragment key={i}>{renderLinks(seg.text)}</React.Fragment>;
      })}
    </>
  );
}

const URL_RE = /(https?:\/\/[^\s<>()]+[^\s<>().,;:!?])/g;

function renderLinks(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  const re = new RegExp(URL_RE.source, "g");
  while ((m = re.exec(text)) !== null) {
    if (m.index > lastIdx) {
      parts.push(text.slice(lastIdx, m.index));
    }
    parts.push(
      <a
        key={m.index}
        href={m[0]}
        target="_blank"
        rel="noreferrer"
        className="text-blue-600 hover:underline break-all"
        onClick={(e) => e.stopPropagation()}
      >
        {m[0]}
      </a>
    );
    lastIdx = m.index + m[0].length;
  }
  if (lastIdx < text.length) {
    parts.push(text.slice(lastIdx));
  }
  return parts;
}

export function MessageItem({
  message,
  currentUserId,
  threadCount,
  reactions,
  deleted,
  mentionsMe,
  pinned,
  onEdit,
  onDelete,
  onReact,
  onReply,
  onOpenThread,
  onPin,
  className,
}: MessageItemProps) {
  const isMine = message.sender_id === currentUserId;
  const isDeleted = !!message.deleted_at || deleted;
  const [showMenu, setShowMenu] = React.useState(false);

  return (
    <article
      className={cn(
        "group relative flex gap-3 px-4 py-2 transition-colors",
        mentionsMe && "bg-primary/5 ring-1 ring-primary/15",
        pinned && "bg-amber-50/40 dark:bg-amber-950/20",
        className
      )}
      data-message-id={message.id}
      data-thread-root-id={message.thread_root_id ?? undefined}
    >
      {pinned && (
        <div className="absolute left-1.5 top-3 flex items-center text-amber-600">
          <Pin className="h-3.5 w-3.5" />
        </div>
      )}

      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white shadow-sm",
          "bg-gradient-to-br from-blue-500 to-purple-600",
          isMine && "ring-2 ring-primary/40"
        )}
        aria-hidden
      >
        {message.sender_id.slice(0, 2).toUpperCase()}
      </div>

      <div className="min-w-0 flex-1">
        <header className="flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground">
            {message.sender_id}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {formatTime(message.created_at)}
          </span>
          {message.edited_at && !isDeleted && (
            <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
              <Edit3 className="h-2.5 w-2.5" />
              已编辑
            </span>
          )}
          {pinned && (
            <span className="rounded bg-amber-100 px-1 text-[10px] text-amber-700">
              已置顶
            </span>
          )}
          {isMine && <CheckCheck className="h-3 w-3 text-muted-foreground" />}
        </header>

        {message.parent_id && (
          <div className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
            <CornerDownRight className="h-2.5 w-2.5" />
            回复线程
          </div>
        )}

        <div
          className={cn(
            "mt-0.5 break-words text-sm leading-relaxed text-foreground",
            isDeleted && "text-muted-foreground italic"
          )}
        >
          {isDeleted ? (
            <span>(消息已删除)</span>
          ) : message.message_type === "markdown" ? (
            <span className="font-mono text-xs">
              {renderContentWithMentions(message.content, message.mention_offsets)}
            </span>
          ) : (
            renderContentWithMentions(message.content, message.mention_offsets)
          )}
        </div>

        {/* 附件 / 文件 */}
        {message.attachments && message.attachments.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-2">
            {message.attachments.map((a, i) => (
              <li key={i}>
                <a
                  href={a.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded border bg-muted/40 px-2 py-1 text-xs hover:bg-muted"
                  onClick={(e) => e.stopPropagation()}
                >
                  <span>{a.name}</span>
                  {a.size && <span className="text-[10px] text-muted-foreground">{(a.size / 1024).toFixed(1)} KB</span>}
                </a>
              </li>
            ))}
          </ul>
        )}

        {onReact && (
          <ReactionBar reactions={reactions} currentUserId={currentUserId} onToggle={(e) => onReact(e)} />
        )}

        {/* 线程汇总 */}
        {message.parent_id === null && (
          <div className="mt-1.5">
            <button
              type="button"
              onClick={() => onOpenThread?.(message)}
              className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <MessageSquare className="h-3 w-3" />
              {threadCount && threadCount > 0
                ? `${threadCount} 条回复`
                : "回复线程"}
            </button>
          </div>
        )}
      </div>

      {/* Hover 操作菜单 (own only) */}
      {(onEdit || onDelete || onReply || onPin) && (
        <div className="absolute right-3 top-2 hidden gap-1 rounded-md border bg-popover p-0.5 shadow-sm group-hover:flex">
          {onReply && message.parent_id === null && (
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => onReply(message)} aria-label="回复线程">
              <CornerDownRight className="h-3.5 w-3.5" />
            </Button>
          )}
          {onEdit && isMine && !isDeleted && (
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => onEdit(message)} aria-label="编辑">
              <Edit3 className="h-3.5 w-3.5" />
            </Button>
          )}
          {onDelete && (isMine || onPin) && !isDeleted && (
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => onDelete(message)} aria-label="删除">
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
          {onPin && (
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => onPin(message)} aria-label={pinned ? "取消置顶" : "置顶"}>
              <Pin className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      )}
    </article>
  );
}
