"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * T2304 — 智能通知偏好 (求职者).
 *
 * 功能:
 * - 细粒度配置 (category × priority × channel)
 * - 频率 (realtime / hourly / daily / weekly)
 * - 静默时间 (拖动时间轴)
 * - LLM 智能建议 + 一键应用
 */

import * as React from "react";
import { Bell, Loader2, RefreshCw, Save } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

import { CategorySwitch, type PriorityKey, type ChannelKey } from "@/components/notifications/CategorySwitch";
import { QuietHoursPicker } from "@/components/notifications/QuietHoursPicker";
import { SmartSuggestion, type SmartSuggestionItem } from "@/components/notifications/SmartSuggestion";

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------

type FrequencyKey = "realtime" | "hourly" | "daily" | "weekly";

interface Pref {
  id?: string | null;
  category: string;
  priority: PriorityKey;
  channel: ChannelKey;
  frequency: FrequencyKey;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  enabled: boolean;
}

interface Metadata {
  categories: string[];
  priorities: string[];
  channels: string[];
  frequencies: string[];
  category_labels: Record<string, string>;
  channel_labels: Record<string, string>;
  frequency_labels: Record<string, string>;
  priority_labels: Record<string, string>;
}

const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  matching: "候选人匹配成功 / 新增候选",
  ticket: "HR 工单创建 / 状态更新",
  emotion: "情绪高风险告警",
  system: "系统告警 / 容量预警",
  recruiting: "招聘流程推进 / Offer 状态",
};

const FREQUENCY_OPTIONS: FrequencyKey[] = [
  "realtime",
  "hourly",
  "daily",
  "weekly",
];

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

const API_PREFIX = "/api/notifications";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return (await res.json()) as T;
}

