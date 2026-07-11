"use client";

/**
 * EmotionEventDetail (T605)
 *
 * Side-panel detail card shown when the user clicks a point on the
 * emotion timeline. Mirrors the per-row data the timeline tooltip uses
 * but adds a richer layout: emotion badge, intensity meter, trigger
 * quote, optional journal crossing-link.
 */

import * as React from "react";
import {
  Heart,
  Activity,
  AlertCircle,
  Quote,
  FileText,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export interface EmotionEventDetailData {
  recorded_at: string;
  primary_emotion?: string | null;
  sentiment?: number | null;
  intensity?: number | null;
  trigger_text?: string | null;
  needs_attention?: boolean;
  journal_id?: string | null;
  journal_rating?: string | null;
  journal_content?: string | null;
}

export interface EmotionEventDetailProps {
  event: EmotionEventDetailData | null;
  onClose?: () => void;
  onOpenJournal?: (journalId: string) => void;
  className?: string;
}

export function EmotionEventDetail({
  event,
  onClose,
  onOpenJournal,
  className,
}: EmotionEventDetailProps) {
  if (!event) {
    return (
      <Card className={cn("border-dashed", className)}>
        <CardContent className="flex items-center gap-2 py-6 text-xs text-slate-500">
          <Heart className="size-4 text-slate-400" />
          点击折线上的任意一点,查看当日情绪详情。
        </CardContent>
      </Card>
    );
  }
  const sentiment = clamp(event.sentiment ?? 0);
  const intensityPct = clampPct((event.intensity ?? 0) * 100);
  const sentimentPct = ((sentiment + 1) / 2) * 100;
  const isAlert = !!event.needs_attention;

  return (
    <Card className={cn(isAlert ? "border-rose-200 bg-rose-50/30" : "border-slate-200", className)}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          {isAlert ? (
            <AlertCircle className="size-4 text-rose-500" />
          ) : (
            <Heart className="size-4 text-pink-500" />
          )}
          <span>{event.primary_emotion || "情绪记录"}</span>
          <span className="ml-2 text-[10px] text-slate-500">
            {new Date(event.recorded_at).toLocaleString("en-GB", {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </span>
          {onClose && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="ml-auto h-7 w-7 p-0"
              aria-label="关闭"
            >
              <X className="size-4" />
            </Button>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <div className="mb-1 flex items-center justify-between gap-2 text-[11px] text-slate-500">
            <span className="inline-flex items-center gap-1">
              <Activity className="size-3" />
              情绪倾向
            </span>
            <span className="tabular-nums">{sentiment.toFixed(2)} ({Math.round(sentimentPct)})</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-gradient-to-r from-rose-200 via-slate-200 to-emerald-200">
            <div
              className="h-full rounded-full bg-indigo-500/80"
              style={{ width: `${Math.max(2, Math.round(sentimentPct))}%` }}
            />
          </div>
        </div>

        {event.intensity != null && (
          <div>
            <div className="mb-1 flex items-center justify-between gap-2 text-[11px] text-slate-500">
              <span>强度</span>
              <span className="tabular-nums">{Math.round(intensityPct)}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-200">
              <div
                className={cn(
                  "h-full rounded-full",
                  intensityPct > 66
                    ? "bg-rose-500"
                    : intensityPct > 33
                      ? "bg-amber-500"
                      : "bg-emerald-500",
                )}
                style={{ width: `${Math.max(2, Math.round(intensityPct))}%` }}
              />
            </div>
          </div>
        )}

        {event.trigger_text && (
          <div className="rounded-md border border-blue-200 bg-blue-50/40 p-2 text-[11px] text-slate-700">
            <div className="mb-1 inline-flex items-center gap-1 text-blue-700">
              <Quote className="size-3" />
              触发片段
            </div>
            <blockquote className="italic">"{event.trigger_text}"</blockquote>
          </div>
        )}

        {event.journal_id && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenJournal?.(event.journal_id!)}
            className="w-full gap-2"
          >
            <FileText className="size-3.5" />
            查看当日日记
          </Button>
        )}

        {isAlert && (
          <Badge variant="outline" className="border-rose-300 bg-rose-100 text-rose-700">
            当日需要关注 — 建议联系 HR / 心理援助
          </Badge>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function clamp(v: number): number {
  return Math.max(-1, Math.min(1, v));
}
function clampPct(v: number): number {
  return Math.max(0, Math.min(100, v));
}
