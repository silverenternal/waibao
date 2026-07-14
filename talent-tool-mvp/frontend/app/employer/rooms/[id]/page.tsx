"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Room conversation page — /rooms/{id} (T608).
 *
 * 综合:
 *   - RoomHeader (在线状态 + 成员 + pin 计数)
 *   - MessageList (主对话流 + 无限滚动)
 *   - ThreadPanel (线程侧栏)
 *   - MessageComposer (输入)
 *
 * WebSocket (useRoom):
 *   - publish 消息 → 上线消息直接出现在列表
 *   - delivery_id + ack 模式
 *   - typing / presence / read 状态
 *
 * 上传附件走 v2.0 的 /api/uploads 接口.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { Loader2, Search } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RoomSidebar } from "@/components/rooms/RoomSidebar";
import { RoomHeader } from "@/components/rooms/RoomHeader";
import { MessageList } from "@/components/rooms/MessageList";
import { ThreadPanel } from "@/components/rooms/ThreadPanel";
import {
  MessageComposer,
  buildMentionOffsets,
} from "@/components/rooms/MessageComposer";
import {
  roomsApi,
  type RoomAttachment,
  type RoomMessage,
  type RoomReaction,
  type RoomWithExtras,
} from "@/lib/api-rooms";
import { useRoom } from "@/lib/use-room";
import { createClient } from "@/lib/supabase";

const PAGE_SIZE = 50;

