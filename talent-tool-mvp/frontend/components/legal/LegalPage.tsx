"use client";

/**
 * Re-export the client-only LegalClient as `LegalPage` for backwards compat.
 * T1201 — legal pages now route through a server-component page.tsx that
 * exports `metadata`, then renders this client component which does the
 * runtime fetch / markdown render.
 */
export { LegalClient as LegalPage } from "./LegalClient";
export { default } from "./LegalClient";
