"use client";

/**
 * ConsentSwitch — T2603 per-purpose consent toggle.
 *
 * Talks to ``GET /api/gdpr-v2/purposes`` for the canonical list, then
 * patches individual grants via ``POST /api/gdpr-v2/consent/grant`` /
 * ``/withdraw``. Designed for the privacy preference centre.
 *
 * Uses the Checkbox primitive instead of a Switch (the project's UI
 * library does not ship Switch but does ship Checkbox with the same
 * `checked` + `onCheckedChange` callback shape).
 */

import * as React from "react";
import { Loader2, Lock } from "lucide-react";

import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";

export interface PurposeDefinition {
  code: string;
  label_zh: string;
  label_en: string;
  label_ja?: string;
  description_zh: string;
  description_en: string;
  required: boolean;
  lawful_basis?: Record<string, string>;
}

interface ConsentSwitchProps {
  purpose: PurposeDefinition;
  granted: boolean;
  withdrawnAt?: string | null;
  locale?: "zh" | "en" | "ja";
  pending?: boolean;
  onChange: (next: boolean) => void;
  className?: string;
}

export function ConsentSwitch({
  purpose,
  granted,
  withdrawnAt,
  locale = "en",
  pending,
  onChange,
  className,
}: ConsentSwitchProps) {
  const label =
    locale === "zh"
      ? purpose.label_zh
      : locale === "ja" && purpose.label_ja
        ? purpose.label_ja
        : purpose.label_en;
  const description =
    locale === "zh" ? purpose.description_zh : purpose.description_en;
  const disabled = purpose.required || pending;

  return (
    <div
      data-testid={`consent-switch-${purpose.code}`}
      className={cn(
        "flex items-start justify-between gap-4 rounded-lg border p-4 transition-colors",
        granted ? "border-primary/30 bg-primary/5" : "border-border bg-card",
        disabled && "opacity-90",
        className,
      )}
    >
      <div className="flex flex-1 items-start gap-3">
        <Checkbox
          id={`consent-${purpose.code}`}
          checked={granted}
          disabled={disabled}
          onCheckedChange={(value: boolean) => onChange(Boolean(value))}
          aria-label={label}
          data-testid={`consent-switch-toggle-${purpose.code}`}
          className="mt-1"
        />
        <label
          htmlFor={`consent-${purpose.code}`}
          className="flex-1 cursor-pointer space-y-1"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium leading-none">{label}</span>
            {purpose.required && (
              <Badge variant="secondary" className="text-[10px]">
                <Lock className="mr-1 size-3" />
                {locale === "zh" ? "必需" : "Required"}
              </Badge>
            )}
            {withdrawnAt && (
              <Badge variant="outline" className="text-[10px]">
                {locale === "zh" ? "已撤回" : "Withdrawn"}
              </Badge>
            )}
            {pending && (
              <Loader2 className="size-3 animate-spin text-muted-foreground" />
            )}
          </div>
          <span className="block text-xs leading-relaxed text-muted-foreground">
            {description}
          </span>
          {purpose.lawful_basis && (
            <span className="mt-1 block text-[10px] uppercase tracking-wide text-muted-foreground/70">
              {locale === "zh" ? "法律依据" : "Lawful basis"}:{" "}
              {Object.entries(purpose.lawful_basis)
                .map(([region, basis]) => `${region}=${basis}`)
                .join(" · ")}
            </span>
          )}
        </label>
      </div>
    </div>
  );
}

export default ConsentSwitch;
