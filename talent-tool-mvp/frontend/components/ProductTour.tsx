"use client";

/**
 * T1403 (extends T1106) — Product Tour with full keyboard navigation.
 *
 * Features:
 *   - Spotlight on current step's target element using getBoundingClientRect
 *   - Floating tooltip with auto-placement (top/bottom/left/right)
 *   - Keyboard navigation: Esc to close, ←/→ to navigate steps, Home/End
 *   - Accessible: role="dialog", aria-modal="true", aria-labelledby, focus trap
 *   - Mobile-friendly: stacks tooltip below target on small screens
 *   - SSR-safe (window guards)
 */

import * as React from "react";
import { ArrowLeft, ArrowRight, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useEscapeToClose, useFocusTrap } from "@/hooks/use-keyboard-nav";

export interface TourStep {
  /** CSS selector for the target element. */
  targetSelector?: string;
  /** React ref to the target element (preferred over selector). */
  ref?: React.RefObject<HTMLElement>;
  /** Title shown in the tooltip header. */
  title: string;
  /** Body copy explaining the highlighted UI. */
  content: string;
  /** Preferred tooltip placement relative to target. */
  placement?: "top" | "bottom" | "left" | "right";
  /** Optional CTA href for "go" button instead of next. */
  href?: string;
}

export interface ProductTourProps {
  steps: TourStep[];
  open: boolean;
  /** Called when the user dismisses or finishes. */
  onClose: () => void;
  /** Called only when the last step is confirmed. */
  onComplete?: () => void;
  /** Optional class for the tooltip root. */
  className?: string;
}

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

function getBox(target: Element | null | undefined): Box | null {
  if (!target) return null;
  const rect = target.getBoundingClientRect();
  return {
    top: rect.top,
    left: rect.left,
    width: rect.width,
    height: rect.height,
  };
}

const TOOLTIP_W = 320;
const TOOLTIP_H = 180;
const PAD = 8;
const EDGE = 16;

