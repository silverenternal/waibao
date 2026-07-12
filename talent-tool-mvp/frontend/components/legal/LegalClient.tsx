"use client";

/**
 * LegalClient — extracted from LegalPage so that page.tsx can stay a server component
 * and export `metadata` for SEO. All interactivity / data fetching stays here.
 */

import * as React from "react";
import { useLocale } from "next-intl";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

const LANG_TO_QUERY: Record<string, string> = {
  "zh-CN": "zh-CN",
  "en-US": "en-US",
  "ja-JP": "ja-JP",
  zh: "zh-CN",
  en: "en-US",
  ja: "ja-JP",
};

interface LegalDocPayload {
  type: string;
  lang: string;
  filename: string;
  content: string;
  version: string;
  effective_at: string;
  size: number;
  fetched_at: string;
}

function renderMarkdown(md: string): React.ReactNode {
  const lines = md.split("\n");
  const out: React.ReactNode[] = [];
  let para: string[] = [];
  let list: string[] = [];

  const flushPara = () => {
    if (para.length) {
      out.push(
        <p key={`p-${out.length}`} className="leading-7 text-sm text-foreground/90">
          {para.join(" ")}
        </p>,
      );
      para = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      out.push(
        <ul
          key={`ul-${out.length}`}
          className="ml-6 list-disc space-y-1 text-sm text-foreground/90"
        >
          {list.map((it, i) => (
            <li key={i}>{it}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };

  for (const line of lines) {
    const t = line.trimEnd();
    if (!t) {
      flushPara();
      flushList();
      continue;
    }
    const h = t.match(/^(#{1,4})\s+(.+)$/);
    if (h) {
      flushPara();
      flushList();
      const level = h[1].length;
      const txt = h[2].trim();
      const cls =
        level === 1
          ? "text-3xl font-bold tracking-tight"
          : level === 2
            ? "mt-6 text-2xl font-semibold"
            : level === 3
              ? "mt-4 text-lg font-semibold"
              : "mt-3 text-base font-semibold";
      out.push(
        <h2 key={`h-${out.length}`} className={cn(cls, "text-foreground")}>
          {txt}
        </h2>,
      );
      continue;
    }
    if (/^\d+\.\s+/.test(t) || /^[-*]\s+/.test(t)) {
      flushPara();
      list.push(t.replace(/^\d+\.\s+|^[-*]\s+/, ""));
      continue;
    }
    flushList();
    para.push(t);
  }
  flushPara();
  flushList();
  return out;
}

export function LegalClient({ docType, title }: { docType: string; title?: string }) {
  const locale = useLocale();
  const lang = LANG_TO_QUERY[locale] ?? "zh-CN";
  const [doc, setDoc] = React.useState<LegalDocPayload | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/legal/${docType}?lang=${lang}`);
        if (!res.ok) {
          if (!cancelled) setError(`HTTP ${res.status}`);
          return;
        }
        const data = (await res.json()) as LegalDocPayload;
        if (!cancelled) {
          setDoc(data);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [docType, lang]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      <header className="mb-6 border-b pb-4">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
          {title ?? docType.toUpperCase()}
        </h1>
        {doc && (
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span>版本 {doc.version}</span>
            <span>·</span>
            <span>生效 {doc.effective_at}</span>
            <span>·</span>
            <span>语言 {doc.lang}</span>
          </div>
        )}
      </header>

      {!doc && !error && (
        <div className="space-y-3">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-10/12" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          加载失败:{error}
        </div>
      )}

      {doc && (
        <article className="space-y-4">{renderMarkdown(doc.content)}</article>
      )}
    </div>
  );
}

export default LegalClient;
