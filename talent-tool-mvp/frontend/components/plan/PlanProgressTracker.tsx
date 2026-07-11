"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { checkin, type PlanProgress, type PlanItemProgress } from "@/lib/api-plan";
import { PlanAdjustmentDialog } from "./PlanAdjustmentDialog";
import { CheckCircle2, Clock, Flame, AlertTriangle } from "lucide-react";

interface Props {
  userId: string;
  data: PlanProgress;
  onChanged?: () => void;
}

const PRIORITY_COLOR: Record<string, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-slate-100 text-slate-700",
};

const BUCKET_LABEL: Record<string, string> = {
  short: "短期",
  mid: "中期",
  long: "长期",
};

export function PlanProgressTracker({ userId, data, onChanged }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [delta, setDelta] = useState(0.1);

  async function doCheckin(item: PlanItemProgress) {
    setBusy(item.title);
    try {
      await checkin(userId, item.title, delta, note);
      setNote("");
      onChanged?.();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">总体进度</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between text-sm">
            <span>完成度</span>
            <span className="font-mono">
              {(data.overall_progress * 100).toFixed(0)}%
            </span>
          </div>
          <Progress value={data.overall_progress * 100} className="mt-2" />
        </CardContent>
      </Card>

      {data.stale_items && data.stale_items.length > 0 && (
        <Card className="border-amber-300 bg-amber-50">
          <CardContent className="flex items-start gap-2 p-3 text-sm">
            <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600" />
            <div>
              <p className="font-medium text-amber-900">需要关注</p>
              <ul className="mt-1 list-disc pl-4 text-xs text-amber-800">
                {data.stale_items.map((t) => (
                  <li key={t}>{t} 已超过 14 天未推进</li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {data.items.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            暂无计划项,请先生成职业规划
          </p>
        )}
        {data.items.map((item) => (
          <Card key={item.title}>
            <CardContent className="space-y-2 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-sm font-semibold">{item.title}</h4>
                    <Badge
                      variant="secondary"
                      className={PRIORITY_COLOR[item.priority] || ""}
                    >
                      {item.priority}
                    </Badge>
                    <Badge variant="outline">{BUCKET_LABEL[item.bucket]}</Badge>
                    {item.completed && (
                      <Badge className="bg-green-100 text-green-700">
                        <CheckCircle2 className="mr-1 h-3 w-3" />
                        已完成
                      </Badge>
                    )}
                  </div>
                  <p className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    {item.duration || "未排期"}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <Popover>
                    <PopoverTrigger>
                      <Button size="sm" variant="outline" className="gap-1">
                        <Flame className="h-3.5 w-3.5" />
                        打卡
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-72 space-y-2">
                      <p className="text-sm font-medium">推进进度</p>
                      <Input
                        type="number"
                        min={0.05}
                        max={1}
                        step={0.05}
                        value={delta}
                        onChange={(e) =>
                          setDelta(Math.min(1, Math.max(0.05, parseFloat(e.target.value || "0.1"))))
                        }
                      />
                      <Textarea
                        placeholder="备注 (可选)"
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                      />
                      <Button
                        size="sm"
                        className="w-full"
                        disabled={busy === item.title}
                        onClick={() => doCheckin(item)}
                      >
                        {busy === item.title ? "提交中…" : `+${(delta * 100).toFixed(0)}% 打卡`}
                      </Button>
                    </PopoverContent>
                  </Popover>
                  <PlanAdjustmentDialog
                    userId={userId}
                    itemTitle={item.title}
                    onAdjusted={onChanged}
                  />
                </div>
              </div>
              <Progress value={item.progress * 100} />
              <p className="text-right text-xs text-muted-foreground">
                {(item.progress * 100).toFixed(0)}%
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default PlanProgressTracker;