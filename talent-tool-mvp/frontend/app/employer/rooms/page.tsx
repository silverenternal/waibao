"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Rooms list page (T608).
 *
 * /rooms - 我参与的房间列表
 *
 * 顶部 toolbar 显示 total_unread, 主区域为 RoomSidebar
 * 弹窗 (NewRoomDialog) 用于创建.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { Plus, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { UnreadBadge } from "@/components/rooms/UnreadBadge";
import { RoomSidebar } from "@/components/rooms/RoomSidebar";
import { roomsApi, ROOM_TYPES, type RoomType } from "@/lib/api-rooms";
import { toast } from "sonner";

export default function RoomsListPage() {
  const router = useRouter();
  const [rooms, setRooms] = React.useState<
    Awaited<ReturnType<typeof roomsApi.listRooms>>["rooms"]
  >([]);
  const [totalUnread, setTotalUnread] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [createOpen, setCreateOpen] = React.useState(false);

  const fetch = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await roomsApi.listRooms();
      setRooms(res.rooms);
      setTotalUnread(res.total_unread);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(err);
      toast.error("载入房间失败");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void fetch();
  }, [fetch]);

  return (
    <ErrorBoundary>(<div className="flex h-[calc(100vh-3.5rem)] w-full flex-col md:flex-row">
        <div className="md:hidden">
          <RoomSidebar rooms={rooms} loading={loading} onCreate={() => setCreateOpen(true)} />
        </div>
        <div className="hidden md:block">
          <RoomSidebar rooms={rooms} loading={loading} onCreate={() => setCreateOpen(true)} />
        </div>
        <main className="flex-1 flex flex-col items-center justify-center p-8 text-center">
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              载入中...
            </div>
          ) : rooms.length === 0 ? (
            <EmptyState onCreate={() => setCreateOpen(true)} />
          ) : (
            <InlineSummary totalUnread={totalUnread} />
          )}
        </main>
        <NewRoomDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          onCreated={(room) => {
            setCreateOpen(false);
            void fetch();
            router.push(`/rooms/${room.id}`);
          }}
        />
      </div>)</ErrorBoundary>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="max-w-md">
      <div className="text-lg font-semibold mb-1">还没有协同房间</div>
      <p className="text-sm text-muted-foreground mb-4">
        把老板 / HR / 部门负责人 / 财务 / 管理员邀请到一个房间, 实时讨论招聘决策.
      </p>
      <Button onClick={onCreate}>
        <Plus className="h-4 w-4 mr-2" />
        创建第一个房间
      </Button>
    </div>
  );
}

function InlineSummary({ totalUnread }: { totalUnread: number }) {
  return (
    <div className="text-muted-foreground">
      <div className="text-sm">共 <strong>{totalUnread}</strong> 条未读</div>
      <UnreadBadge count={totalUnread} className="mt-3 inline-flex" />
      <div className="mt-4 text-xs">从左侧选择一个房间开始聊天</div>
    </div>
  );
}

interface NewRoomDialogProps {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  onCreated: (room: { id: string; name: string }) => void;
}

function NewRoomDialog({ open, onOpenChange, onCreated }: NewRoomDialogProps) {
  const [name, setName] = React.useState("");
  const [type, setType] = React.useState<RoomType>("group");
  const [members, setMembers] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  async function submit() {
    if (!name.trim()) {
      toast.error("房间名必填");
      return;
    }
    setBusy(true);
    try {
      const room = await roomsApi.createRoom({
        name: name.trim(),
        type,
        members: members.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean),
      });
      toast.success(`已创建房间 ${room.name}`);
      onCreated({ id: room.id, name: room.name });
      setName("");
      setMembers("");
    } catch (err) {
      toast.error((err as Error).message || "创建失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新建协同房间</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="room-name">房间名</Label>
            <Input
              id="room-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如 Q3 招聘评审"
              maxLength={200}
            />
          </div>
          <div>
            <Label htmlFor="room-type">类型</Label>
            <Select value={type} onValueChange={(v) => setType(v as RoomType)}>
              <SelectTrigger id="room-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROOM_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="room-members">成员 (邮箱 / UUID, 用逗号或空格分隔)</Label>
            <Textarea
              id="room-members"
              value={members}
              onChange={(e) => setMembers(e.target.value)}
              placeholder="hr@firm.com, dept-lead@firm.com, finance@firm.com"
              rows={3}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            取消
          </Button>
          <Button onClick={submit} disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            创建
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
