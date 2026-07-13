// Cube.js BI proxy client (T2802)
//
// All functions hit the backend /api/bi/* endpoints which proxy
// the Cube.js server with a 5-minute Redis cache.

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function authedFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
  // Auth header is enforced server-side; for client fetch we rely on cookies
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`BI API ${path} ${res.status}: ${await res.text()}`);
  }
  return (await res.json()) as T;
}

// -------------------------------------------------------------------
// Types — mirror backend/api/bi.py
// -------------------------------------------------------------------
export interface CubeDimension {
  name: string;
  title: string;
  type: string;
}

export interface CubeMeasure {
  name: string;
  title: string;
  type: string;
}

export interface CubeMeta {
  name: string;
  title: string;
  dimensions: CubeDimension[];
  measures: CubeMeasure[];
}

export interface BiMeta {
  cubes: CubeMeta[];
}

export interface CubeQuery {
  measures?: string[];
  dimensions?: string[];
  filters?: Array<Record<string, unknown>>;
  timeDimensions?: Array<Record<string, unknown>>;
  order?: Array<unknown[]>;
  limit?: number;
  offset?: number;
}

export interface CubeQueryResult {
  data: Array<Record<string, unknown>>;
  cached?: boolean;
  stale?: boolean;
  annotation?: Record<string, unknown>;
}

export interface BiWidget {
  id: string;
  type: string;
  title: string;
  query: CubeQuery;
  data?: CubeQueryResult | { data: unknown[] };
  error?: string;
}

export interface BiDashboardConfig {
  key: string;
  title: string;
  description: string;
  widgets: BiWidget[];
  built_in?: boolean;
}

export interface SavedDashboard {
  id: string;
  name: string;
  description: string;
  widgets: BiWidget[];
  shared: boolean;
  owner_id: string;
  created_at: number;
  updated_at: number;
}

export interface BiHealth {
  ok: boolean;
  cubejs_url: string;
  cubejs_reachable: boolean;
  redis: boolean;
  cache_ttl_seconds: number;
  built_in_dashboards: string[];
}

// -------------------------------------------------------------------
// Endpoints
// -------------------------------------------------------------------
export const biApi = {
  meta: () => authedFetch<{ data: BiMeta; cached: boolean }>("/api/bi/meta"),
  query: (q: CubeQuery) =>
    authedFetch<CubeQueryResult>("/api/bi/query", {
      method: "POST",
      body: JSON.stringify(q),
    }),
  builtinDashboards: () =>
    authedFetch<{ dashboards: BiDashboardConfig[] }>("/api/bi/dashboards/built-in"),
  dashboardData: (key: string) =>
    authedFetch<BiDashboardConfig>(`/api/bi/dashboards/${key}/data`),
  listSaved: () =>
    authedFetch<{ dashboards: SavedDashboard[] }>("/api/bi/dashboards"),
  save: (body: {
    name: string;
    widgets: BiWidget[];
    description?: string;
    shared?: boolean;
  }) =>
    authedFetch<SavedDashboard>("/api/bi/dashboards", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  remove: (id: string) =>
    authedFetch<{ ok: boolean; id: string }>(`/api/bi/dashboards/${id}`, {
      method: "DELETE",
    }),
  share: (id: string) =>
    authedFetch<{ share_token: string; url: string }>(
      `/api/bi/dashboards/${id}/share`,
      { method: "POST" }
    ),
  health: () => authedFetch<BiHealth>("/api/bi/health"),
};

// -------------------------------------------------------------------
// Chart-type catalogue used by the drag/drop builder
// -------------------------------------------------------------------
export const CHART_TYPES = [
  { type: "bar", title: "柱状图", icon: "bar-chart" },
  { type: "line", title: "折线图", icon: "line-chart" },
  { type: "pie", title: "饼图", icon: "pie-chart" },
  { type: "doughnut", title: "环形图", icon: "circle" },
  { type: "area", title: "面积图", icon: "area-chart" },
  { type: "scatter", title: "散点图", icon: "scatter-chart" },
  { type: "radar", title: "雷达图", icon: "radar" },
  { type: "funnel", title: "漏斗图", icon: "funnel" },
  { type: "heatmap", title: "热力图", icon: "grid" },
  { type: "treemap", title: "矩形树图", icon: "layout-grid" },
  { type: "sankey", title: "桑基图", icon: "git-branch" },
  { type: "gauge", title: "仪表盘", icon: "gauge" },
  { type: "kpi", title: "KPI 卡", icon: "number" },
  { type: "table", title: "数据表", icon: "table" },
  { type: "stacked_bar", title: "堆叠柱", icon: "columns-3" },
  { type: "stacked_area", title: "堆叠面积", icon: "layers" },
  { type: "waterfall", title: "瀑布图", icon: "trending-down" },
  { type: "box_plot", title: "箱线图", icon: "square" },
  { type: "bubble", title: "气泡图", icon: "circle-dot" },
  { type: "candlestick", title: "K 线", icon: "candlestick" },
  { type: "timeline", title: "时间线", icon: "clock" },
  { type: "map", title: "地图", icon: "map" },
] as const;
