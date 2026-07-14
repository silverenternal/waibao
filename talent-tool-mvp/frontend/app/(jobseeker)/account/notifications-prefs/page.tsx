"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v8.1 T3603 — 通知偏好设置
 *
 * 控制:
 *   - 每天最多 N 条
 *   - 静默时间
 *   - 哪些 trigger 接收
 */

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { QuietHoursPicker } from "@/components/notifications/QuietHoursPicker";

const TRIGGERS = [
  { id: "re_engage_3d", label: "3 天没互动提醒", defaultOn: true },
  { id: "long_break", label: "长假结束问候", defaultOn: true },
  { id: "new_jobs", label: "新职位汇总", defaultOn: true },
  { id: "interview_tomorrow", label: "面试前一天提醒", defaultOn: true },
  { id: "offer_followup", label: "Offer 谈判跟进", defaultOn: true },
  { id: "festival_return", label: "节日 / 长假后", defaultOn: false },
];

export default function NotificationPrefsPage() {
  const [maxPerDay, setMaxPerDay] = React.useState(3);
  const [quietStart, setQuietStart] = React.useState<string | null>("22:00");
  const [quietEnd, setQuietEnd] = React.useState<string | null>("08:00");
  const [enabled, setEnabled] = React.useState<Record<string, boolean>>(
    () => Object.fromEntries(TRIGGERS.map((t) => [t.id, t.defaultOn])),
  );
  const [saved, setSaved] = React.useState(false);

  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 space-y-4 max-w-2xl">
        <h1 className="text-2xl font-bold">通知偏好</h1>
        <Card className="p-4 space-y-4">
          <div>
            <Label>每天最多推送条数</Label>
            <Input
              type="number"
              min="0"
              max="20"
              value={maxPerDay}
              onChange={(e) => setMaxPerDay(parseInt(e.target.value || "0", 10))}
              className="mt-1"
            />
          </div>
          <QuietHoursPicker
            start={quietStart}
            end={quietEnd}
            onChange={(s, e) => {
              setQuietStart(s);
              setQuietEnd(e);
            }}
          />
          <div>
            <Label className="mb-2 block">订阅触发</Label>
            <div className="space-y-2">
              {TRIGGERS.map((t) => (
                <label
                  key={t.id}
                  className="flex items-center justify-between p-2 bg-slate-50 rounded"
                >
                  <span className="text-sm">{t.label}</span>
                  <input
                    type="checkbox"
                    checked={enabled[t.id] ?? false}
                    onChange={(e) =>
                      setEnabled((p) => ({ ...p, [t.id]: e.target.checked }))
                    }
                  />
                </label>
              ))}
            </div>
          </div>
          <Button
            onClick={() => {
              setSaved(true);
              setTimeout(() => setSaved(false), 2000);
            }}
          >
            保存偏好
          </Button>
          {saved ? (
            <p className="text-sm text-green-600">已保存</p>
          ) : null}
        </Card>
      </div>)</ErrorBoundary>
  );
}