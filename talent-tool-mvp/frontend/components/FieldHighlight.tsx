"use client";

import * as React from "react";
import { Sparkles, MessageCircleQuestion } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export type HighlightSeverity = "missing" | "weak";

export interface FieldHighlightProps {
  /** Field label shown above the input. */
  label: string;
  /** Currently stored value (empty / undefined ⇒ missing). */
  value?: string | string[] | number | null;
  /** Severity drives the red-vs-amber styling. */
  severity?: HighlightSeverity;
  /** Helper text shown beneath the label. */
  hint?: string;
  /** Click handler for the "一键补问" button — usually opens an AI drawer. */
  onAskAI?: () => void;
  /** When true, render the inline AI prompt box where the user can type their answer. */
  onConfirmValue?: (value: string) => Promise<void> | void;
  /** Question to pre-fill the AI prompt box. */
  aiQuestion?: string;
  /** Whether the multi-line textarea should be shown instead of a single-line input. */
  multiline?: boolean;
  /** Whether the field is currently loading (e.g. AI is filling it in). */
  loading?: boolean;
  /** Optional element rendered on the right side of the label row (e.g. status badge). */
  rightSlot?: React.ReactNode;
  className?: string;
}

/** A field input wrapper that highlights missing/weak values and offers an AI quick-fill action. */
export function FieldHighlight({
  label,
  value,
  severity = "missing",
  hint,
  onAskAI,
  onConfirmValue,
  aiQuestion,
  multiline = false,
  loading = false,
  rightSlot,
  className,
}: FieldHighlightProps) {
  const isMissing = severity === "missing";
  const isWeak = severity === "weak";
  const hasValue = isMeaningfulValue(value);

  // Show AI prompt only when the value is missing/weak AND the parent wired onConfirmValue.
  const showAIForm =
    !hasValue && Boolean(onConfirmValue || onAskAI);

  const [draft, setDraft] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  const handleSubmit = async () => {
    if (!draft.trim() || !onConfirmValue) return;
    setSubmitting(true);
    try {
      await onConfirmValue(draft.trim());
      setDraft("");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      data-severity={isMissing ? "missing" : isWeak ? "weak" : "ok"}
      className={cn(
        "rounded-lg border bg-card p-3 transition-colors",
        isMissing && "border-rose-300 bg-rose-50/40",
        isWeak && "border-amber-300 bg-amber-50/30",
        !isMissing && !isWeak && "border-border",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "text-sm font-medium",
              isMissing && "text-rose-700",
              isWeak && "text-amber-700",
            )}
          >
            {label}
          </span>
          {isMissing && (
            <Badge variant="destructive" className="h-5 px-1.5 text-[10px]">
              缺失
            </Badge>
          )}
          {isWeak && (
            <Badge
              variant="outline"
              className="h-5 border-amber-400 bg-amber-100 px-1.5 text-[10px] text-amber-700"
            >
              偏弱
            </Badge>
          )}
          {rightSlot}
        </div>

        {onAskAI && (
          <Button
            type="button"
            size="xs"
            variant={isMissing ? "destructive" : "outline"}
            onClick={onAskAI}
            disabled={loading}
          >
            <Sparkles className="size-3" />
            一键补问
          </Button>
        )}
      </div>

      {/* Hint */}
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}

      {/* Current value preview */}
      {hasValue && (
        <div className="mt-2 rounded-md bg-muted/50 px-3 py-2 text-sm">
          {Array.isArray(value) ? value.join("、") : String(value)}
        </div>
      )}

      {/* AI quick-fill form */}
      {showAIForm && (
        <div className="mt-3 rounded-md border border-dashed border-primary/40 bg-primary/5 p-3">
          <div className="flex items-start gap-2">
            <MessageCircleQuestion className="mt-0.5 size-4 shrink-0 text-primary" />
            <div className="flex-1 space-y-2">
              <p className="text-xs text-muted-foreground">
                {aiQuestion ?? `告诉我们你的${label},AI 会自动归档。`}
              </p>
              {onConfirmValue && (
                <div className="flex flex-col gap-2 sm:flex-row">
                  {multiline ? (
                    <Textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      placeholder={`例如:${placeholderFor(label)}`}
                      className="min-h-16 flex-1 bg-background"
                      disabled={submitting || loading}
                    />
                  ) : (
                    <Input
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      placeholder={`例如:${placeholderFor(label)}`}
                      className="flex-1 bg-background"
                      disabled={submitting || loading}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          void handleSubmit();
                        }
                      }}
                    />
                  )}
                  <Button
                    type="button"
                    size="sm"
                    onClick={handleSubmit}
                    disabled={submitting || loading || !draft.trim()}
                    className="shrink-0"
                  >
                    {submitting ? "保存中…" : "保存"}
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function isMeaningfulValue(v: FieldHighlightProps["value"]): boolean {
  if (v === undefined || v === null) return false;
  if (typeof v === "string") return v.trim().length > 0;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === "number") return Number.isFinite(v);
  return true;
}

function placeholderFor(label: string): string {
  // Tiny heuristic so the placeholder isn't blank — call sites can always override.
  if (/技能/i.test(label)) return "React, TypeScript, Node.js";
  if (/经验|年限/i.test(label)) return "5 年";
  if (/期望|薪资|salary/i.test(label)) return "30k-50k / 月";
  if (/地点|城市|location/i.test(label)) return "上海 / 远程";
  if (/邮箱|email/i.test(label)) return "you@example.com";
  if (/电话|phone|手机/i.test(label)) return "+86 138 0000 0000";
  return "在这里填写…";
}