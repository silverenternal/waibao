"use client";

/**
 * v8.1 T3601 — 个性化 ChatBubble
 *
 * 根据 relationship 阶段显示不同的:
 *   - avatar 表情 (wave/smile/heart/briefcase/tada)
 *   - 语气 (friendly/casual/gentle/formal/celebratory)
 *   - 欢迎语模板
 *
 * 数据来自 backend /api/v8_1/relationship/state
 */

import * as React from "react";
import {
  Briefcase,
  Heart,
  Smile,
  Sparkles,
  Waves,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";

export type RelationshipTone =
  | "friendly"
  | "casual"
  | "gentle"
  | "formal"
  | "celebratory";

export interface ChatBubbleProps {
  greeting: string;
  tone?: RelationshipTone;
  avatar?: "wave" | "smile" | "heart" | "briefcase" | "tada";
  stage?: string;
  className?: string;
}

const AVATAR_ICON: Record<NonNullable<ChatBubbleProps["avatar"]>, React.ComponentType<{ className?: string }>> = {
  wave: Waves,
  smile: Smile,
  heart: Heart,
  briefcase: Briefcase,
  tada: Sparkles,
};

const TONE_STYLES: Record<RelationshipTone, string> = {
  friendly: "from-blue-50 to-indigo-50 border-blue-200",
  casual: "from-green-50 to-emerald-50 border-green-200",
  gentle: "from-pink-50 to-rose-50 border-pink-200",
  formal: "from-slate-50 to-gray-50 border-slate-200",
  celebratory: "from-yellow-50 to-amber-50 border-amber-200",
};

export function ChatBubble({
  greeting,
  tone = "friendly",
  avatar = "wave",
  stage,
  className,
}: ChatBubbleProps) {
  const Icon = AVATAR_ICON[avatar] ?? Waves;
  return (
    <Card
      className={cn(
        "p-4 bg-gradient-to-br",
        TONE_STYLES[tone],
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-10 h-10 rounded-full bg-white shadow-sm flex items-center justify-center">
          <Icon className="w-5 h-5 text-slate-700" aria-hidden="true" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-slate-800 leading-relaxed">
            {greeting}
          </p>
          {stage ? (
            <p className="mt-1 text-xs text-slate-500">阶段: {stage}</p>
          ) : null}
        </div>
      </div>
    </Card>
  );
}

export default ChatBubble;