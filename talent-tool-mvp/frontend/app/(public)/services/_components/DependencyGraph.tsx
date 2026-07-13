"use client";

/**
 * v8.0 T3502 — Service dependency DAG.
 *
 * Lightweight, dependency-free SVG renderer for the public service
 * dependency graph. We intentionally do NOT use react-flow (not in the
 * frontend bundle) so the page can stay static and ship fast.
 *
 * Layout strategy: BFS from the root service, placing each layer on a row.
 * Edges are rendered as straight lines between the centres of nodes.
 */

import * as React from "react";

export interface DepNode {
  id: string;
  label?: string;
  category?: string;
  plan_required?: string;
  status?: string;
  external?: boolean;
}

interface DepEdge {
  from: string;
  to: string;
  kind?: string;
}

interface DependencyGraphProps {
  nodes: DepNode[];
  edges: DepEdge[];
  root: string;
}

const NODE_W = 180;
const NODE_H = 56;
const X_GAP = 60;
const Y_GAP = 32;

const STATUS_FILL: Record<string, string> = {
  enabled: "#22c55e",
  beta: "#3b82f6",
  maintenance: "#eab308",
  deprecated: "#f59e0b",
  disabled: "#ef4444",
};

interface Positioned {
  id: string;
  label: string;
  status: string;
  plan: string;
  x: number;
  y: number;
  layer: number;
  external: boolean;
}

export function DependencyGraph({ nodes, edges, root }: DependencyGraphProps): React.ReactElement {
  const layout = React.useMemo(() => layoutNodes(nodes, edges, root), [nodes, edges, root]);
  if (layout.positions.length === 0) {
    return <p className="p-4 text-center text-sm text-slate-500">没有节点</p>;
  }

  const minX = Math.min(...layout.positions.map((p) => p.x));
  const minY = Math.min(...layout.positions.map((p) => p.y));
  const maxX = Math.max(...layout.positions.map((p) => p.x + NODE_W));
  const maxY = Math.max(...layout.positions.map((p) => p.y + NODE_H));
  const width = Math.max(maxX - minX + 60, 320);
  const height = Math.max(maxY - minY + 60, 200);

  const byId = new Map(layout.positions.map((p) => [p.id, p] as const));

  return (
    <svg
      role="img"
      aria-label="Service dependency graph"
      viewBox={`${minX - 30} ${minY - 30} ${width} ${height}`}
      width={width}
      height={height}
      className="block"
    >
      <defs>
        <marker
          id="dep-arrow"
          viewBox="0 0 10 10"
          refX="10"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
        </marker>
      </defs>

      {/* edges */}
      {edges.map((e, i) => {
        const from = byId.get(e.from);
        const to = byId.get(e.to);
        if (!from || !to) return null;
        const x1 = from.x + NODE_W / 2;
        const y1 = from.y + NODE_H;
        const x2 = to.x + NODE_W / 2;
        const y2 = to.y;
        return (
          <line
            key={`e-${i}`}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke="#94a3b8"
            strokeWidth={1.5}
            markerEnd="url(#dep-arrow)"
          />
        );
      })}

      {/* nodes */}
      {layout.positions.map((p) => {
        const fill = STATUS_FILL[p.status] ?? "#94a3b8";
        const isRoot = p.id === root;
        return (
          <g key={p.id} transform={`translate(${p.x}, ${p.y})`}>
            <rect
              width={NODE_W}
              height={NODE_H}
              rx={10}
              ry={10}
              fill="white"
              stroke={isRoot ? "#1d4ed8" : "#cbd5e1"}
              strokeWidth={isRoot ? 2 : 1}
            />
            <circle cx={14} cy={NODE_H / 2} r={6} fill={fill} />
            <text
              x={28}
              y={NODE_H / 2 - 4}
              fontSize={12}
              fontWeight={600}
              fill="#0f172a"
            >
              {truncate(p.label, 22)}
            </text>
            <text
              x={28}
              y={NODE_H / 2 + 12}
              fontSize={10}
              fill="#64748b"
            >
              {p.plan || "free"} {p.external ? "· external" : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}

interface LayoutResult {
  positions: Positioned[];
}

function layoutNodes(nodes: DepNode[], edges: DepEdge[], root: string): LayoutResult {
  const byId = new Map(nodes.map((n) => [n.id, n] as const));
  if (!byId.has(root) && nodes.length > 0) {
    // root not in the graph; pick the first node
    root = nodes[0].id;
  }
  const adj: Record<string, string[]> = {};
  for (const n of nodes) adj[n.id] = [];
  for (const e of edges) {
    if (adj[e.from]) adj[e.from].push(e.to);
  }

  // BFS layers from root
  const layers: Record<string, number> = {};
  const queue: string[] = [root];
  layers[root] = 0;
  while (queue.length) {
    const cur = queue.shift()!;
    const nextLayer = (layers[cur] ?? 0) + 1;
    for (const n of adj[cur] ?? []) {
      if (!(n in layers)) {
        layers[n] = nextLayer;
        queue.push(n);
      }
    }
  }

  // Group by layer
  const byLayer: Record<number, string[]> = {};
  for (const id of Object.keys(layers)) {
    const l = layers[id];
    byLayer[l] = byLayer[l] ?? [];
    byLayer[l].push(id);
  }

  const positions: Positioned[] = [];
  const sortedLayers = Object.keys(byLayer)
    .map((k) => Number(k))
    .sort((a, b) => a - b);
  for (const l of sortedLayers) {
    const ids = byLayer[l];
    ids.forEach((id, idx) => {
      const node = byId.get(id);
      const label = node?.label ?? id;
      positions.push({
        id,
        label,
        status: node?.status ?? "enabled",
        plan: node?.plan_required ?? "",
        external: Boolean(node?.external),
        x: idx * (NODE_W + X_GAP),
        y: l * (NODE_H + Y_GAP),
        layer: l,
      });
    });
  }
  return { positions };
}