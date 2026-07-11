"use client";

/**
 * ThreadPanel — T608
 *
 * 房间内右侧弹出的线程回复面板.
 *   - 顶部: 父消息 + 关闭按钮
 *   - 中: 回复列表 (按时间正序)
 *   - 底: MessageComposer (parentId = parent.id)
 */

import * as React from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { MessageItem } from "@/components/rooms/MessageItem";
import { MessageComposer, buildMentionOffsets } from "@/components/rooms/MessageComposer";
import type { RoomMember, RoomMessage, RoomReaction } from "@/lib/api-rooms";
import { roomsApi } from "@/lib/api-rooms";

interface ThreadPanelProps {
  roomId: string;
  parentMessage: RoomMessage;
  members: RoomMember[];
  currentUserId: string;
  reactions?: RoomReaction[];
  onClose?: () => void;
  onReplied?: (reply: RoomMessage) => void;
  className?: string;
}

export function ThreadPanel({
  roomId,
  parentMessage,
  members,
  currentUserId,
  reactions,
  onClose,
  onReplied,
  className,
}: ThreadPanelProps) {
  const [replies, setReplies] = React.useState<RoomMessage[]>([]);
  const [loading, setLoading] = React.useState(true);

  const fetchReplies = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await roomsApi.listThreadReplies(roomId, parentMessage.id);
      setReplies(res.messages || []);
    } finally {
      setLoading(false);
    }
  }, [roomId, parentMessage.id]);

  React.useEffect(() => {
    void fetchReplies();
  }, [fetchReplies]);

  async function handleSend(content: string, attachments: import("@/lib/api-rooms").RoomAttachment[]) {
    const msg = await roomsApi.postMessage(roomId, {
      content,
      parent_id: parentMessage.id,
      message_type: "text",
      mentions: [],
      mention_offsets: buildMentionOffsets(content),
      attachments,
    });
    onReplied?.(msg);
    setReplies((xs) => [...xs, msg]);
  }

  return (
    <aside
      className={cn(
        "fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l bg-background shadow-xl md:relative md:max-w-none md:flex-1 md:shadow-none",
        className
      )}
      role="dialog"
      aria-label="线程回复"
    >
      <header className="flex items-center justify-between border-b px-4 py-2">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">线程</div>
          <div className="truncate text-sm font-semibold">
            {parentMessage.sender_id} 的消息
          </div>
        </div>
        <Button size="icon" variant="ghost" onClick={onClose} aria-label="关闭线程">
          <X className="h-4 w-4" />
        </Button>
      </header>

      <div className="border-b bg-muted/40 px-4 py-3">
        <MessageItem
          message={parentMessage}
          currentUserId={currentUserId}
          reactions={reactions || []}
          mentionsMe={parentMessage.mentions.includes(currentUserId)}
        />
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        <ul className="flex flex-col">
          {loading ? (
            <li className="px-4 py-3 text-xs text-muted-foreground">载入回复...</li>
          ) : replies.length === 0 ? (
            <li className="px-4 py-8 text-center text-sm text-muted-foreground">
              成为第一个回复的人 ↩
            </li>
          ) : (
            replies.map((r) => (
              <li key={r.id}>
                <MessageItem
                  message={r}
                  currentUserId={currentUserId}
                  reactions={[]}
                  mentionsMe={r.mentions.includes(currentUserId)}
                />
              </li>
            ))
          )}
        </ul>
      </div>

      <MessageComposer
        members={members}
        onSend={handleSend}
        placeholder={`回复 ${parentMessage.sender_id}...`}
        parentId={parentMessage.id}
      />
    </aside>
  );
}
