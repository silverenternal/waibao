"use client";

/**
 * Markdown — shared renderer for LLM / agent generated text.
 *
 * Why this exists (v11.6 R1): agents (career-plan, journal advisor, HR
 * assistant, recommendation / match explainer, JD marketer, …) emit rich
 * markdown — headings, **bold**, lists, tables. Many surfaces were rendering
 * the raw string inside a `<p>`, so users saw literal `#` / `*` / `|`.
 *
 * This component is the single, safe way to render any agent/LLM text blob:
 *   - `react-markdown` + `remark-gfm` (headings / emphasis / lists / tables).
 *   - No raw-HTML injection (no `__html` prop, no `rehype-raw`) → inline HTML is NOT
 *     executed, which closes the XSS path for untrusted LLM output.
 *   - Explicit Tailwind element styles via the `components` map, because
 *     `@tailwindcss/typography` (the `prose` plugin) is NOT installed in this
 *     project, so `prose` classes are a no-op. All styling is self-contained
 *     and theme-aware (uses tokens like `text-foreground`, `border`).
 *
 * Sizing variants:
 *   - `sm`  — dense lists (match reasons, journal advice) — default.
 *   - `base` — longer prose blocks (JD description, plan detail).
 *
 * Usage:
 *   import { Markdown } from "@/components/shared";
 *   <Markdown>{llmText}</Markdown>
 *   <Markdown size="base">{jd.description}</Markdown>
 */
import type { ComponentPropsWithoutRef } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

export interface MarkdownProps {
  /** The markdown source (LLM / agent generated). Empty string renders nothing. */
  children: string | null | undefined;
  /** Density of the rendered output. */
  size?: "sm" | "base";
  /** Extra classes on the wrapping `<div>`. */
  className?: string;
}

/**
 * Element-level styles. Kept minimal + responsive + accessible.
 * Lists reset their default margin so the host layout controls spacing.
 */
function buildComponents(size: "sm" | "base"): Components {
  // Colors inherit from the host container (e.g. text-primary-foreground on a
  // filled chat bubble) so the component works in any background context.
  const h = "font-semibold tracking-tight";
  const lead = size === "sm" ? "text-sm" : "text-base";
  const small = size === "sm" ? "text-xs" : "text-sm";

  return {
    h1: ({ children, ...props }) => (
      <h1 className={cn(h, "mt-4 mb-2 text-lg", lead)} {...props}>
        {children}
      </h1>
    ),
    h2: ({ children, ...props }) => (
      <h2 className={cn(h, "mt-4 mb-2 text-base", lead)} {...props}>
        {children}
      </h2>
    ),
    h3: ({ children, ...props }) => (
      <h3 className={cn(h, "mt-3 mb-1.5 text-sm", lead)} {...props}>
        {children}
      </h3>
    ),
    h4: ({ children, ...props }) => (
      <h4 className={cn(h, "mt-3 mb-1 text-sm", small)} {...props}>
        {children}
      </h4>
    ),
    h5: ({ children, ...props }) => (
      <h5 className={cn(h, "mt-2 mb-1", small)} {...props}>
        {children}
      </h5>
    ),
    h6: ({ children, ...props }) => (
      <h6 className={cn(h, "mt-2 mb-1", small)} {...props}>
        {children}
      </h6>
    ),
    p: ({ children, ...props }) => (
      <p className={cn("my-1.5 leading-relaxed", lead)} {...props}>
        {children}
      </p>
    ),
    a: ({ children, ...props }) => (
      <a
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline underline-offset-2"
        {...props}
      >
        {children}
      </a>
    ),
    ul: ({ children, ...props }) => (
      <ul className={cn("my-1.5 list-disc space-y-0.5 pl-5", lead)} {...props}>
        {children}
      </ul>
    ),
    ol: ({ children, ...props }) => (
      <ol
        className={cn("my-1.5 list-decimal space-y-0.5 pl-5", lead)}
        {...props}
      >
        {children}
      </ol>
    ),
    li: ({ children, ...props }: ComponentPropsWithoutRef<"li">) => (
      <li className="leading-relaxed marker:text-muted-foreground" {...props}>
        {children}
      </li>
    ),
    blockquote: ({ children, ...props }) => (
      <blockquote
        className={cn(
          "my-2 border-l-2 border-border pl-3 italic text-muted-foreground",
          lead,
        )}
        {...props}
      >
        {children}
      </blockquote>
    ),
    hr: (props) => <hr className="my-3 border-border" {...props} />,
    strong: ({ children, ...props }) => (
      <strong className="font-semibold" {...props}>
        {children}
      </strong>
    ),
    em: ({ children, ...props }) => (
      <em className="italic" {...props}>
        {children}
      </em>
    ),
    // Inline code — no syntax highlighter (keeps the chunk light); styled chip.
    code: ({ className, children, ...props }) => (
      <code
        className={cn(
          "rounded bg-muted px-1 py-0.5 font-mono",
          small,
          className,
        )}
        {...props}
      >
        {children}
      </code>
    ),
    // Fenced code blocks — scrollable on mobile, no raw HTML execution.
    pre: ({ children, ...props }) => (
      <pre
        className={cn(
          "my-2 overflow-x-auto rounded-md border bg-muted/50 p-3 font-mono",
          small,
        )}
        {...props}
      >
        {children}
      </pre>
    ),
    // GFM tables — horizontally scrollable so wide tables don't break mobile.
    table: ({ children, ...props }) => (
      <div className="my-2 overflow-x-auto">
        <table
          className="w-full border-collapse text-left border-border"
          {...props}
        >
          {children}
        </table>
      </div>
    ),
    thead: ({ children, ...props }) => (
      <thead className="bg-muted/60" {...props}>
        {children}
      </thead>
    ),
    th: ({ children, ...props }) => (
      <th
        className={cn("border border-border px-2 py-1 font-semibold", small)}
        {...props}
      >
        {children}
      </th>
    ),
    td: ({ children, ...props }) => (
      <td className={cn("border border-border px-2 py-1 align-top", small)} {...props}>
        {children}
      </td>
    ),
  };
}

/**
 * Render an agent/LLM markdown string. Renders nothing for empty/null input
 * so callers can drop it in unconditionally without leaving blank blocks.
 */
export function Markdown({
  children,
  size = "sm",
  className,
}: MarkdownProps) {
  const source = children?.trim();
  if (!source) return null;
  return (
    <div className={cn("markdown-body break-words text-foreground", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={buildComponents(size)}>
        {source}
      </ReactMarkdown>
    </div>
  );
}

export default Markdown;
