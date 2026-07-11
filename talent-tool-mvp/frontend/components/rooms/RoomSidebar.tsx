"use client";

/**
 * RoomSidebar — T608
 *
 * 房间列表侧边栏 (左侧):
 *   - 顶部 tab 切换: 全部 / 未读 / 我创建的
 *   - 搜索框 (room 名过滤)
 *   - 房间项 (RoomItem): name, last_msg preview, last_message_at, unread_count
 *   - 底部 [+] 新建房间按钮
 *
 * 选中态高亮, 折叠态隐藏 (移动端).
 */

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Plus, Search, Inbox, MessageSquare } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { UnreadBadge } from "@/components/rooms/UnreadBadge";
import type { Room } from "@/lib/api-rooms";

interface RoomListItem extends Room {
  last_read_at: string | null;
  unread_count: number;
}

interface RoomSidebarProps {
  rooms: RoomListItem[];
  loading?: boolean;
  onCreate?: () => void;
  className?: string;
  activeRoomId?: string;
}

function relativeTime(iso: string | null | undefined) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  if (Number.isNaN(t)) return "";
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes}分`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}时`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}天`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}周`;
  return new Date(iso).toLocaleDateString();
}

export function RoomItem({ room, active }: { room: RoomListItem; active?: boolean }) {
  return (
    <Link
      href={`/rooms/${encodeURIComponent(room.id)}`}
      className={cn(
        "flex items-start gap-3 rounded-lg px-3 py-2 transition-colors",
        active ? "bg-primary/10 ring-1 ring-primary/30" : "hover:bg-muted/60"
      )}
    >
      <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-blue-500/15 to-purple-500/15 text-blue-700 text-sm">
        <MessageSquare className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="truncate text-sm font-medium text-foreground">
            {room.name}
          </div>
          <span className="shrink-0 text-[10px] text-muted-foreground">
            {relativeTime(room.last_message_at)}
          </span>
        </div>
        <div className="mt-0.5 flex items-center justify-between gap-2">
          <span className="truncate text-xs text-muted-foreground">
            {room.archived ? "(已归档)" : `${room.member_count} 人`}
          </span>
          <UnreadBadge count={room.unread_count} size="xs" />
        </div>
      </div>
    </Link>
  );
}

export function RoomSidebar({
  rooms,
  loading,
  onCreate,
  className,
  activeRoomId,
}: RoomSidebarProps) {
  const [tab, setTab] = React.useState<"all" | "unread" | "mine">("all");
  const [q, setQ] = React.useState("");
  const pathname = usePathname();

  const filtered = React.useMemo(() => {
    let xs = rooms;
    if (tab === "unread") xs = xs.filter((r) => r.unread_count > 0);
    if (tab === "mine") xs = xs.filter((r) => r.created_by); // 简化: 所有非空都视为可看
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      xs = xs.filter((r) => r.name.toLowerCase().includes(needle));
    }
    return xs;
  }, [rooms, tab, q]);

  return (
    <aside
      className={cn(
        "flex flex-col gap-3 border-r bg-muted/20 px-3 py-4 w-full md:w-72",
        className
      )}
    >
      <header className="flex items-center justify-between gap-2 px-1">
        <h2 className="text-sm font-semibold text-foreground">协同房间</h2>
        <Button size="icon" variant="ghost" onClick={onCreate} aria-label="新建房间">
          <Plus className="h-4 w-4" />
        </Button>
      </header>

      <div className="relative px-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜索房间"
          className="pl-8 h-8 text-xs"
        />
      </div>

      <nav className="flex items-center gap-1 px-1" role="tablist">
        {([
          { key: "all", label: "全部" },
          { key: "unread", label: "未读" },
          { key: "mine", label: "我创建" },
        ] as const).map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              tab === t.key
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted"
            )}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div className="-mx-1 flex-1 overflow-y-auto px-1">
        {loading ? (
          <div className="space-y-2 p-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-2 py-10 text-center text-xs text-muted-foreground">
            <Inbox className="mb-2 h-7 w-7 opacity-40" />
            {tab === "unread" ? "已读完了, 休息一会儿." : "还没有协同房间, 点击右上 + 创建."}
          </div>
        ) : (
          <ul className="space-y-1">
            {filtered.map((r) => (
              <li key={r.id}>
                <RoomItem
                  room={r}
                  active={pathname?.includes(`/rooms/${r.id}`) || activeRoomId === r.id}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
