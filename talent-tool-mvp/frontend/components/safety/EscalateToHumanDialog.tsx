"use client";

/**
 * v11.0 T6110 — Mandatory human-escalation dialog.
 *
 * Rendered when the governance layer detects a topic that MUST be handed to a
 * human (self-harm risk or a labour dispute).  The AI never eliminates a
 * candidate here — it only surfaces a recommendation and a warm hand-off.
 *
 * Two variants:
 *   • self_harm      → warm copy + national psychological-aid hotline +
 *                       "转人工" button (pages HR immediately on submit).
 *   • labour_dispute → advisory copy + "转 HR / 法务" button (opens a ticket).
 *
 * Privacy: the dialog never displays nor transmits the user's verbatim
 * conversation beyond the one-time escalation call; admins only ever see the
 * risk_level + reason on their dashboard.
 */
import * as React from "react";
import { Heart, ShieldCheck, Loader2, Phone } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  escalateToHuman,
  SELF_HARM_HOTLINE,
  type EscalationRule,
} from "@/lib/api-safety";

export interface EscalateToHumanDialogProps {
  /** Controlled open state. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Which rule triggered the dialog. */
  rule: EscalationRule;
  /** Redacted reason from governance (already PII-free). */
  reason?: string;
  /** Organisation id (forwarded to the escalation ticket). */
  organisationId?: string;
  /** Called after a successful hand-off. */
  onEscalated?: (result: { ticketId?: string; message: string }) => void;
}

export function EscalateToHumanDialog({
  open: openProp,
  onOpenChange,
  rule,
  reason,
  organisationId,
  onEscalated,
}: EscalateToHumanDialogProps) {
  const [open, setOpen] = React.useState(openProp ?? false);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState(false);

  React.useEffect(() => {
    if (openProp !== undefined) setOpen(openProp);
  }, [openProp]);

  React.useEffect(() => {
    if (!open) {
      setDone(false);
      setError(null);
    }
  }, [open]);

  const isSelfHarm = rule === "self_harm";

  async function handleEscalate() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await escalateToHuman({
        // The category reason only — never the verbatim chat.
        text: reason || (isSelfHarm ? "自伤风险提醒" : "劳动争议提醒"),
        department: isSelfHarm ? "general" : "legal",
        priority: isSelfHarm ? "urgent" : "high",
        organisation_id: organisationId,
        context: { rule, source: "safety_dialog", raw_text_stored: false },
      });
      setDone(true);
      onEscalated?.({ ticketId: res.ticket_id, message: res.message });
    } catch (e) {
      setError(e instanceof Error ? e.message : "转人工失败,请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  function close() {
    setOpen(false);
    onOpenChange?.(false);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        onOpenChange?.(v);
      }}
    >
      <DialogContent
        className={cn(
          "max-w-md",
          isSelfHarm
            ? "border-rose-200 dark:border-rose-900"
            : "border-amber-200 dark:border-amber-900"
        )}
      >
        <DialogHeader>
          <div
            className={cn(
              "mb-2 inline-flex h-10 w-10 items-center justify-center rounded-full",
              isSelfHarm
                ? "bg-rose-100 text-rose-600 dark:bg-rose-950 dark:text-rose-300"
                : "bg-amber-100 text-amber-600 dark:bg-amber-950 dark:text-amber-300"
            )}
          >
            {isSelfHarm ? (
              <Heart className="h-5 w-5" />
            ) : (
              <ShieldCheck className="h-5 w-5" />
            )}
          </div>
          <DialogTitle>
            {isSelfHarm ? "你不是一个人,我在这里" : "这个问题建议联系 HR 或法务"}
          </DialogTitle>
        </DialogHeader>

        <DescriptionBody isSelfHarm={isSelfHarm} reason={reason} />

        {done ? (
          <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200">
            已为你转接人工。HR 会尽快以保密方式联系你。
          </div>
        ) : null}

        {error ? (
          <div className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={close} disabled={submitting}>
            稍后再说
          </Button>
          <Button
            onClick={handleEscalate}
            disabled={submitting || done}
            className={isSelfHarm ? "bg-rose-600 text-white hover:bg-rose-700" : ""}
          >
            {submitting ? (
              <>
                <Loader2 className="mr-1 h-4 w-4 animate-spin" /> 正在转接…
              </>
            ) : isSelfHarm ? (
              "立即转人工"
            ) : (
              "转 HR / 法务"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Warm, accessible description body (no verbatim user text). */
function DescriptionBody({
  isSelfHarm,
  reason,
}: {
  isSelfHarm: boolean;
  reason?: string;
}) {
  return (
    <div className="space-y-3 pt-1 text-sm leading-relaxed text-muted-foreground">
      {isSelfHarm ? (
        <>
          <p>
            我注意到你可能正在经历困难。请记得,你的感受很重要,
            有专业的人可以陪你一起面对。
          </p>
          <p className="rounded-lg bg-rose-50 p-3 text-rose-800 dark:bg-rose-950/50 dark:text-rose-200">
            <Phone className="mr-1 inline h-3.5 w-3.5" />
            全国24小时心理援助热线:
            <strong className="mx-1 text-base tracking-wide">
              {SELF_HARM_HOTLINE}
            </strong>
          </p>
          <p>我可以帮你立即转接给 HR,他们会以保密方式跟进。</p>
        </>
      ) : (
        <>
          <p>
            这个问题涉及劳动争议,我作为助手只能提供建议,
            不能替代 HR 或法务的专业判断。
          </p>
          <p>我可以帮你创建一个工单转交给 HR 或法务部门处理。</p>
        </>
      )}
      {reason ? <p className="text-xs">提醒原因: {reason}</p> : null}
    </div>
  );
}