function buildDefaultMatrix(
  categories: string[],
  priorities: PriorityKey[],
  channels: ChannelKey[],
): Record<string, Record<PriorityKey, Record<ChannelKey, boolean>>> {
  const out: Record<string, Record<PriorityKey, Record<ChannelKey, boolean>>> = {};
  for (const cat of categories) {
    out[cat] = {} as Record<PriorityKey, Record<ChannelKey, boolean>>;
    for (const p of priorities) {
      out[cat][p] = {} as Record<ChannelKey, boolean>;
      for (const c of channels) {
        out[cat][p][c] = true; // 默认开启
      }
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function NotificationsPage() {
  const [meta, setMeta] = React.useState<Metadata | null>(null);
  const [prefs, setPrefs] = React.useState<Pref[]>([]);
  const [matrix, setMatrix] = React.useState<
    Record<string, Record<PriorityKey, Record<ChannelKey, boolean>>>
  >({});
  const [quietHours, setQuietHours] = React.useState<{
    start: string | null;
    end: string | null;
  }>({ start: null, end: null });
  const [frequency, setFrequency] = React.useState<FrequencyKey>("realtime");
  const [suggestions, setSuggestions] = React.useState<SmartSuggestionItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [regenerating, setRegenerating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [savedAt, setSavedAt] = React.useState<Date | null>(null);

  // ---- 初始加载 ----
  const loadAll = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [metaRes, prefsRes, suggRes] = await Promise.all([
        fetchJson<Metadata>(`${API_PREFIX}/categories`),
        fetchJson<{ prefs: Pref[] }>(`${API_PREFIX}/prefs`),
        fetchJson<{ suggestions: SmartSuggestionItem[] }>(
          `${API_PREFIX}/suggestions`,
        ).catch(() => ({ suggestions: [] })),
      ]);
      setMeta(metaRes);
      setPrefs(prefsRes.prefs ?? []);
      setSuggestions(suggRes.suggestions ?? []);

      // 重建 matrix
      const priorities = metaRes.priorities as PriorityKey[];
      const channels = metaRes.channels as ChannelKey[];
      const m = buildDefaultMatrix(metaRes.categories, priorities, channels);
      let firstQuiet: { start: string | null; end: string | null } | null = null;
      let firstFreq: FrequencyKey | null = null;
      for (const p of prefsRes.prefs ?? []) {
        const cat = p.category;
        const pri = p.priority as PriorityKey;
        const ch = p.channel as ChannelKey;
        if (m[cat] && m[cat][pri]) {
          m[cat][pri][ch] = p.enabled;
        }
        if (firstQuiet == null && (p.quiet_hours_start || p.quiet_hours_end)) {
          firstQuiet = {
            start: p.quiet_hours_start ?? null,
            end: p.quiet_hours_end ?? null,
          };
        }
        if (firstFreq == null) {
          firstFreq = p.frequency as FrequencyKey;
        }
      }
      setMatrix(m);
      if (firstQuiet) setQuietHours(firstQuiet);
      if (firstFreq) setFrequency(firstFreq);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadAll();
  }, [loadAll]);

  // ---- toggle ----
  const onToggle = React.useCallback(
    (cat: string, pri: PriorityKey, ch: ChannelKey, enabled: boolean) => {
      setMatrix((prev) => ({
        ...prev,
        [cat]: {
          ...(prev[cat] || ({} as Record<PriorityKey, Record<ChannelKey, boolean>>)),
          [pri]: {
            ...((prev[cat]?.[pri] as Record<ChannelKey, boolean>) ||
              ({} as Record<ChannelKey, boolean>)),
            [ch]: enabled,
          },
        },
      }));
    },
    [],
  );

  // ---- bulk save ----
  const onSave = React.useCallback(async () => {
    if (!meta) return;
    setSaving(true);
    setError(null);
    try {
      const payload: Pref[] = [];
      for (const cat of meta.categories) {
        for (const pri of meta.priorities as PriorityKey[]) {
          for (const ch of meta.channels as ChannelKey[]) {
            const enabled = matrix[cat]?.[pri]?.[ch] ?? true;
            payload.push({
              category: cat,
              priority: pri,
              channel: ch,
              frequency,
              quiet_hours_start: quietHours.start,
              quiet_hours_end: quietHours.end,
              enabled,
            });
          }
        }
      }
      const res = await fetchJson<{ prefs: Pref[] }>(`${API_PREFIX}/prefs/bulk`, {
        method: "POST",
        body: JSON.stringify({ prefs: payload }),
      });
      setPrefs(res.prefs ?? []);
      setSavedAt(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [meta, matrix, frequency, quietHours]);

  // ---- 建议操作 ----
  const regenerate = React.useCallback(async () => {
    setRegenerating(true);
    setError(null);
    try {
      const res = await fetchJson<{
        created: number;
        suggestions: SmartSuggestionItem[];
      }>(`${API_PREFIX}/suggestions/generate`, { method: "POST" });
      setSuggestions(res.suggestions ?? []);
      // 重新拉 prefs (建议可能写入了)
      const prefsRes = await fetchJson<{ prefs: Pref[] }>(`${API_PREFIX}/prefs`);
      setPrefs(prefsRes.prefs ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRegenerating(false);
    }
  }, []);

  const applySuggestion = React.useCallback(
    async (id: string) => {
      await fetchJson(`${API_PREFIX}/suggestions/${id}/apply`, { method: "POST" });
      setSuggestions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, status: "applied" } : s)),
      );
      // 重新拉 prefs (apply 后改了)
      const prefsRes = await fetchJson<{ prefs: Pref[] }>(`${API_PREFIX}/prefs`);
      setPrefs(prefsRes.prefs ?? []);
    },
    [],
  );

  const dismissSuggestion = React.useCallback(async (id: string) => {
    await fetchJson(`${API_PREFIX}/suggestions/${id}/dismiss`, { method: "POST" });
    setSuggestions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, status: "dismissed" } : s)),
    );
  }, []);

  // ---- render ----
  if (loading && !meta) {
    return (
      <div className="container mx-auto max-w-5xl px-4 py-8">
        <Skeleton className="mb-4 h-10 w-1/3" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!meta) {
    return (
      <div className="container mx-auto max-w-5xl px-4 py-8">
        <Card>
          <CardHeader>
            <CardTitle>加载失败</CardTitle>
            <CardDescription>{error ?? "无法获取通知偏好元数据"}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  const priorities = meta.priorities as PriorityKey[];
  const channels = meta.channels as ChannelKey[];

  return (
    <ErrorBoundary>(<div className="container mx-auto max-w-5xl space-y-6 px-4 py-8">
        {/* Header */}
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold">
              <Bell className="h-6 w-6 text-indigo-500" aria-hidden="true" />
              通知偏好
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              细粒度控制每种类别 / 优先级 / 通道的通知接收; 支持智能降噪 + 静默时间.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {savedAt && (
              <Badge variant="secondary" className="text-xs">
                已保存 · {savedAt.toLocaleTimeString()}
              </Badge>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={onSave}
              disabled={saving}
              data-testid="save-prefs"
            >
              {saving ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : (
                <Save className="mr-1 h-3 w-3" aria-hidden="true" />
              )}
              保存
            </Button>
          </div>
        </header>
        {error && (
          <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </div>
        )}
        {/* 智能建议 */}
        <Card data-testid="smart-suggestions-card">
          <CardHeader className="flex flex-row items-start justify-between">
            <div>
              <CardTitle className="text-base">智能优化建议</CardTitle>
              <CardDescription>
                基于你最近 7 天的通知使用行为, AI 推荐更合适的配置.
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={regenerate}
              disabled={regenerating}
              data-testid="regenerate-suggestions"
            >
              {regenerating ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : (
                <RefreshCw className="mr-1 h-3 w-3" aria-hidden="true" />
              )}
              重新生成
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {suggestions.length === 0 && (
              <p className="text-sm text-slate-500">
                暂无建议 — 点击「重新生成」让 AI 基于你的使用数据给出优化建议.
              </p>
            )}
            {suggestions.map((s) => (
              <SmartSuggestion
                key={s.id}
                item={s}
                onApply={
                  s.status === "pending" ? applySuggestion : undefined
                }
                onDismiss={
                  s.status === "pending" ? dismissSuggestion : undefined
                }
              />
            ))}
          </CardContent>
        </Card>
        {/* 静默时间 + 频率 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">静默时间 + 频率</CardTitle>
            <CardDescription>
              静默时间内不发送; 非实时频率会聚合成摘要定期发送.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <QuietHoursPicker
              start={quietHours.start}
              end={quietHours.end}
              onChange={(s, e) => setQuietHours({ start: s, end: e })}
            />
            <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
              <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
                默认发送频率
              </h3>
              <p className="mb-3 text-xs text-slate-500">
                非实时频率会在累积到下一个周期后批量摘要发送.
              </p>
              <div className="grid grid-cols-2 gap-2">
                {FREQUENCY_OPTIONS.map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => setFrequency(f)}
                    className={cn(
                      "rounded-md border px-3 py-2 text-sm transition-colors",
                      frequency === f
                        ? "border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-200"
                        : "border-slate-200 hover:border-slate-300 dark:border-slate-700",
                    )}
                    data-frequency={f}
                  >
                    {meta.frequency_labels[f] ?? f}
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
        {/* 类别矩阵 */}
        <div className="space-y-4">
          {meta.categories.map((cat) => (
            <CategorySwitch
              key={cat}
              category={cat}
              label={meta.category_labels[cat] ?? cat}
              description={CATEGORY_DESCRIPTIONS[cat]}
              priorities={priorities}
              channels={channels}
              matrix={
                (matrix[cat] as Record<PriorityKey, Record<ChannelKey, boolean>>) ||
                buildDefaultMatrix([cat], priorities, channels)[cat]
              }
              onToggle={(pri, ch, enabled) => onToggle(cat, pri, ch, enabled)}
              badge={
                meta.categories.indexOf(cat) === 0 ? `${prefs.length} 条已配置` : undefined
              }
            />
          ))}
        </div>
      </div>)</ErrorBoundary>
  );
}