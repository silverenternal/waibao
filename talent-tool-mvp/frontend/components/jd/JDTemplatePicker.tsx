"use client";

/**
 * JDTemplatePicker (T604)
 *
 * Picker card listing all available industry JD templates. Renders the
 * summary returned by `GET /api/jd-templates/list` (industry, salary band,
 * counts) plus the per-template `over_spec_warnings` as small chips.
 *
 * Selecting a template calls `onPick(templateId, full)` so the parent page
 * can swap to the detail view (which fetches `/api/jd-templates/{id}`).
 */

import * as React from "react";
import {
  Layers,
  Briefcase,
  Wallet,
  ChevronRight,
  AlertTriangle,
  CheckCircle2,
  Search,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

import { jdApi, type JDTemplateSummary } from "@/lib/api-jd";

export interface JDTemplatePickerProps {
  onPick?: (templateId: string) => void;
  /** Optional pre-selected template id (controlled). */
  selectedId?: string | null;
  className?: string;
}

export function JDTemplatePicker({
  onPick,
  selectedId,
  className,
}: JDTemplatePickerProps) {
  const [items, setItems] = React.useState<JDTemplateSummary[]>([]);
  const [industries, setIndustries] = React.useState<string[]>([]);
  const [industry, setIndustry] = React.useState<string>("");
  const [search, setSearch] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  // Combined loader: list + industries.
  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [resp] = await Promise.all([
        jdApi.templates({ industry: industry || undefined, search: search || undefined }),
      ]);
      setItems(resp.templates);
      setIndustries(resp.industries ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载模板失败");
    } finally {
      setLoading(false);
    }
  }, [industry, search]);

  React.useEffect(() => {
    const id = window.setTimeout(() => load(), 150);
    return () => window.clearTimeout(id);
  }, [load]);

  return (
    <div className={cn("space-y-4", className)}>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Layers className="size-4 text-blue-500" />
            行业模板库
            <Badge variant="outline" className="ml-auto text-[10px]">
              {items.length} 项
            </Badge>
          </CardTitle>
          <CardDescription>
            选择相近的岗位模板作为起点,再针对公司实际场景微调。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索职位 / 行业 / 关键字…"
                className="h-9 pl-9"
              />
            </div>
            <div className="flex flex-wrap gap-1">
              <IndustryPill
                active={!industry}
                label="全部"
                onClick={() => setIndustry("")}
              />
              {industries.map((i) => (
                <IndustryPill
                  key={i}
                  active={industry === i}
                  label={i}
                  onClick={() => setIndustry(industry === i ? "" : i)}
                />
              ))}
              {industry && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIndustry("")}
                  className="h-7 gap-1 px-2 text-xs"
                >
                  <X className="size-3" />
                  清空
                </Button>
              )}
            </div>
          </div>

          {loading ? (
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <li key={i}>
                  <Card>
                    <CardContent className="space-y-2 py-4">
                      <Skeleton className="h-3 w-20" />
                      <Skeleton className="h-5 w-3/4" />
                      <Skeleton className="h-3 w-full" />
                    </CardContent>
                  </Card>
                </li>
              ))}
            </ul>
          ) : error ? (
            <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
              {error}
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-md border border-dashed bg-slate-50 px-3 py-6 text-center text-xs text-slate-500">
              没有匹配的模板。
            </div>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {items.map((t) => (
                <li key={t.id}>
                  <TemplateCard
                    t={t}
                    selected={selectedId === t.id}
                    onClick={() => onPick?.(t.id)}
                  />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function TemplateCard({
  t,
  selected,
  onClick,
}: {
  t: JDTemplateSummary;
  selected: boolean;
  onClick: () => void;
}) {
  const band = t.salary_band;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group flex w-full flex-col rounded-lg border bg-white p-3 text-left shadow-sm transition",
        selected
          ? "border-blue-500 ring-2 ring-blue-100"
          : "border-slate-200 hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="grid size-8 shrink-0 place-items-center rounded-md bg-blue-50 text-blue-600">
          <Briefcase className="size-4" />
        </span>
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-slate-900">{t.title}</h3>
          <p className="truncate text-[10px] text-slate-500">{t.industry}</p>
        </div>
        <ChevronRight className="ml-auto size-4 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-blue-500" />
      </div>
      <p className="mt-2 line-clamp-2 text-[11px] text-slate-600">{t.description}</p>

      <ul className="mt-2 flex flex-wrap gap-1 text-[10px] text-slate-700">
        <Badge variant="outline" className="bg-slate-50 text-slate-600">
          职责 {t.responsibility_count}
        </Badge>
        <Badge variant="outline" className="bg-blue-50 text-blue-700">
          必填 {t.hard_requirement_count}
        </Badge>
        <Badge variant="outline" className="bg-emerald-50 text-emerald-700">
          加分 {t.nice_to_have_count}
        </Badge>
        {band && (
          <Badge variant="outline" className="ml-auto bg-amber-50 text-amber-700">
            <Wallet className="mr-1 size-3" />
            {band.min_k ?? 0}-{band.max_k ?? 0}K
          </Badge>
        )}
      </ul>

      {(t.over_spec_warnings ?? []).length > 0 && (
        <div className="mt-2 rounded-md border border-amber-200 bg-amber-50/60 p-2">
          <div className="flex items-center gap-1 text-[10px] font-medium text-amber-800">
            <AlertTriangle className="size-3" />
            {t.over_spec_warnings.length} 项提醒
          </div>
          <ul className="mt-1 space-y-0.5 text-[10px] text-amber-700">
            {t.over_spec_warnings.slice(0, 2).map((w, i) => (
              <li key={i} className="line-clamp-2">
                · {w}
              </li>
            ))}
            {t.over_spec_warnings.length > 2 && (
              <li className="text-amber-500">…等 {t.over_spec_warnings.length - 2} 项</li>
            )}
          </ul>
        </div>
      )}

      {(t.over_spec_warnings ?? []).length === 0 && (
        <p className="mt-2 inline-flex items-center gap-1 text-[10px] text-emerald-600">
          <CheckCircle2 className="size-3" />
          模板经验证,需求合理
        </p>
      )}
    </button>
  );
}

function IndustryPill({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-2.5 py-0.5 text-[11px] transition",
        active
          ? "border-blue-500 bg-blue-500 text-white"
          : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50",
      )}
    >
      {label}
    </button>
  );
}
