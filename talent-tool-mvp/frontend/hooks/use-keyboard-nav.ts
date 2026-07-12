"use client";

import * as React from "react";

/**
 * useKeyboardNav — WAI-ARIA keyboard navigation utilities.
 *
 * Provides:
 *   - useRovingTabIndex: roving tabindex pattern for menu/toolbar/listbox.
 *   - useArrowKeyNavigation: arrow-key navigation between items.
 *   - useEscapeToClose: ESC key handler with optional skip.
 *   - useFocusTrap: trap focus within a container (dialogs).
 *   - useShortcut: register a global keyboard shortcut.
 *
 * All hooks are SSR-safe and clean up listeners on unmount.
 */

export type Direction = "horizontal" | "vertical" | "both";

export interface RovingTabIndexOptions {
  /** Direction of arrow navigation. */
  direction?: Direction;
  /** Wrap around at edges. */
  loop?: boolean;
  /** Selector for items to navigate between. */
  itemSelector?: string;
}

export interface ArrowNavOptions extends RovingTabIndexOptions {
  /** Initial active index. */
  initialIndex?: number;
  /** Callback when index changes. */
  onIndexChange?: (index: number) => void;
}

/** Returns props to spread onto a focusable list. */
export function useRovingTabIndex({
  direction = "vertical",
  loop = true,
  itemSelector = "[data-roving-item]",
}: RovingTabIndexOptions = {}) {
  const [activeIndex, setActiveIndex] = React.useState(0);
  const containerRef = React.useRef<HTMLElement | null>(null);

  const items = React.useCallback(() => {
    const root = containerRef.current;
    if (!root) return [] as HTMLElement[];
    return Array.from(root.querySelectorAll<HTMLElement>(itemSelector));
  }, [itemSelector]);

  const focusIndex = React.useCallback(
    (idx: number) => {
      const all = items();
      if (all.length === 0) return;
      const next = loop
        ? (idx + all.length) % all.length
        : Math.max(0, Math.min(all.length - 1, idx));
      setActiveIndex(next);
      all[next]?.focus();
    },
    [items, loop]
  );

  const onKeyDown = React.useCallback(
    (event: React.KeyboardEvent) => {
      const all = items();
      if (all.length === 0) return;
      const currentIdx = all.findIndex((el) => el === document.activeElement);
      const idx = currentIdx === -1 ? activeIndex : currentIdx;
      switch (event.key) {
        case "ArrowDown":
        case "ArrowRight":
          if (
            direction === "vertical" ||
            direction === "horizontal" ||
            direction === "both"
          ) {
            event.preventDefault();
            focusIndex(idx + 1);
          }
          break;
        case "ArrowUp":
        case "ArrowLeft":
          if (
            direction === "vertical" ||
            direction === "horizontal" ||
            direction === "both"
          ) {
            event.preventDefault();
            focusIndex(idx - 1);
          }
          break;
        case "Home":
          event.preventDefault();
          focusIndex(0);
          break;
        case "End":
          event.preventDefault();
          focusIndex(all.length - 1);
          break;
        default:
          break;
      }
    },
    [activeIndex, direction, focusIndex, items]
  );

  return {
    containerRef,
    activeIndex,
    setActiveIndex,
    onKeyDown,
    getItemProps: (index: number) => ({
      tabIndex: index === activeIndex ? 0 : -1,
      "data-roving-item": true,
    }),
  };
}

