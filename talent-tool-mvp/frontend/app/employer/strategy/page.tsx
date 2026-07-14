"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * HR Strategy Map page — /strategy (T205).
 *
 * Layout (top → bottom):
 *   1. Sticky header  · 返回 / 标题 / 刷新 / 视角切换 (map | timeline | diff)
 *   2. Composer       · 输入愿景/规划/战略/战术 → POST /api/vision/submit
 *   3. GapAlert       · 缺失层级红色警告 (banner variant)
 *   4. Body           · 按视角渲染:
 *        - "map"      → <StrategyMap/> 四层堆叠卡
 *        - "timeline" → <StrategyTimeline/> 时间线
 *        - "diff"     → <StrategyDiffView/> 旧 vs 新(基于 timeline 选中两个快照)
 *
 * Data flow:
 *   - On mount: GET /api/vision/strategy-map?organisation_id=<me>
 *   - On submit: POST /api/vision/submit → refetch map (so 4-lane view stays in sync)
 *   - Refresh button refetches.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  History,
  Layers,
  Loader2,
  RefreshCcw,
  Send,
  Sparkles,
  Telescope,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

import { StrategyMap } from "@/components/strategy/StrategyMap";
import { StrategyDiffView } from "@/components/strategy/StrategyDiff";
import { StrategyTimeline } from "@/components/strategy/StrategyTimeline";
import { GapAlert } from "@/components/strategy/GapAlert";

import {
  strategyApi,
  type StrategyItem,
  type StrategyMapResponse,
  type VisionArtifacts,
  LEVEL_ORDER,
  LEVEL_LABEL,
  levelHasContent,
  followUpQuestions,
  flattenStrategyMap,
} from "@/lib/api-strategy";

// ---------------------------------------------------------------------------
// View modes — drives the body region beneath the composer.
// ---------------------------------------------------------------------------

