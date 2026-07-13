"use client";

/**
 * v8.1 T3606 — CheckinModal
 *
 * 每日打卡对话框: 选任务 / 写 note / 推进进度.
 */

import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export interface CheckinModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: { title: string }[];
  onSubmit: (itemTitle: string, note: string) => Promise<void> | void;
}

export function CheckinModal({
  open,
  onOpenChange,
  items,
  onSubmit,
}: CheckinModalProps) {
  const [selected, setSelected] = React.useState<string>("");
  const [note, setNote] = React.useState("");

  React.useEffect(() => {
    if (open) {
      setSelected(items[0]?.title ?? "");
      setNote("");
    }
  }, [open, items]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>每日打卡</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium">选择任务</label>
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="w-full mt-1 p-2 border rounded"
            >
              {items.map((it) => (
                <option key={it.title} value={it.title}>
                  {it.title}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium">今日心得 (可选)</label>
            <Textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="记录今天做了什么、遇到什么困难..."
              className="mt-1"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={async () => {
              await onSubmit(selected, note);
              onOpenChange(false);
            }}
          >
            打卡
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default CheckinModal;