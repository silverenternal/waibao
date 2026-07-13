"use client";

/**
 * v8.1 T3605 — ProfileConfirmCard
 *
 * 显示 AI 理解的我 面板 (4 部分):
 *   - 基础信息
 *   - 性格特质
 *   - 真实需求
 *   - 能力图谱
 *
 * 每个字段可点赞 / 修正. 修正写回 Mem0.
 */

import * as React from "react";
import { Check, Edit2, ThumbsUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface ProfileField {
  path: string;
  value: string;
  reasoning?: string;
  confidence?: number;
  sources?: string[];
}

export interface ProfileConfirmCardProps {
  fields: ProfileField[];
  section: "basic" | "personality" | "needs" | "skills";
  onUpvote?: (fieldPath: string) => Promise<void> | void;
  onCorrect?: (fieldPath: string, newValue: string, reason?: string) => Promise<void> | void;
  className?: string;
}

const SECTION_TITLE = {
  basic: "基础信息",
  personality: "性格特质",
  needs: "真实需求",
  skills: "能力图谱",
} as const;

export function ProfileConfirmCard({
  fields,
  section,
  onUpvote,
  onCorrect,
  className,
}: ProfileConfirmCardProps) {
  const [editingPath, setEditingPath] = React.useState<string | null>(null);
  const [editValue, setEditValue] = React.useState("");

  return (
    <Card className={cn("p-4", className)}>
      <h3 className="text-sm font-semibold text-slate-800 mb-3">
        {SECTION_TITLE[section]}
      </h3>
      <div className="space-y-3">
        {fields.map((f) => (
          <div key={f.path} className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500 font-mono">
                {f.path}
              </span>
              {typeof f.confidence === "number" ? (
                <Badge
                  variant="outline"
                  className={cn(
                    "text-xs",
                    f.confidence >= 0.8
                      ? "border-green-300 text-green-700"
                      : f.confidence >= 0.5
                      ? "border-yellow-300 text-yellow-700"
                      : "border-red-300 text-red-700",
                  )}
                >
                  {Math.round(f.confidence * 100)}%
                </Badge>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              {editingPath === f.path ? (
                <>
                  <Input
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    className="flex-1 h-8"
                  />
                  <Button
                    size="sm"
                    variant="default"
                    onClick={() => {
                      onCorrect?.(f.path, editValue);
                      setEditingPath(null);
                    }}
                  >
                    <Check className="w-3 h-3" />
                  </Button>
                </>
              ) : (
                <span className="text-sm text-slate-800 flex-1">
                  {f.value}
                </span>
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onUpvote?.(f.path)}
                aria-label="点赞"
              >
                <ThumbsUp className="w-3 h-3" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditingPath(f.path);
                  setEditValue(f.value);
                }}
                aria-label="修正"
              >
                <Edit2 className="w-3 h-3" />
              </Button>
            </div>
            {f.reasoning ? (
              <p className="text-xs text-slate-500 italic">{f.reasoning}</p>
            ) : null}
            {f.sources && f.sources.length > 0 ? (
              <div className="flex gap-1 flex-wrap">
                {f.sources.map((s, i) => (
                  <Badge key={i} variant="secondary" className="text-xs">
                    {s}
                  </Badge>
                ))}
              </div>
            ) : null}
            {typeof f.confidence === "number" ? (
              <div className="h-1.5 bg-slate-100 rounded">
                <div
                  className="h-full bg-blue-500 rounded"
                  style={{ width: `${Math.round(f.confidence * 100)}%` }}
                />
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </Card>
  );
}

export default ProfileConfirmCard;