type ViewMode = "map" | "timeline" | "diff";

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function StrategyPage() {
  const router = useRouter();

  // ---------- State ----------
  const [organisationId, setOrganisationId] = React.useState<string | null>(null);
  const [map, setMap] = React.useState<StrategyMapResponse["strategy_map"] | null>(
    null,
  );
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const [view, setView] = React.useState<ViewMode>("map");

  // Composer
  const [composerText, setComposerText] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [agentText, setAgentText] = React.useState<string | null>(null);
  const [artifacts, setArtifacts] = React.useState<VisionArtifacts | null>(null);

  // Selection state — used by map / timeline to cross-highlight.
  const [highlightedId, setHighlightedId] = React.useState<string | null>(null);

  // Diff mode: pick two snapshots to compare against.
  const [diffOlderId, setDiffOlderId] = React.useState<string | null>(null);
  const [diffNewerId, setDiffNewerId] = React.useState<string | null>(null);

  // ---------- Loaders ----------
  const loadMap = React.useCallback(async (manual = false) => {
    if (!organisationId) return;
    if (manual) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const resp = await strategyApi.strategyMap(organisationId);
      setMap(resp.strategy_map ?? null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载战略地图失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [organisationId]);

  // Bootstrap: grab current user to derive org id, then load map.
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await fetch("/api/users/me", { cache: "no-store" }).then((r) =>
          r.ok ? r.json() : null,
        );
        if (cancelled) return;
        const orgId =
          (me && (me.organisation_id || me.id)) || "demo-org";
        setOrganisationId(orgId);
      } catch {
        if (!cancelled) setOrganisationId("demo-org");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    if (organisationId) loadMap();
  }, [organisationId, loadMap]);

  // ---------- Derived ----------
  const flat = React.useMemo(() => flattenStrategyMap(map), [map]);
  const missing = React.useMemo(
    () =>
      LEVEL_ORDER.filter(
        (lvl) => !levelHasContent(map, lvl),
      ),
    [map],
  );

  // For diff view: build the two snapshots.
  const diffSlices = React.useMemo(() => {
    const sorted = [...flat].sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    );
    if (sorted.length === 0) return null;

    const findById = (id: string | null) =>
      id ? sorted.find((s) => s.id === id) ?? null : null;

    const olderAnchor = findById(diffOlderId) ?? sorted[0];
    const newerAnchor = findById(diffNewerId) ?? sorted[sorted.length - 1];

    const sliceBefore = (anchor: StrategyItem) =>
      sorted.filter((s) => new Date(s.created_at) <= new Date(anchor.created_at));
    const sliceAfter = (anchor: StrategyItem) =>
      sorted.filter((s) => new Date(s.created_at) <= new Date(anchor.created_at));

    return {
      before: sliceBefore(olderAnchor),
      after: sliceAfter(newerAnchor),
      options: sorted,
      olderAnchor,
      newerAnchor,
    };
  }, [flat, diffOlderId, diffNewerId]);

  // ---------- Handlers ----------
  async function handleSubmit() {
    const text = composerText.trim();
    if (!text || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const resp = await strategyApi.submit(text);
      setAgentText(resp.text);
      setArtifacts(resp.artifacts ?? null);
      // Refresh so the 4-lane view shows the new rows.
      await loadMap(false);
      setComposerText("");
      setView("map");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  function scrollToComposer() {
    if (typeof document === "undefined") return;
    document
      .getElementById("strategy-composer")
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function handleTimelineSelect(item: StrategyItem) {
    setHighlightedId(item.id);
  }

  // ---------- Render ----------
  return (
    <ErrorBoundary>(<div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
        {/* ============ Header ============ */}
        <header className="sticky top-0 z-20 border-b bg-white/80 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => router.push("/employer")}
                aria-label="返回"
              >
                <ArrowLeft className="size-4" />
              </Button>
              <div>
                <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
                  <Telescope className="size-5 text-indigo-500" />
                  战略地图
                </h1>
                <p className="text-xs text-muted-foreground">
                  愿景 → 规划 → 战略 → 战术 — 四层堆叠 + 时间线 + 版本对比
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadMap(true)}
                disabled={refreshing || loading}
                className="gap-2"
              >
                {refreshing ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <RefreshCcw className="size-4" />
                )}
                刷新
              </Button>
            </div>
          </div>
        </header>
        {/* ============ Body ============ */}
        <main className="mx-auto max-w-7xl px-6 py-6">
          <div className="grid gap-6 lg:grid-cols-3">
            {/* ----- Left column: composer + view tabs ----- */}
            <div className="lg:col-span-2 flex flex-col gap-4">
              {/* Gap warning */}
              <GapAlert
                missing={missing}
                onCtaClick={scrollToComposer}
                className={cn(missing.length === 0 && "hidden")}
              />

              {/* Composer */}
              <Card id="strategy-composer" className="border-indigo-100">
                <CardContent className="space-y-3 p-5">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-indigo-600">
                      <Sparkles className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <h2 className="text-sm font-semibold text-slate-900">
                        告诉智能体你的战略
                      </h2>
                      <p className="mt-0.5 text-xs text-slate-500">
                        用自然语言描述愿景、规划、战略、战术 — Agent 会自动解构并入库。
                        {missing.length > 0 && (
                          <span className="ml-1 text-rose-600">
                            当前缺失:{missing.map((l) => LEVEL_LABEL[l]).join(" / ")}
                          </span>
                        )}
                      </p>
                    </div>
                  </div>

                  <Textarea
                    value={composerText}
                    onChange={(e) => setComposerText(e.target.value)}
                    placeholder={
                      "例如:\n" +
                      "愿景:3 年内成为 AI 原生 HR 平台,服务 1000 家中型企业。\n" +
                      "规划:明年聚焦金融 + 制造行业,做到行业前三。\n" +
                      "战略:聚焦 AI 招聘官 + 雇主品牌两条线。\n" +
                      "战术:Q3 上线 AI 简历评估;Q4 启动雇主品牌投放。"
                    }
                    className="min-h-[140px] text-sm"
                  />

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      onClick={handleSubmit}
                      disabled={submitting || composerText.trim().length === 0}
                      className="gap-2"
                    >
                      {submitting ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <Send className="size-4" />
                      )}
                      {submitting ? "分析中..." : "提交分析"}
                    </Button>
                    {agentText && (
                      <span className="text-xs text-slate-500 line-clamp-1">
                        最近回复:{agentText.split("\n")[0]}
                      </span>
                    )}
                  </div>

                  {artifacts && followUpQuestions(artifacts).length > 0 && (
                    <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs">
                      <div className="mb-1 font-semibold text-amber-900">
                        智能体追问
                      </div>
                      <ul className="space-y-0.5 text-amber-800">
                        {followUpQuestions(artifacts).map((q, i) => (
                          <li key={i}>· {q}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* View tabs */}
              <Tabs
                value={view}
                onValueChange={(v) => setView(v as ViewMode)}
                className="w-full"
              >
                <TabsList variant="line">
                  <TabsTrigger value="map" className="gap-1.5">
                    <Layers className="size-3.5" /> 战略地图
                  </TabsTrigger>
                  <TabsTrigger value="timeline" className="gap-1.5">
                    <History className="size-3.5" /> 时间线
                  </TabsTrigger>
                  <TabsTrigger value="diff" className="gap-1.5">
                    对比
                  </TabsTrigger>
                </TabsList>

                {/* Map view */}
                <TabsContent value="map" className="mt-4">
                  {loading && <LoadingState />}
                  {error && !loading && (
                    <ErrorState message={error} onRetry={() => loadMap(true)} />
                  )}
                  {!loading && !error && (
                    <StrategyMap
                      items={map}
                      onItemClick={handleTimelineSelect}
                      highlightedId={highlightedId}
                    />
                  )}
                </TabsContent>

                {/* Timeline view */}
                <TabsContent value="timeline" className="mt-4">
                  {loading && <LoadingState />}
                  {error && !loading && (
                    <ErrorState message={error} onRetry={() => loadMap(true)} />
                  )}
                  {!loading && !error && (
                    <Card>
                      <CardContent className="p-5">
                        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
                          <History className="size-4 text-slate-500" />
                          战略历史 ({flat.length})
                        </h3>
                        <StrategyTimeline
                          items={flat}
                          selectedId={highlightedId}
                          onSelect={handleTimelineSelect}
                          maxItems={50}
                        />
                      </CardContent>
                    </Card>
                  )}
                </TabsContent>

                {/* Diff view */}
                <TabsContent value="diff" className="mt-4">
                  {loading && <LoadingState />}
                  {error && !loading && (
                    <ErrorState message={error} onRetry={() => loadMap(true)} />
                  )}
                  {!loading && !error && (
                    <Card>
                      <CardContent className="space-y-4 p-5">
                        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                          版本对比
                        </h3>
                        {flat.length < 2 ? (
                          <p className="rounded-md border border-dashed border-slate-200 bg-slate-50/60 p-4 text-center text-xs text-slate-500">
                            至少需要 2 条战略记录才能对比 — 在上方再提交一次文本。
                          </p>
                        ) : diffSlices ? (
                          <>
                            <DiffAnchors
                              items={diffSlices.options}
                              olderId={diffSlices.olderAnchor.id}
                              newerId={diffSlices.newerAnchor.id}
                              onChange={(older, newer) => {
                                setDiffOlderId(older);
                                setDiffNewerId(newer);
                              }}
                            />
                            <StrategyDiffView
                              before={diffSlices.before}
                              after={diffSlices.after}
                              beforeLabel={`截止 ${new Date(
                                diffSlices.olderAnchor.created_at,
                              ).toLocaleDateString("en-GB")} (${diffSlices.olderAnchor.title.slice(0, 12)})`}
                              afterLabel={`截止 ${new Date(
                                diffSlices.newerAnchor.created_at,
                              ).toLocaleDateString("en-GB")} (${diffSlices.newerAnchor.title.slice(0, 12)})`}
                            />
                          </>
                        ) : null}
                      </CardContent>
                    </Card>
                  )}
                </TabsContent>
              </Tabs>
            </div>

            {/* ----- Right column: legend + recent ----- */}
            <aside className="space-y-4">
              <Card>
                <CardContent className="space-y-3 p-5">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                    <Layers className="size-4 text-slate-500" /> 四层结构
                  </h3>
                  <ol className="space-y-2 text-xs text-slate-600">
                    {LEVEL_ORDER.map((lvl) => (
                      <li
                        key={lvl}
                        className={cn(
                          "flex items-center justify-between gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5",
                        )}
                      >
                        <span className="font-medium text-slate-800">
                          {LEVEL_LABEL[lvl]}
                        </span>
                        <span className="text-[10px] text-slate-500">
                          {(map?.[lvl] ?? []).length} 项
                        </span>
                      </li>
                    ))}
                  </ol>
                  <p className="text-[10px] text-slate-400">
                    顶层最大,逐层缩进 — 视觉化&ldquo;愿景→执行&rdquo;传导。
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="space-y-3 p-5">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                    <History className="size-4 text-slate-500" /> 最近更新
                  </h3>
                  <StrategyTimeline
                    items={flat.slice(0, 8)}
                    selectedId={highlightedId}
                    onSelect={handleTimelineSelect}
                  />
                </CardContent>
              </Card>
            </aside>
          </div>
        </main>
      </div>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// Anchor selector for the diff view — pick two snapshots from the sorted
// history.
// ---------------------------------------------------------------------------

function DiffAnchors({
  items,
  olderId,
  newerId,
  onChange,
}: {
  items: StrategyItem[];
  olderId: string;
  newerId: string;
  onChange: (olderId: string, newerId: string) => void;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <AnchorSelect
        label="旧版本(基线)"
        items={items}
        value={olderId}
        onChange={(v) => onChange(v, newerId)}
      />
      <AnchorSelect
        label="新版本(对比)"
        items={items}
        value={newerId}
        onChange={(v) => onChange(olderId, v)}
      />
    </div>
  );
}

function AnchorSelect({
  label,
  items,
  value,
  onChange,
}: {
  label: string;
  items: StrategyItem[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="font-medium text-slate-600">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs focus:border-blue-400 focus:outline-none"
      >
        {items.map((it) => (
          <option key={it.id} value={it.id}>
            {new Date(it.created_at).toLocaleString("en-GB", {
              day: "2-digit",
              month: "short",
              hour: "2-digit",
              minute: "2-digit",
            })}{" "}
            · {LEVEL_LABEL[it.level]} · {it.title.slice(0, 20)}
          </option>
        ))}
      </select>
    </label>
  );
}

// ---------------------------------------------------------------------------
// States
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500">
        <Loader2 className="size-4 animate-spin text-indigo-500" />
        加载战略地图中...
      </CardContent>
    </Card>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Card className="border-rose-200 bg-rose-50">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-sm text-rose-700">
        <AlertCircle className="size-5" />
        <span>{message}</span>
        <Button variant="outline" size="sm" onClick={onRetry}>
          重试
        </Button>
      </CardContent>
    </Card>
  );
}