"use client";

/**
 * RoomHeader — T608
 *
 * 顶部房间头:
 *   - 左: 房间名 + 类型 chip + 成员头像堆叠 (前 5)
 *   - 中: 在线状态指示 (绿点 = 当前有 WS 连接 + 心跳)
 *   - 右: 搜索按钮, 置顶消息, 房间信息菜单
 */

import * as React from "react";
import {
  Pin,
  Search,
  Info,
  Users,
  CircleDot,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { RoomMember, RoomType } from "@/lib/api-rooms";
import { ROLE_LABEL } from "@/lib/api-rooms";

// 兜底: 没有 tooltip 组件时, 用 title 属性代替
const Tooltip = ({ children }: { children: React.ReactNode }) => <>{children}</>;
const TooltipTrigger = ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) =>
  asChild ? <>{children}</> : <span>{children}</span>;
const TooltipContent = ({ children }: { children: React.ReactNode }) => <>{children}</>;
const TooltipProvider = ({ children, delayDuration: _d }: { children: React.ReactNode; delayDuration?: number }) => <>{children}</>;

interface RoomHeaderProps {
  name: string;
  type: RoomType;
  members: RoomMember[];
  onlineUserIds: Set<string>;
  pinnedCount: number;
  wsStatus: "idle" | "connecting" | "open" | "closed" | "error";
  onToggleSearch?: () => void;
  onShowPins?: () => void;
  onShowInfo?: () => void;
  onLeave?: () => void;
  className?: string;
}

function AvatarStack({
  members,
  onlineUserIds,
  max = 5,
}: {
  members: RoomMember[];
  onlineUserIds: Set<string>;
  max?: number;
}) {
  const sliced = members.slice(0, max);
  const remaining = members.length - sliced.length;
  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex -space-x-2">
        {sliced.map((m, i) => {
          const initials = (m.user_id.slice(0, 2)).toUpperCase();
          const online = onlineUserIds.has(m.user_id);
          return (
            <Tooltip key={m.user_id}>
              <TooltipTrigger {...({ asChild: true } as any)}>
                <div
                  className={cn(
                    "relative h-7 w-7 rounded-full border-2 border-background text-[10px] font-semibold text-white flex items-center justify-center shadow-sm",
                    "bg-gradient-to-br",
                    i % 5 === 0
                      ? "from-blue-500 to-blue-700"
                      : i % 5 === 1
                      ? "from-purple-500 to-purple-700"
                      : i % 5 === 2
                      ? "from-emerald-500 to-emerald-700"
                      : i % 5 === 3
                      ? "from-amber-500 to-amber-700"
                      : "from-rose-500 to-rose-700"
                  )}
                  title={`${m.user_id} (${ROLE_LABEL[m.role]})`}
                >
                  {initials}
                  {online && (
                    <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-emerald-500 border-2 border-background" />
                  )}
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs">
                  {m.user_id} · {ROLE_LABEL[m.role]}
                  {online ? " · 在线" : ""}
                </p>
              </TooltipContent>
            </Tooltip>
          );
        })}
        {remaining > 0 && (
          <div className="h-7 w-7 rounded-full bg-muted border-2 border-background flex items-center justify-center text-[10px] font-medium text-muted-foreground">
            +{remaining}
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}

const WS_STATUS_LABEL: Record<RoomHeaderProps["wsStatus"], string> = {
  idle: "未连接",
  connecting: "连接中",
  open: "实时同步中",
  closed: "已断开",
  error: "连接异常",
};

const WS_STATUS_COLOR: Record<RoomHeaderProps["wsStatus"], string> = {
  idle: "bg-slate-400",
  connecting: "bg-amber-500",
  open: "bg-emerald-500",
  closed: "bg-slate-400",
  error: "bg-rose-500",
};

export function RoomHeader({
  name,
  type,
  members,
  onlineUserIds,
  pinnedCount,
  wsStatus,
  onToggleSearch,
  onShowPins,
  onShowInfo,
  onLeave,
  className,
}: RoomHeaderProps) {
  return (
    <header
      className={cn(
        "flex items-center justify-between gap-3 border-b bg-background/95 backdrop-blur px-4 py-2",
        className
      )}
    >
      <div className="min-w-0 flex-1 flex items-center gap-3">
        <h1 className="truncate text-base font-semibold text-foreground">
          {name}
        </h1>
        <Badge variant="secondary" className="text-xs capitalize">
          {type}
        </Badge>
        <div className="hidden md:flex items-center gap-1.5 text-xs text-muted-foreground">
          <CircleDot className={cn("h-2.5 w-2.5 fill-current", WS_STATUS_COLOR[wsStatus])} />
          <span>{WS_STATUS_LABEL[wsStatus]}</span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <AvatarStack members={members} onlineUserIds={onlineUserIds} max={5} />

        <TooltipProvider delayDuration={150}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="icon" variant="ghost" onClick={onShowPins} aria-label="查看置顶">
                <Pin className="h-4 w-4" />
                {pinnedCount > 0 && (
                  <span className="ml-1 inline-flex items-center justify-center h-4 min-w-4 rounded-full bg-amber-500 text-white text-[10px] px-1">
                    {pinnedCount}
                  </span>
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{pinnedCount > 0 ? `${pinnedCount} 条置顶` : "置顶消息"}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="icon" variant="ghost" onClick={onToggleSearch} aria-label="搜索消息">
                <Search className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>搜索</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="icon" variant="ghost" onClick={onShowInfo} aria-label="房间信息">
                <Info className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              房间信息 ({members.length} 人 · 在线 {onlineUserIds.size})
            </TooltipContent>
          </Tooltip>

          {onLeave && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button size="icon" variant="ghost" onClick={onLeave} aria-label="离开房间">
                  <Users className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>离开 / 归档</TooltipContent>
            </Tooltip>
          )}
        </TooltipProvider>
      </div>
    </header>
  );
}