export default function RoomDetailPage() {
  const { id } = useParams<{ id: string }>();
  const roomId = decodeURIComponent(id || "");
  const router = useRouter();

  const [room, setRoom] = React.useState<RoomWithExtras | null>(null);
  const [rooms, setRooms] = React.useState<Awaited<ReturnType<typeof roomsApi.listRooms>>["rooms"]>([]);
  const [messages, setMessages] = React.useState<RoomMessage[]>([]);
  const [reactions, setReactions] = React.useState<Record<string, RoomReaction[]>>({});
  const [threadCounts, setThreadCounts] = React.useState<Record<string, number>>({});
  const [pinnedIds, setPinnedIds] = React.useState<Set<string>>(new Set());
  const [loadingRoom, setLoadingRoom] = React.useState(true);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [nextCursor, setNextCursor] = React.useState<string | null>(null);
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [searchResults, setSearchResults] = React.useState<RoomMessage[]>([]);
  const [openThread, setOpenThread] = React.useState<RoomMessage | null>(null);

  const currentUserIdRef = React.useRef<string>("");
  React.useEffect(() => {
    createClient().auth.getSession().then(({ data }) => {
      currentUserIdRef.current = data.session?.user?.id ?? "anonymous";
    });
  }, []);

  const currentUserId = currentUserIdRef.current;

  // ────────────────────────────────────────────────────────────────
  // 拉取数据
  // ────────────────────────────────────────────────────────────────
  const fetchRoom = React.useCallback(async () => {
    if (!roomId) return;
    try {
      const data = await roomsApi.getRoom(roomId);
      setRoom(data);
      // pin set
      setPinnedIds(new Set((data.pins || []).map((p) => p.message.id)));
    } catch (err) {
      toast.error("加载房间失败");
    } finally {
      setLoadingRoom(false);
    }
  }, [roomId]);

  const fetchRooms = React.useCallback(async () => {
    const res = await roomsApi.listRooms();
    setRooms(res.rooms);
  }, []);

  const fetchMessages = React.useCallback(
    async (cursor?: string | null) => {
      if (!roomId) return;
      if (cursor) setLoadingMore(true);
      try {
        const res = await roomsApi.listMessages(roomId, {
          cursor: cursor ?? undefined,
          limit: PAGE_SIZE,
        });
        const next = res.messages;
        if (cursor) {
          setMessages((xs) => [...next, ...xs]);
        } else {
          setMessages(next);
        }
        setNextCursor(res.next_cursor);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error(err);
        toast.error("加载消息失败");
      } finally {
        setLoadingMore(false);
      }
    },
    [roomId]
  );

  React.useEffect(() => {
    void fetchRoom();
    void fetchRooms();
    void fetchMessages(null);
    roomsApi.markRead(roomId).catch(() => undefined);
  }, [roomId, fetchRoom, fetchMessages, fetchRooms]);

  // ────────────────────────────────────────────────────────────────
  // WebSocket
  // ────────────────────────────────────────────────────────────────
  const onMessage = React.useCallback((m: RoomMessage) => {
    setMessages((xs) => {
      if (xs.some((x) => x.id === m.id)) return xs;
      return [...xs, m];
    });
    if (m.parent_id) {
      setThreadCounts((c) => ({ ...c, [m.parent_id!]: (c[m.parent_id!] ?? 0) + 1 }));
    }
  }, []);
  const onMemberChange = React.useCallback(() => {
    void fetchRoom();
  }, [fetchRoom]);

  const { status: wsStatus, pending, sendMessage, sendTyping, markRead: wsMarkRead } = useRoom({
    roomId,
    currentUserId,
    onMessage,
    onMemberChange,
  });

  // 已读标记 (Enter-room + 滚到底触发)
  React.useEffect(() => {
    wsMarkRead();
  }, [wsMarkRead, messages.length]);

  // ────────────────────────────────────────────────────────────────
  // 操作
  // ────────────────────────────────────────────────────────────────
  async function handleSend(content: string, attachments: RoomAttachment[]) {
    await sendMessage(content, {
      message_type: "text",
    });
    if (attachments.length > 0) {
      // 当前实现不发送到消息 (composer 自己处理); 真实场景下应先发 base 消息再 PATCH attachments.
      toast.info("已附带附件 (本演示仅展示字段)");
    }
  }

  async function handleAttach(): Promise<RoomAttachment | null> {
    // 调 v2.0 的 /api/uploads
    try {
      const fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.click();
      await new Promise<void>((resolve, reject) => {
        fileInput.onchange = () => resolve();
        fileInput.oncancel = () => reject(new Error("canceled"));
      });
      const f = fileInput.files?.[0];
      if (!f) return null;
      const fd = new FormData();
      fd.append("file", f);
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/uploads`, {
        method: "POST",
        headers: session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {},
        body: fd,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      return {
        url: data.url ?? data.file_url,
        name: f.name,
        mime: f.type,
        size: f.size,
      };
    } catch (err) {
      toast.error("附件上传失败");
      return null;
    }
  }

  async function handleDelete(m: RoomMessage) {
    if (!confirm("删除这条消息?")) return;
    try {
      await roomsApi.deleteMessage(roomId, m.id);
      setMessages((xs) =>
        xs.map((x) => (x.id === m.id ? { ...x, deleted_at: new Date().toISOString() } : x))
      );
      toast.success("已删除");
    } catch (err) {
      toast.error((err as Error).message ?? "删除失败");
    }
  }

  async function handleEdit(m: RoomMessage, content: string) {
    try {
      const updated = await roomsApi.editMessage(roomId, m.id, content);
      setMessages((xs) => xs.map((x) => (x.id === m.id ? updated : x)));
      toast.success("已编辑");
    } catch (err) {
      toast.error((err as Error).message ?? "编辑失败");
    }
  }

  async function handleReact(messageId: string, emoji: string) {
    try {
      const res = await roomsApi.toggleReaction(roomId, messageId, emoji);
      // optimistic update list
      setReactions((m) => {
        const list = m[messageId] ? [...m[messageId]] : [];
        const filtered = list.filter((r) => r.emoji !== emoji || r.user_id !== currentUserId);
        if (res.active) {
          filtered.push({
            message_id: messageId,
            user_id: currentUserId,
            emoji,
            created_at: new Date().toISOString(),
          });
        }
        return { ...m, [messageId]: filtered };
      });
    } catch (err) {
      toast.error("反应失败");
    }
  }

  async function handlePin(m: RoomMessage) {
    try {
      const isCurrentlyPinned = pinnedIds.has(m.id);
      if (isCurrentlyPinned) {
        await roomsApi.unpinMessage(roomId, m.id);
        setPinnedIds((s) => {
          const ns = new Set(s);
          ns.delete(m.id);
          return ns;
        });
        toast.success("已取消置顶");
      } else {
        await roomsApi.pinMessage(roomId, m.id);
        setPinnedIds((s) => new Set(s).add(m.id));
        toast.success("已置顶");
      }
    } catch (err) {
      toast.error((err as Error).message ?? "置顶操作失败");
    }
  }

  async function performSearch(q: string) {
    if (!q.trim()) {
      setSearchResults([]);
      return;
    }
    try {
      const res = await roomsApi.searchMessages(roomId, q);
      setSearchResults(res.messages);
    } catch {
      // ignore
    }
  }

  // ────────────────────────────────────────────────────────────────
  // 渲染
  // ────────────────────────────────────────────────────────────────
  if (loadingRoom || !room) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center text-muted-foreground">
        <Loader2 className="h-5 w-5 mr-2 animate-spin" />
        载入房间...
      </div>
    );
  }

  return (
    <ErrorBoundary>(<div className="flex h-[calc(100vh-3.5rem)] w-full">
        <div className="hidden md:block">
          <RoomSidebar rooms={rooms} activeRoomId={roomId} />
        </div>
        <div className="flex flex-1 min-w-0 flex-col">
          <RoomHeader
            name={room.name}
            type={room.type}
            members={room.members}
            onlineUserIds={new Set()} // 实时由 useRoom 内部统计, 这里先空
            pinnedCount={pinnedIds.size}
            wsStatus={wsStatus}
            onToggleSearch={() => setSearchOpen((o) => !o)}
            onShowPins={() => router.push(`/rooms/${roomId}#pins`)}
            onLeave={() => {
              if (!confirm("离开这个房间?")) return;
              roomsApi.removeMember(roomId, currentUserId).then(() => {
                toast.success("已离开");
                router.push("/rooms");
              });
            }}
          />

          {searchOpen && (
            <div className="border-b bg-muted/30 px-4 py-2 flex items-center gap-2">
              <Search className="h-4 w-4 text-muted-foreground" />
              <Input
                autoFocus
                placeholder="在房间内搜索消息..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  void performSearch(e.target.value);
                }}
                className="h-8"
              />
              {searchResults.length > 0 && (
                <span className="text-xs text-muted-foreground">{searchResults.length} 条</span>
              )}
            </div>
          )}

          <MessageList
            messages={messages}
            threadCounts={threadCounts}
            reactions={reactions}
            pendingMessages={Array.from(pending.values())}
            mentionsMe={new Set(messages.filter((m) => m.mentions.includes(currentUserId)).map((m) => m.id))}
            pinnedIds={pinnedIds}
            currentUserId={currentUserId}
            loadingMore={loadingMore}
            hasMore={!!nextCursor}
            onLoadMore={() => fetchMessages(nextCursor)}
            onDelete={handleDelete}
            onEdit={(m) => {
              const txt = window.prompt("编辑消息:", m.content);
              if (txt != null) void handleEdit(m, txt);
            }}
            onReply={(m) => setOpenThread(m)}
            onOpenThread={(m) => setOpenThread(m)}
            onPin={handlePin}
            onReact={handleReact}
            className="flex-1"
          />

          <MessageComposer
            members={room.members}
            onSend={handleSend}
            onAttach={handleAttach}
            onTyping={sendTyping}
          />

          {openThread && (
            <ThreadPanel
              roomId={roomId}
              parentMessage={openThread}
              members={room.members}
              currentUserId={currentUserId}
              reactions={reactions[openThread.id] || []}
              onClose={() => setOpenThread(null)}
              onReplied={() => {
                setThreadCounts((c) => ({ ...c, [openThread.id]: (c[openThread.id] ?? 0) + 1 }));
              }}
            />
          )}
        </div>
        <div className="md:hidden">
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push("/rooms")}
            className="fixed bottom-20 left-3 z-30"
          >
            ← 房间列表
          </Button>
        </div>
      </div>)</ErrorBoundary>
  );
}
