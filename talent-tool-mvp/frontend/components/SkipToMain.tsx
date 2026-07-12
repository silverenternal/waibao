import * as React from "react";

/**
 * SkipToMain — keyboard-only "skip to main content" link.
 * Becomes visible only when focused, allowing keyboard/screen-reader users to
 * bypass navigation. Complies with WCAG 2.1 SC 2.4.1 (Bypass Blocks).
 *
 * Place once near the top of the document body (root layout).
 */
export interface SkipToMainProps {
  /** Target id (without `#`). Defaults to `main-content`. */
  targetId?: string;
  /** Visible label text. */
  label?: string;
}

export function SkipToMain({
  targetId = "main-content",
  label = "Skip to main content",
}: SkipToMainProps) {
  return (
    <a
      href={`#${targetId}`}
      className="skip-to-main"
      data-testid="skip-to-main"
      aria-label={label}
      // Make this the very first tab-stop on the page
      tabIndex={0}
    >
      {label}
    </a>
  );
}

export default SkipToMain;