export function ProductTour({
  steps,
  open,
  onClose,
  onComplete,
  className,
}: ProductTourProps) {
  const [idx, setIdx] = React.useState(0);
  const [box, setBox] = React.useState<Box | null>(null);

  const step = steps[idx];
  const isLast = idx === steps.length - 1;

  const updateBox = React.useCallback(() => {
    if (!step) return;
    let el: Element | null = null;
    if (step.ref?.current) el = step.ref.current;
    else if (step.targetSelector) el = document.querySelector(step.targetSelector);
    setBox(getBox(el));
  }, [step]);

  React.useEffect(() => {
    if (!open) return;
    updateBox();
    window.addEventListener("resize", updateBox);
    window.addEventListener("scroll", updateBox, true);
    return () => {
      window.removeEventListener("resize", updateBox);
      window.removeEventListener("scroll", updateBox, true);
    };
  }, [open, updateBox]);

  // Reset to first step whenever tour opens
  React.useEffect(() => {
    if (open) setIdx(0);
  }, [open]);

  const close = React.useCallback(() => {
    onClose();
    setIdx(0);
  }, [onClose]);

  useEscapeToClose(close, { enabled: open });

  const focusTrapRef = useFocusTrap<HTMLDivElement>({
    active: open,
    restoreFocus: undefined,
  });

  const handleKey = React.useCallback(
    (e: KeyboardEvent) => {
      if (!open) return;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        setIdx((i) => Math.min(steps.length - 1, i + 1));
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        setIdx((i) => Math.max(0, i - 1));
      } else if (e.key === "Home") {
        e.preventDefault();
        setIdx(0);
      } else if (e.key === "End") {
        e.preventDefault();
        setIdx(steps.length - 1);
      } else if (e.key === "Enter") {
        // Allow Enter on the next/finish button to advance
        if (document.activeElement?.getAttribute("data-tour-action") === "next") {
          e.preventDefault();
          if (isLast) {
            onComplete?.();
            close();
          } else {
            setIdx((i) => i + 1);
          }
        }
      }
    },
    [open, steps.length, isLast, onComplete, close]
  );

  React.useEffect(() => {
    if (!open) return;
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, handleKey]);

  if (!open || !step) return null;

  const highlight = box
    ? {
        top: box.top - PAD,
        left: box.left - PAD,
        width: box.width + PAD * 2,
        height: box.height + PAD * 2,
      }
    : null;

  const tooltipStyle = (() => {
    if (!highlight) {
      return { top: "50%", left: "50%", transform: "translate(-50%, -50%)" };
    }
    const vpW = window.innerWidth;
    const vpH = window.innerHeight;
    const isMobile = vpW < 640;
    const placement = step.placement ?? "bottom";

    let top = highlight.top + highlight.height + 12;
    let left = highlight.left;

    if (placement === "top") {
      top = highlight.top - TOOLTIP_H - 12;
    } else if (placement === "left") {
      top = highlight.top;
      left = highlight.left - TOOLTIP_W - 12;
    } else if (placement === "right") {
      top = highlight.top;
      left = highlight.left + highlight.width + 12;
    }

    if (isMobile) {
      // On mobile, dock tooltip at bottom of viewport.
      top = vpH - TOOLTIP_H - EDGE;
      left = EDGE;
    } else {
      if (top + TOOLTIP_H > vpH) top = vpH - TOOLTIP_H - EDGE;
      if (top < EDGE) top = EDGE;
      if (left + TOOLTIP_W > vpW) left = vpW - TOOLTIP_W - EDGE;
      if (left < EDGE) left = EDGE;
    }

    return {
      top: `${top}px`,
      left: `${left}px`,
      width: `${TOOLTIP_W}px`,
    };
  })();

  const finish = () => {
    if (isLast) {
      onComplete?.();
      close();
    } else {
      setIdx((i) => i + 1);
    }
  };

  const stepId = `tour-step-${idx}`;
  const titleId = `${stepId}-title`;
  const descId = `${stepId}-desc`;

  return (
    <div
      ref={focusTrapRef}
      className="fixed inset-0 z-[60] outline-none"
      data-testid="product-tour"
    >
      {/* Backdrop (click outside to close) */}
      <button
        type="button"
        aria-label="Close product tour"
        tabIndex={-1}
        onClick={close}
        className="absolute inset-0 cursor-default bg-black/60"
        style={{ border: 0 }}
      />

      {/* Highlight spotlight via box-shadow trick */}
      {highlight && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute rounded-lg"
          style={{
            top: highlight.top,
            left: highlight.left,
            width: highlight.width,
            height: highlight.height,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.6)",
            border: "2px solid #fff",
            transition: "all 200ms ease-out",
          }}
        />
      )}

      {/* Tooltip dialog */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className={cn(
          "absolute z-[61] rounded-xl border bg-background p-4 shadow-xl",
          "max-w-[calc(100vw-2rem)]",
          className
        )}
        style={tooltipStyle as React.CSSProperties}
      >
        <div className="flex items-start justify-between gap-2">
          <h3
            id={titleId}
            className="text-sm font-semibold"
            data-testid="tour-title"
          >
            {step.title}
          </h3>
          <button
            type="button"
            onClick={close}
            className="rounded p-1 text-muted-foreground hover:bg-muted"
            aria-label="关闭引导"
          >
            <X className="size-4" />
          </button>
        </div>
        <p
          id={descId}
          className="mt-2 text-sm text-muted-foreground"
          data-testid="tour-content"
        >
          {step.content}
        </p>
        <div className="mt-4 flex items-center justify-between">
          <p
            className="text-xs text-muted-foreground tabular-nums"
            aria-live="polite"
            aria-atomic="true"
          >
            第 {idx + 1} 步 / 共 {steps.length} 步
          </p>
          <div className="flex gap-2">
            {idx > 0 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setIdx((i) => Math.max(0, i - 1))}
                aria-label="上一步"
              >
                <ArrowLeft className="mr-1 size-3.5" />
                上一步
              </Button>
            )}
            <Button
              size="sm"
              onClick={finish}
              data-tour-action="next"
              aria-label={isLast ? "完成引导" : "下一步"}
              className={cn(isLast && "min-w-20")}
            >
              {isLast ? "完成" : "下一步"}
              {!isLast && <ArrowRight className="ml-1 size-3.5" />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ProductTour;
