"use client";

/**
 * T1106 — 4 步 onboarding checklist.
 *
 * 从 use-onboarding 读取 steps + completed 状态,渲染 progress + 列表.
 * 完成后展示 confetti CTA (简单 inline SVG,无依赖).
 */

import * as React from "react";
import Link from "next/link";
import { Check, Circle, Sparkles, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  useOnboarding,
  type OnboardingStep,
  type StepDef,
} from "@/hooks/use-onboarding";

export interface OnboardingChecklistProps {
  role: "jobseeker" | "employer";
  /** 允许外部覆盖步骤完成状态 (例如 API 同步后). */
  externalCompleted?: OnboardingStep[];
  /** 关闭按钮回调 (默认调用 dismiss). */
  onDismiss?: () => void;
}

export function OnboardingChecklist({
  role,
  externalCompleted,
  onDismiss,
}: OnboardingChecklistProps) {
  const ob = useOnboarding(role);

  // 合并外部完成项 (用于 API 同步)
  const mergedCompleted = React.useMemo(() => {
    const all = new Set(ob.completed);
    (externalCompleted ?? []).forEach((k) => all.add(k));
    return all;
  }, [ob.completed, externalCompleted]);

  if (ob.dismissed) return null;

  const visibleSteps = ob.steps;
  const completedCount = mergedCompleted.size;
  const progress = visibleSteps.length
    ? completedCount / visibleSteps.length
    : 0;

  return (
    <Card className="border-primary/20 bg-gradient-to-br from-primary/5 to-transparent">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="size-4 text-primary" />
              开始使用 waibao
            </CardTitle>
            <CardDescription>
              完成 4 步,解锁全部功能
              {completedCount > 0 && ` · 已完成 ${completedCount}/${visibleSteps.length}`}
            </CardDescription>
          </div>
          <button
            type="button"
            onClick={() => (onDismiss ? onDismiss() : ob.dismiss())}
            className="rounded p-1 text-muted-foreground hover:bg-muted"
            aria-label="隐藏清单"
          >
            <X className="size-4" />
          </button>
        </div>
        <Progress value={progress * 100} className="h-1.5" />
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {visibleSteps.map((s) => (
            <ChecklistItem
              key={s.key}
              step={s}
              done={mergedCompleted.has(s.key)}
              onMark={() => ob.markStep(s.key)}
            />
          ))}
        </ul>
        {progress >= 1 && (
          <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-center text-sm text-emerald-700">
            🎉 全部完成,您已是 waibao 高手!
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ChecklistItem({
  step,
  done,
  onMark,
}: {
  step: StepDef;
  done: boolean;
  onMark: () => void;
}) {
  return (
    <li className="flex items-start gap-3 rounded-md p-2 transition-colors hover:bg-muted/50">
      <button
        type="button"
        onClick={onMark}
        className={cn(
          "mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border-2 transition-colors",
          done
            ? "border-primary bg-primary text-primary-foreground"
            : "border-muted-foreground/40 text-transparent hover:border-primary",
        )}
        aria-label={done ? "已完成" : "标记完成"}
      >
        {done ? <Check className="size-3" /> : <Circle className="size-2" />}
      </button>
      <div className="flex-1">
        <p
          className={cn(
            "text-sm font-medium",
            done && "text-muted-foreground line-through",
          )}
        >
          {step.title}
        </p>
        <p className="text-xs text-muted-foreground">{step.description}</p>
        {step.href && !done && (
          <Link
            href={step.href}
            className="mt-1 inline-block text-xs text-primary hover:underline"
          >
            去完成 →
          </Link>
        )}
      </div>
    </li>
  );
}

export default OnboardingChecklist;