"use client";

/**
 * v8.1 T3604 — EmotionCareCard
 *
 * 显示 emotion care ticket 的 actions + 资源.
 */

import * as React from "react";
import { Heart, Phone, Shield, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type CareLevel = "light" | "medium" | "heavy";

export interface CareTicket {
  id: string;
  user_id: string;
  level: CareLevel;
  risk_level: string;
  primary_emotion: string;
  trigger_text?: string;
  hr_notified?: boolean;
  created_at?: string;
  closed_at?: string | null;
}

export interface CareAction {
  action_id: string;
  user_id: string;
  level: CareLevel;
  action_type:
    | "warm_message"
    | "send_resource"
    | "schedule_hr_callback"
    | "notify_hr"
    | "send_crisis_resource";
  payload: Record<string, unknown>;
  result?: string;
}

const LEVEL_COLOR: Record<CareLevel, string> = {
  light: "bg-yellow-50 border-yellow-200",
  medium: "bg-orange-50 border-orange-200",
  heavy: "bg-rose-50 border-rose-200",
};

const LEVEL_LABEL: Record<CareLevel, string> = {
  light: "轻度关怀",
  medium: "中度关怀",
  heavy: "重度关怀",
};

const ACTION_LABEL: Record<CareAction["action_type"], string> = {
  warm_message: "温暖对话",
  send_resource: "减压资源",
  schedule_hr_callback: "HR 关怀窗口",
  notify_hr: "HR 通知",
  send_crisis_resource: "危机干预资源",
};

export interface EmotionCareCardProps {
  ticket: CareTicket;
  actions: CareAction[];
  onClose?: () => void;
  className?: string;
}

export function EmotionCareCard({
  ticket,
  actions,
  onClose,
  className,
}: EmotionCareCardProps) {
  return (
    <Card className={cn("p-4 border", LEVEL_COLOR[ticket.level], className)}>
      <div className="flex items-start gap-3">
        <Heart className="w-5 h-5 text-rose-600 mt-1" aria-hidden="true" />
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-sm font-semibold text-slate-800">
              {LEVEL_LABEL[ticket.level]}
            </h3>
            <Badge variant="outline" className="text-xs">
              {ticket.risk_level}
            </Badge>
            <Badge variant="secondary" className="text-xs">
              {ticket.primary_emotion}
            </Badge>
            {ticket.hr_notified ? (
              <Badge variant="destructive" className="text-xs">
                <Shield className="w-3 h-3 mr-1" /> HR 已通知
              </Badge>
            ) : null}
          </div>
          {ticket.trigger_text ? (
            <p className="mt-2 text-xs text-slate-600 italic">
              "{ticket.trigger_text}"
            </p>
          ) : null}
          <div className="mt-3 space-y-2">
            {actions.map((a) => (
              <CareActionRow key={a.action_id} action={a} />
            ))}
          </div>
        </div>
      </div>
      {onClose && !ticket.closed_at ? (
        <div className="mt-3 flex justify-end">
          <Button size="sm" variant="outline" onClick={onClose}>
            标记为已处理
          </Button>
        </div>
      ) : null}
      {ticket.closed_at ? (
        <p className="mt-2 text-xs text-slate-500">
          已于 {new Date(ticket.closed_at).toLocaleString()} 关闭
        </p>
      ) : null}
    </Card>
  );
}

function CareActionRow({ action }: { action: CareAction }) {
  return (
    <div className="flex items-start gap-2 p-2 bg-white/60 rounded">
      <Sparkles className="w-4 h-4 text-amber-500 mt-0.5" aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-800">
          {ACTION_LABEL[action.action_type]}
        </p>
        <pre className="text-xs text-slate-600 whitespace-pre-wrap break-all mt-1">
          {JSON.stringify(action.payload, null, 2)}
        </pre>
      </div>
      {action.action_type === "send_crisis_resource" ? (
        <Phone className="w-4 h-4 text-rose-600" aria-hidden="true" />
      ) : null}
    </div>
  );
}

export default EmotionCareCard;