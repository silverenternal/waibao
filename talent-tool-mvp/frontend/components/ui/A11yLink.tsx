"use client";
/**
 * Re-export anchor/link helpers with sensible a11y defaults.
 * Components here are pass-through that ensure aria-* props propagate.
 */
import * as React from "react";

export interface A11yLinkProps
  extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
  /** Visible label is required for screen readers; provide if children is icon-only. */
  ariaLabel?: string;
  /** Marks link as external (adds rel & target). */
  external?: boolean;
}

export const A11yLink = React.forwardRef<HTMLAnchorElement, A11yLinkProps>(
  function A11yLink(
    { ariaLabel, external, children, rel, target, ...rest },
    ref
  ) {
    const computedRel =
      rel ?? (external ? "noopener noreferrer" : undefined);
    const computedTarget = target ?? (external ? "_blank" : undefined);
    return (
      <a
        ref={ref}
        aria-label={ariaLabel}
        rel={computedRel}
        target={computedTarget}
        {...rest}
      >
        {children}
      </a>
    );
  }
);

export default A11yLink;
