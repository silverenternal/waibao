"use client";

/**
 * GlobalSearchBar — persistent trigger that opens GlobalSearchPalette via ⌘K.
 *
 * Mounted once in root layout. Renders an unobtrusive bar at the top of the
 * page (mobile-friendly), with a keyboard hint that doubles as the trigger.
 */
import * as React from "react";
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { GlobalSearchPalette } from "@/components/GlobalSearchPalette";
import { useShortcut } from "@/hooks/use-keyboard-nav";

export interface GlobalSearchBarProps {
  /** Mac, Win, Linux all support ⌘K or Ctrl+K via combo. */
  shortcut?: string;
  /** Render as a button-only trigger (hide the persistent bar). */
  triggerOnly?: boolean;
}

export function GlobalSearchBar({
  shortcut = "mod+k",
  triggerOnly = false,
}: GlobalSearchBarProps) {
  const [open, setOpen] = React.useState(false);
  const trigger = React.useCallback(() => setOpen(true), []);

  useShortcut(trigger, {
    combo: shortcut,
    description: "Open global search",
    preventDefault: true,
  });

  const [shortcutLabel, setShortcutLabel] = React.useState("Ctrl K");
  React.useEffect(() => {
    const isMac =
      typeof navigator !== "undefined" &&
      /Mac|iPhone|iPad|iPod/.test(navigator.platform);
    setShortcutLabel(isMac ? "⌘ K" : "Ctrl K");
  }, []);

  return (
    <>
      {!triggerOnly && (
        <div className="flex items-center justify-end border-b bg-background/80 px-4 py-1.5 backdrop-blur-sm">
          <Button
            variant="outline"
            size="sm"
            onClick={trigger}
            data-testid="open-global-search"
            aria-label={`Open global search (${shortcutLabel})`}
            className="gap-2 text-muted-foreground"
          >
            <Search className="size-3.5" />
            <span className="hidden sm:inline">搜索...</span>
            <kbd className="hidden rounded border bg-muted px-1.5 text-[10px] font-medium text-muted-foreground md:inline">
              {shortcutLabel}
            </kbd>
          </Button>
        </div>
      )}
      <GlobalSearchPalette open={open} onClose={() => setOpen(false)} />
    </>
  );
}

export default GlobalSearchBar;