/** Hook for Listbox/Menu style arrow key navigation. */
export function useArrowKeyNavigation(
  length: number,
  {
    direction = "vertical",
    loop = true,
    initialIndex = -1,
    onIndexChange,
  }: ArrowNavOptions = {}
) {
  const [activeIndex, setActiveIndex] = React.useState(initialIndex);

  const setIndex = React.useCallback(
    (idx: number) => {
      if (length === 0) return;
      const safe = loop
        ? (idx + length) % length
        : Math.max(-1, Math.min(length - 1, idx));
      setActiveIndex(safe);
      onIndexChange?.(safe);
    },
    [length, loop, onIndexChange]
  );

  const onKeyDown = React.useCallback(
    (event: React.KeyboardEvent) => {
      const nextKeys =
        direction === "horizontal"
          ? ["ArrowRight", "ArrowLeft"]
          : direction === "vertical"
            ? ["ArrowDown", "ArrowUp"]
            : ["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft"];
      if (nextKeys.includes(event.key)) {
        event.preventDefault();
        const offset = event.key === "ArrowDown" || event.key === "ArrowRight" ? 1 : -1;
        setIndex(activeIndex + offset);
      } else if (event.key === "Home") {
        event.preventDefault();
        setIndex(0);
      } else if (event.key === "End") {
        event.preventDefault();
        setIndex(length - 1);
      }
    },
    [activeIndex, direction, length, setIndex]
  );

  return { activeIndex, setIndex, onKeyDown };
}

/** Closes a layer when Escape is pressed. */
export function useEscapeToClose(
  onEscape: () => void,
  options: { enabled?: boolean } = {}
) {
  const { enabled = true } = options;
  React.useEffect(() => {
    if (!enabled) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onEscape();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [enabled, onEscape]);
}

export interface FocusTrapOptions {
  /** Whether the trap is active. */
  active?: boolean;
  /** Element to restore focus to on unmount. */
  restoreFocus?: HTMLElement | null;
}

/** Traps focus within a container while active. */
export function useFocusTrap<T extends HTMLElement>(
  options: FocusTrapOptions = {}
) {
  const { active = true, restoreFocus } = options;
  const ref = React.useRef<T | null>(null);

  React.useEffect(() => {
    if (!active) return;
    const root = ref.current;
    if (!root) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;

    const focusables = () =>
      Array.from(
        root.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      );

    // Focus first focusable element
    const [first] = focusables();
    first?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const firstEl = items[0];
      const lastEl = items[items.length - 1];
      const current = document.activeElement as HTMLElement | null;
      if (event.shiftKey && current === firstEl) {
        event.preventDefault();
        lastEl.focus();
      } else if (!event.shiftKey && current === lastEl) {
        event.preventDefault();
        firstEl.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      const target = restoreFocus ?? previouslyFocused;
      target?.focus?.();
    };
  }, [active, restoreFocus]);

  return ref;
}

export interface ShortcutOptions {
  /** Key combo string, e.g. "Cmd+K", "Ctrl+/", "Escape". */
  combo: string;
  /** Description for help docs. */
  description?: string;
  /** Whether to call preventDefault. Defaults to true. */
  preventDefault?: boolean;
  /** Whether the shortcut is active. */
  enabled?: boolean;
}

function parseCombo(combo: string) {
  const parts = combo.toLowerCase().split("+").map((p) => p.trim());
  return {
    mod: parts.includes("cmd") || parts.includes("ctrl") || parts.includes("meta"),
    shift: parts.includes("shift"),
    alt: parts.includes("alt"),
    key: parts[parts.length - 1],
  };
}

/** Register a global keyboard shortcut. */
export function useShortcut(
  handler: (event: KeyboardEvent) => void,
  options: ShortcutOptions
) {
  const { combo, preventDefault = true, enabled = true } = options;
  React.useEffect(() => {
    if (!enabled) return;
    const parsed = parseCombo(combo);
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== parsed.key) return;
      if (parsed.mod && !(event.metaKey || event.ctrlKey)) return;
      if (parsed.shift && !event.shiftKey) return;
      if (parsed.alt && !event.altKey) return;
      // If modifier required and not held, skip
      if (parsed.mod && !event.metaKey && !event.ctrlKey) return;
      if (!parsed.mod && (event.metaKey || event.ctrlKey)) return;
      if (preventDefault) event.preventDefault();
      handler(event);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [handler, combo, preventDefault, enabled]);
}
