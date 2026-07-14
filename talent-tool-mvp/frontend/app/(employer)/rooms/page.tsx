"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Collab Rooms — Cal.com/Linear-style collaborative spaces.
 *
 * Two-pane layout:
 *   - Left rail: room list (pinned / recent), search, + new
 *   - Right pane: welcome state with quick links to candidate -> room
 *     because the room composition primitives take concrete props we
 *     deliberately keep the URL-driven creation flow light here.
 *
 * In production, the right pane would mount `<MessageList />`,
 * `<MessageComposer />`, etc. — these are imported on the per-room detail
 * page so the page stays static and route-fast.
 */

import * as React from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Plus, Search, Pin, Users2 } from "lucide-react";

interface RoomRow {
  id: string;
  title: string;
  unread: number;
  pinned: boolean;
  members: number;
  lastAt: string;
  preview: string;
}

const ROOMS: RoomRow[] = [
  { id: "rm-1", title: "候选人 · 陈诺 — 面试", unread: 2, pinned: true, members: 4, lastAt: "10:42", preview: "我对 Next.js 16 熟悉,最近在做…" },
  { id: "rm-2", title: "高管评审 · Q2 招聘战略", unread: 0, pinned: true, members: 6, lastAt: "昨天", preview: "国际化扩招预算已经批了 ~" },
  { id: "rm-3", title: "画像澄清 · 周野", unread: 0, pinned: false, members: 2, lastAt: "昨天", preview: "算法方向的偏好我已经同步了" },
  { id: "rm-4", title: "海外 BD 团队", unread: 1, pinned: false, members: 8, lastAt: "周一", preview: "Maya, 第二批简历我看完了" },
  { id: "rm-5", title: "复盘 · Q1 招聘漏斗", unread: 0, pinned: false, members: 3, lastAt: "上周", preview: "转化率提升在 HR 主动建议之后…" },
];

export default function RoomsPage() {
  const [q, setQ] = React.useState("");
  const filtered = ROOMS.filter((r) => (q ? r.title.toLowerCase().includes(q.toLowerCase()) : true));
  const pinned = filtered.filter((r) => r.pinned);
  const others = filtered.filter((r) => !r.pinned);

  return (
    <ErrorBoundary>(<div className="grid h-[calc(100vh-7rem)] grid-cols-1 gap-3 p-3 md:p-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <Card className="flex flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b p-3">
            <h1 className="text-sm font-semibold">协同空间</h1>
            <Button size="icon" variant="ghost" aria-label="新空间">
              <Plus className="h-4 w-4" />
            </Button>
          </div>
          <div className="relative border-b p-3">
            <Search className="absolute left-5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索房间..."
              className="pl-8 text-xs"
              aria-label="搜索房间"
            />
          </div>
          <div className="flex-1 overflow-y-auto p-2 text-sm">
            {pinned.length > 0 && (
              <div className="mb-3">
                <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  <Pin className="mr-1 inline h-3 w-3" /> 置顶
                </div>
                {pinned.map((r) => <RoomRowItem key={r.id} room={r} />)}
              </div>
            )}
            <div className="mb-1 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              最近
            </div>
            {others.map((r) => <RoomRowItem key={r.id} room={r} />)}
          </div>
          <div className="border-t p-2 text-xs text-muted-foreground">共 {ROOMS.length} 个空间</div>
        </Card>
        <div className="flex flex-col items-center justify-center rounded-xl border bg-card p-8 text-center">
          <Users2 className="h-10 w-10 text-muted-foreground" />
          <h2 className="mt-3 text-lg font-semibold">选择一个空间开始协同</h2>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">
            左侧列表点击进入,或打开候选人后从详情页直接打开 / 进入专属空间。
          </p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            <Button asChild>
              <Link href="/employer/candidates">
                候选人列表
              </Link>
            </Button>
            <Button variant="outline">+ 新建空间</Button>
          </div>
        </div>
      </div>)</ErrorBoundary>
  );
}

function RoomRowItem({ room }: { room: RoomRow }) {
  return (
    <Link
      href={`/employer/rooms/${room.id}`}
      className="flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-muted/60"
    >
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded bg-primary/10 text-xs">
        {room.title.charAt(0)}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className="truncate font-medium">{room.title}</span>
          {room.unread > 0 && (
            <Badge variant="destructive" className="text-[10px]">
              {room.unread}
            </Badge>
          )}
        </div>
        <p className="truncate text-xs text-muted-foreground">{room.preview}</p>
        <p className="mt-0.5 text-[10px] text-muted-foreground">
          {room.members} 人 · {room.lastAt}
        </p>
      </div>
    </Link>
  );
}
