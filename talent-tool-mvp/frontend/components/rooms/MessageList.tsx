"use client";

/**
 * MessageList — T608
 *
 * 主对话流 + 无限滚动 + 线程根聚合.
 *
 * 设计:
 *   - 顶部 "跳到最新" 按钮 (用户回滚查看历史时显示)
 *   - 滚动到底部时自动加载下一页 (cursor pagination)
 *   - 显示 optimistic pending messages (useRoom.pending)
 *   - 用户被 @mention 的消息加 ring 高亮 (mentionsMe)
 *
 * Props:
 *   - messages: 主对话流 (parent_id IS NULL) 倒序追加
 *   - threadCounts: Map<msg_id, count>
 *   - pendingMessages: useRoom.pending
 *   - mentionsMe: Set<msg_id>
 *   - onLoadMore(cursor) - 游标回调
 */

import * as React from "react";
import { ArrowDown, Loader2, MessageCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { MessageItem } from "@/components/rooms/MessageItem";
import type { PendingMessage } from "@/lib/use-room";
import type {
  RoomMessage,
  RoomReaction,
} from "@/lib/api-rooms";

interface MessageListProps {
  messages: RoomMessage[];
  threadCounts?: Record<string, number>;
  reactions?: Record<string, RoomReaction[]>;
  pendingMessages?: PendingMessage[];
  pendingIds?: Set<string>;
  mentionsMe?: Set<string>;
  pinnedIds?: Set<string>;
  currentUserId: string;
  loadingMore?: boolean;
  hasMore?: boolean;
  onLoadMore?: () => void;
  onEdit?: (m: RoomMessage) => void;
  onDelete?: (m: RoomMessage) => void;
  onReply?: (m: RoomMessage) => void;
  onOpenThread?: (m: RoomMessage) => void;
  onPin?: (m: RoomMessage) => void;
  onReact?: (messageId: string, emoji: string) => void;
  className?: string;
}

export function MessageList({
  messages,
  threadCounts,
  reactions,
  pendingMessages,
  pendingIds,
  mentionsMe,
  pinnedIds,
  currentUserId,
  loadingMore,
  hasMore,
  onLoadMore,
  onEdit,
  onDelete,
  onReply,
  onOpenThread,
  onPin,
  onReact,
  className,
}: MessageListProps) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const sentinelRef = React.useRef<HTMLDivElement>(null);
  const [showJump, setShowJump] = React.useState(false);
  const stickToBottomRef = React.useRef(true);
  const [initialScrollDone, setInitialScrollDone] = React.useState(false);

  // 滚动到底部
  const scrollToBottom = React.useCallback((behavior: "smooth" | "auto" = "smooth") => {
    const c = containerRef.current;
    if (!c) return;
    c.scrollTo({ top: c.scrollHeight, behavior });
  }, []);

  // 用户滚到底附近时不要自动跳, 否则保持 stuck bottom
  function onScroll() {
    const c = containerRef.current;
    if (!c) return;
    const distance = c.scrollHeight - c.scrollTop - c.clientHeight;
    if (distance > 200) {
      stickToBottomRef.current = false;
      setShowJump(true);
    } else {
      stickToBottomRef.current = true;
      setShowJump(false);
    }
  }

  // 初次挂载 + 新消息进来时 (只有 "吸附在底" 才滚动)
  React.useEffect(() => {
    if (!messages.length) return;
    if (!initialScrollDone) {
      scrollToBottom("auto");
      setInitialScrollDone(true);
      return;
    }
    if (stickToBottomRef.current) {
      scrollToBottom("smooth");
    }
  }, [messages.length, initialScrollDone, scrollToBottom]);

  // 无限滚动 — 顶部 sentinel
  React.useEffect(() => {
    const sent = sentinelRef.current;
    if (!sent || !onLoadMore) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loadingMore) {
          onLoadMore();
        }
      },
      { root: containerRef.current, rootMargin: "120px 0px 0px 0px" }
    );
    obs.observe(sent);
    return () => obs.disconnect();
  }, [onLoadMore, hasMore, loadingMore]);

  return (
    <div className={cn("relative flex-1 min-h-0", className)}>
      <div
        ref={containerRef}
        onScroll={onScroll}
        className="absolute inset-0 overflow-y-auto"
        role="log"
        aria-live="polite"
      >
        <div ref={sentinelRef} aria-hidden className="h-1" />
        {loadingMore && (
          <div className="flex justify-center py-3">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        )}

        {messages.length === 0 && !loadingMore && (
          <div className="flex flex-col items-center justify-center h-full text-center text-sm text-muted-foreground">
            <MessageCircle className="h-8 w-8 mb-2 opacity-40" />
            还没有消息, 先打个招呼吧 👋
          </div>
        )}

        <ul className="flex flex-col">
          {messages.map((m) => (
            <li key={m.id}>
              <MessageItem
                message={m}
                currentUserId={currentUserId}
                threadCount={threadCounts?.[m.id]}
                reactions={reactions?.[m.id] || []}
                mentionsMe={mentionsMe?.has(m.id)}
                pinned={pinnedIds?.has(m.id)}
                onEdit={onEdit}
                onDelete={onDelete}
                onReply={onReply}
                onOpenThread={onOpenThread}
                onPin={onPin}
                onReact={(emoji) => onReact?.(m.id, emoji)}
              />
            </li>
          ))}
        </ul>

        {/* 乐观更新 pending (发送中) */}
        {pendingMessages && pendingMessages && pendingMessages.length > 0 && (
          <div className="border-t border-dashed mt-2">
            {pendingMessages.map((p) => (
              <div
                key={p.delivery_id}
                className="flex gap-3 px-4 py-2 opacity-70"
                data-pending-id={p.delivery_id}
              >
                <Skeleton className="h-9 w-9 rounded-full" />
                <div className="flex-1">
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="h-4 w-64 mt-1" />
                  <span className="text-[10px] text-muted-foreground">
                    {p.status === "sending" && "发送中..."}
                    {p.status === "delivered" && "已送达"}
                    {p.status === "error" && (p.error || "发送失败")}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showJump && (
        <Button
          size="icon"
          variant="secondary"
          className="absolute bottom-4 right-4 rounded-full shadow-lg"
          onClick={() => {
            scrollToBottom("smooth");
          }}
          aria-label="跳到最新"
        >
          <ArrowDown className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}
