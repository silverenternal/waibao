"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  biApi,
  CHART_TYPES,
  type BiDashboardConfig,
  type BiMeta,
  type BiWidget,
  type CubeQuery,
  type CubeQueryResult,
  type SavedDashboard,
} from "@/lib/api-bi";

const DEFAULT_DASHBOARDS = [
  "funnel",
  "recruitment-efficiency",
  "channel-roi",
  "agent-performance",
  "customer-success",
] as const;

// -------------------------------------------------------------------
// Page
// -------------------------------------------------------------------
export default function BiPage() {
  const [meta, setMeta] = useState<BiMeta | null>(null);
  const [active, setActive] = useState<string>(DEFAULT_DASHBOARDS[0]);
  const [dashboard, setDashboard] = useState<BiDashboardConfig | null>(null);
  const [saved, setSaved] = useState<SavedDashboard[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load meta + saved list once
  useEffect(() => {
    biApi
      .meta()
      .then((m) => setMeta(m.data))
      .catch((e) => setError(String(e)));
    biApi
      .listSaved()
      .then((r) => setSaved(r.dashboards))
      .catch(() => undefined);
  }, []);

  const loadDashboard = useCallback(async (key: string) => {
    setLoading(true);
    setError(null);
    try {
      const d = await biApi.dashboardData(key);
      setDashboard(d);
      setActive(key);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard(active);
  }, [loadDashboard, active]);

  // Builder state — current widget being edited
  const [builder, setBuilder] = useState<{
    open: boolean;
    widget: BiWidget | null;
  }>({ open: false, widget: null });

  const openBuilder = useCallback(
    (w?: BiWidget) =>
      setBuilder({
        open: true,
        widget: w ?? {
          id: `w-${Date.now()}`,
          type: "bar",
          title: "新组件",
          query: { measures: [], dimensions: [], limit: 100 },
        },
      }),
    []
  );

  const runBuilderQuery = useCallback(
    async (q: CubeQuery): Promise<CubeQueryResult> => biApi.query(q),
    []
  );

  const saveAsDashboard = useCallback(
    async (name: string, widgets: BiWidget[]) => {
      const rec = await biApi.save({ name, widgets });
      setSaved((s) => [rec, ...s]);
    },
    []
  );

  return (
    <ErrorBoundary>(<div className="flex flex-col gap-6 p-6">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">商业智能 (BI)</h1>
            <p className="text-sm text-muted-foreground">
              Cube.js 驱动的拖拽式报表 + 5 个内置 dashboard
            </p>
          </div>
          <div className="flex items-center gap-2">
            <ShareButton
              onSave={(name) =>
                dashboard && saveAsDashboard(name, dashboard.widgets)
              }
            />
            <button
              className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground"
              onClick={() => openBuilder()}
            >
              + 新建组件
            </button>
          </div>
        </header>
        <DashboardTabs
          active={active}
          onChange={setActive}
          saved={saved}
        />
        {error ? (
          <div className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm">
            {error}
          </div>
        ) : null}
        {loading ? (
          <SkeletonGrid />
        ) : (
          <WidgetGrid
            widgets={dashboard?.widgets ?? []}
            onEdit={openBuilder}
          />
        )}
        {builder.open && builder.widget && meta ? (
          <BuilderDialog
            meta={meta}
            widget={builder.widget}
            onClose={() => setBuilder({ open: false, widget: null })}
            onRun={runBuilderQuery}
          />
        ) : null}
      </div>)</ErrorBoundary>
  );
}

// -------------------------------------------------------------------
// Tabs
// -------------------------------------------------------------------
function DashboardTabs(props: {
  active: string;
  onChange: (k: string) => void;
  saved: SavedDashboard[];
}) {
  const tabs = [
    { key: "funnel", label: "HR 漏斗" },
    { key: "recruitment-efficiency", label: "招聘效率" },
    { key: "channel-roi", label: "渠道 ROI" },
    { key: "agent-performance", label: "Agent 性能" },
    { key: "customer-success", label: "客户成功" },
  ];
  return (
    <div className="flex flex-wrap gap-1 border-b">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => props.onChange(t.key)}
          className={`px-3 py-2 text-sm ${
            props.active === t.key
              ? "border-b-2 border-primary font-medium"
              : "text-muted-foreground"
          }`}
        >
          {t.label}
        </button>
      ))}
      {props.saved.length > 0 ? (
        <div className="ml-4 flex items-center gap-2 border-l pl-4">
          <span className="text-xs text-muted-foreground">已保存:</span>
          {props.saved.slice(0, 5).map((s) => (
            <span
              key={s.id}
              className="rounded bg-muted px-2 py-0.5 text-xs"
              title={s.description}
            >
              {s.name}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// -------------------------------------------------------------------
// Widget grid
// -------------------------------------------------------------------
function WidgetGrid(props: {
  widgets: BiWidget[];
  onEdit: (w: BiWidget) => void;
}) {
  if (props.widgets.length === 0) {
    return (
      <div className="rounded border border-dashed p-8 text-center text-sm text-muted-foreground">
        空 dashboard — 点击右上角 “+ 新建组件” 开始
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {props.widgets.map((w) => (
        <WidgetCard key={w.id} widget={w} onEdit={() => props.onEdit(w)} />
      ))}
    </div>
  );
}

function WidgetCard(props: { widget: BiWidget; onEdit: () => void }) {
  const { widget } = props;
  const data = useMemo(() => {
    const d: any = widget.data;
    if (!d) return [] as any[];
    if (Array.isArray(d.data)) return d.data;
    if (d.data && Array.isArray(d.data.data)) return d.data.data;
    return [];
  }, [widget.data]);
  const measures = widget.query.measures ?? [];
  const firstMeasure = measures[0];
  const value = firstMeasure ? data[0]?.[firstMeasure] : undefined;
  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium">{widget.title}</h3>
        <div className="flex items-center gap-2">
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
            {widget.type}
          </span>
          <button
            className="text-xs text-primary hover:underline"
            onClick={props.onEdit}
          >
            编辑
          </button>
        </div>
      </div>
      {widget.error ? (
        <div className="text-xs text-destructive">{widget.error}</div>
      ) : widget.type === "kpi" ? (
        <div className="text-3xl font-semibold">
          {value !== undefined ? String(value) : "—"}
        </div>
      ) : widget.type === "table" ? (
        <TableView data={data} measures={measures} />
      ) : (
        <ChartView type={widget.type} data={data} query={widget.query} />
      )}
    </div>
  );
}

function TableView(props: {
  data: Array<Record<string, unknown>>;
  measures: string[];
}) {
  const cols = props.data[0]
    ? Object.keys(props.data[0])
    : [...props.measures];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="bg-muted/40">
          <tr>
            {cols.map((c) => (
              <th key={c} className="px-2 py-1 text-left font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {props.data.slice(0, 8).map((row, i) => (
            <tr key={i} className="border-t">
              {cols.map((c) => (
                <td key={c} className="px-2 py-1">
                  {String(row[c] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChartView(props: {
  type: string;
  data: Array<Record<string, unknown>>;
  query: CubeQuery;
}) {
  // Lightweight bar / line / pie / area renderer using SVG.
  // (Cube.js returns pre-aggregated rows; rendering is generic.)
  const width = 320;
  const height = 160;
  const measures = props.query.measures ?? [];
  const dimensions = props.query.dimensions ?? [];
  const xKey = dimensions[0] ?? measures[0];
  const yKey = measures[0];
  if (!xKey || !yKey) {
    return (
      <div className="text-xs text-muted-foreground">未配置 measure/dimension</div>
    );
  }
  if (props.type === "pie" || props.type === "doughnut") {
    return (
      <PieView
        data={props.data}
        xKey={xKey}
        yKey={yKey}
        width={width}
        height={height}
        doughnut={props.type === "doughnut"}
      />
    );
  }
  return (
    <BarView
      data={props.data}
      xKey={xKey}
      yKey={yKey}
      width={width}
      height={height}
      variant={props.type as "bar" | "line" | "area" | "stacked_bar" | "stacked_area"}
    />
  );
}

function BarView(props: {
  data: Array<Record<string, unknown>>;
  xKey: string;
  yKey: string;
  width: number;
  height: number;
  variant: "bar" | "line" | "area" | "stacked_bar" | "stacked_area";
}) {
  const max = Math.max(
    1,
    ...props.data.map((d) => Number(d[props.yKey] ?? 0))
  );
  const bw = props.width / Math.max(1, props.data.length);
  return (
    <svg viewBox={`0 0 ${props.width} ${props.height}`} className="w-full">
      {props.data.map((d, i) => {
        const v = Number(d[props.yKey] ?? 0);
        const h = (v / max) * (props.height - 24);
        const x = i * bw + 2;
        const y = props.height - h - 4;
        if (props.variant === "line" || props.variant === "area") {
          return null;
        }
        return (
          <g key={i}>
            <rect
              x={x}
              y={y}
              width={Math.max(2, bw - 4)}
              height={h}
              fill="hsl(var(--primary))"
              rx={2}
            />
            <text
              x={x + (bw - 4) / 2}
              y={props.height - 2}
              textAnchor="middle"
              fontSize={9}
              fill="hsl(var(--muted-foreground))"
            >
              {String(d[props.xKey] ?? "").slice(0, 6)}
            </text>
          </g>
        );
      })}
      {(props.variant === "line" || props.variant === "area")
        ? (() => {
            const points = props.data.map((d, i) => {
              const v = Number(d[props.yKey] ?? 0);
              return {
                x: i * bw + bw / 2,
                y: props.height - (v / max) * (props.height - 24) - 4,
              };
            });
            const path = points
              .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
              .join(" ");
            return (
              <>
                {props.variant === "area" ? (
                  <path
                    d={`${path} L ${points[points.length - 1].x} ${props.height - 4} L ${points[0].x} ${props.height - 4} Z`}
                    fill="hsl(var(--primary) / 0.2)"
                  />
                ) : null}
                <path d={path} fill="none" stroke="hsl(var(--primary))" strokeWidth={2} />
              </>
            );
          })()
        : null}
    </svg>
  );
}

function PieView(props: {
  data: Array<Record<string, unknown>>;
  xKey: string;
  yKey: string;
  width: number;
  height: number;
  doughnut: boolean;
}) {
  const total = props.data.reduce((s, d) => s + Number(d[props.yKey] ?? 0), 0) || 1;
  const cx = props.width / 2;
  const cy = props.height / 2;
  const r = Math.min(cx, cy) - 8;
  let acc = 0;
  const palette = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4"];
  return (
    <svg viewBox={`0 0 ${props.width} ${props.height}`} className="w-full">
      {props.data.map((d, i) => {
        const v = Number(d[props.yKey] ?? 0);
        const start = (acc / total) * Math.PI * 2;
        acc += v;
        const end = (acc / total) * Math.PI * 2;
        const x1 = cx + r * Math.sin(start);
        const y1 = cy - r * Math.cos(start);
        const x2 = cx + r * Math.sin(end);
        const y2 = cy - r * Math.cos(end);
        const large = end - start > Math.PI ? 1 : 0;
        const dPath = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`;
        return (
          <path key={i} d={dPath} fill={palette[i % palette.length]} />
        );
      })}
      {props.doughnut ? (
        <circle cx={cx} cy={cy} r={r * 0.5} fill="hsl(var(--background))" />
      ) : null}
    </svg>
  );
}

// -------------------------------------------------------------------
// Builder dialog
// -------------------------------------------------------------------
function BuilderDialog(props: {
  meta: BiMeta;
  widget: BiWidget;
  onClose: () => void;
  onRun: (q: CubeQuery) => Promise<CubeQueryResult>;
}) {
  const [cubeName, setCubeName] = useState<string>(
    props.widget.query.measures?.[0]?.split(".")[0] ??
      props.widget.query.dimensions?.[0]?.split(".")[0] ??
      props.meta.cubes[0]?.name ??
      "Candidates"
  );
  const cube = props.meta.cubes.find((c) => c.name === cubeName) ?? props.meta.cubes[0];
  const [type, setType] = useState(props.widget.type);
  const [title, setTitle] = useState(props.widget.title);
  const [measures, setMeasures] = useState<string[]>(
    props.widget.query.measures ?? []
  );
  const [dimensions, setDimensions] = useState<string[]>(
    props.widget.query.dimensions ?? []
  );
  const [preview, setPreview] = useState<CubeQueryResult | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async () => {
    setBusy(true);
    try {
      const r = await props.onRun({
        measures,
        dimensions,
        limit: 200,
      });
      setPreview(r);
    } finally {
      setBusy(false);
    }
  }, [measures, dimensions, props]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="grid w-full max-w-4xl grid-cols-1 gap-4 rounded-lg border bg-card p-4 shadow-xl md:grid-cols-2">
        <div>
          <h2 className="mb-2 text-lg font-semibold">组件构建器</h2>
          <label className="mb-1 block text-xs text-muted-foreground">标题</label>
          <input
            className="mb-3 w-full rounded border bg-background px-2 py-1 text-sm"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <label className="mb-1 block text-xs text-muted-foreground">Cube</label>
          <select
            className="mb-3 w-full rounded border bg-background px-2 py-1 text-sm"
            value={cubeName}
            onChange={(e) => {
              setCubeName(e.target.value);
              setMeasures([]);
              setDimensions([]);
            }}
          >
            {props.meta.cubes.map((c) => (
              <option key={c.name} value={c.name}>
                {c.title} ({c.name})
              </option>
            ))}
          </select>
          <label className="mb-1 block text-xs text-muted-foreground">图表类型</label>
          <select
            className="mb-3 w-full rounded border bg-background px-2 py-1 text-sm"
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            {CHART_TYPES.map((c) => (
              <option key={c.type} value={c.type}>
                {c.title}
              </option>
            ))}
          </select>
          <label className="mb-1 block text-xs text-muted-foreground">Measures</label>
          <select
            multiple
            className="mb-3 h-32 w-full rounded border bg-background p-1 text-xs"
            value={measures}
            onChange={(e) =>
              setMeasures(
                Array.from(e.target.selectedOptions).map((o) => o.value)
              )
            }
          >
            {cube?.measures.map((m) => (
              <option key={m.name} value={m.name}>
                {m.title} — {m.name}
              </option>
            ))}
          </select>
          <label className="mb-1 block text-xs text-muted-foreground">Dimensions</label>
          <select
            multiple
            className="h-32 w-full rounded border bg-background p-1 text-xs"
            value={dimensions}
            onChange={(e) =>
              setDimensions(
                Array.from(e.target.selectedOptions).map((o) => o.value)
              )
            }
          >
            {cube?.dimensions.map((d) => (
              <option key={d.name} value={d.name}>
                {d.title} — {d.name}
              </option>
            ))}
          </select>
          <div className="mt-3 flex justify-end gap-2">
            <button
              className="rounded border px-3 py-1.5 text-sm"
              onClick={props.onClose}
            >
              取消
            </button>
            <button
              className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground"
              onClick={run}
              disabled={busy}
            >
              {busy ? "运行中…" : "预览"}
            </button>
          </div>
        </div>
        <div>
          <h2 className="mb-2 text-lg font-semibold">预览</h2>
          {preview ? (
            <div className="rounded border p-3">
              <ChartView
                type={type}
                data={preview.data ?? []}
                query={{ measures, dimensions }}
              />
              <pre className="mt-3 max-h-48 overflow-auto rounded bg-muted p-2 text-[10px]">
                {JSON.stringify(preview, null, 2)}
              </pre>
            </div>
          ) : (
            <div className="rounded border border-dashed p-8 text-center text-sm text-muted-foreground">
              选择 measure + dimension + 点击预览
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------
// Save / share
// -------------------------------------------------------------------
function ShareButton(props: { onSave: (name: string) => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("我的 dashboard");
  return (
    <>
      <button
        className="rounded border px-3 py-1.5 text-sm"
        onClick={() => setOpen(true)}
      >
        保存为 dashboard
      </button>
      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-lg border bg-card p-4 shadow-xl">
            <h3 className="mb-2 text-sm font-medium">保存 dashboard</h3>
            <input
              className="mb-3 w-full rounded border bg-background px-2 py-1 text-sm"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <div className="flex justify-end gap-2">
              <button
                className="rounded border px-3 py-1.5 text-sm"
                onClick={() => setOpen(false)}
              >
                取消
              </button>
              <button
                className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground"
                onClick={() => {
                  props.onSave(name);
                  setOpen(false);
                }}
              >
                保存
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

// -------------------------------------------------------------------
// Skeleton
// -------------------------------------------------------------------
function SkeletonGrid() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-40 animate-pulse rounded-lg border bg-muted/30" />
      ))}
    </div>
  );
}
