"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
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
import { adjustPlan, type PlanAdjustAction } from "@/lib/api-plan";
import { Pencil } from "lucide-react";

interface Props {
  userId: string;
  itemTitle: string;
  onAdjusted?: () => void;
}

export function PlanAdjustmentDialog({
  userId,
  itemTitle,
  onAdjusted,
}: Props) {
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState<PlanAdjustAction>("delay");
  const [deltaDays, setDeltaDays] = useState(7);
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await adjustPlan(
        userId,
        action,
        itemTitle,
        detail,
        deltaDays,
      );
      setOpen(false);
      onAdjusted?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "调整失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger>
        <Button size="sm" variant="outline" className="gap-1">
          <Pencil className="h-3.5 w-3.5" />
          调整
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>调整计划项</DialogTitle>
          <DialogDescription>
            针对 <span className="font-medium">{itemTitle}</span> 进行调整
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1">
            <Label>动作</Label>
            <Select
              value={action}
              onValueChange={(v) => setAction(v as PlanAdjustAction)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="delay">推迟</SelectItem>
                <SelectItem value="accelerate">加速</SelectItem>
                <SelectItem value="replace">替换描述</SelectItem>
                <SelectItem value="remove">移除</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {(action === "delay" || action === "accelerate") && (
            <div className="space-y-1">
              <Label>天数 (delay + / accelerate -)</Label>
              <Input
                type="number"
                min={1}
                max={365}
                value={deltaDays}
                onChange={(e) =>
                  setDeltaDays(Math.max(1, parseInt(e.target.value || "1", 10)))
                }
              />
            </div>
          )}

          {(action === "replace" || action === "add") && (
            <div className="space-y-1">
              <Label>{action === "replace" ? "新描述" : "新行动项标题"}</Label>
              <Textarea
                value={detail}
                onChange={(e) => setDetail(e.target.value)}
                placeholder="例如:改学 Next.js 14 App Router"
              />
            </div>
          )}

          {error && (
            <p className="text-sm text-red-600" role="alert">
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            取消
          </Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? "提交中…" : "确认调整"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default PlanAdjustmentDialog;