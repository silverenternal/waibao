"use client";

/**
 * v6.0 T2105 — Drag-drop canvas.
 *
 * The canvas owns the layout of nodes + edges and exposes callbacks when
 * the user interacts. We render edges as SVG paths and nodes as HTML
 * cards, so the editor is dependency-free (no react-flow needed).
 *
 * Coordinate system: top-left of the canvas is (0,0). Nodes are placed
 * via drop targets computed from the mouse position.
 */

import * as React from "react";

import type { NodeType, WorkflowEdge, WorkflowNode } from "./types";

export interface CanvasNode extends WorkflowNode {
  position: { x: number; y: number };
}

export interface CanvasEdge extends WorkflowEdge {}

interface WorkflowCanvasProps {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  selectedNodeId: string | null;
  onSelect: (nodeId: string | null) => void;
  onAddNode: (node: Omit<CanvasNode, "position">,
              position: { x: number; y: number }) => void;
  onMoveNode: (nodeId: string, position: { x: number; y: number }) => void;
  onConnect: (fromNode: string, toNode: string,
               condition?: string) => void;
  onDeleteNode: (nodeId: string) => void;
  /** Nodes currently executing (for live monitoring). */
  activeNodeIds?: Set<string>;
}

const NODE_WIDTH = 200;
const NODE_HEIGHT = 80;

function nodeColor(type: NodeType | "trigger-event"): string {
  switch (type) {
    case "trigger":
    case "trigger-event":
      return "border-amber-300 bg-amber-50";
    case "agent":
      return "border-indigo-300 bg-indigo-50";
    case "condition":
      return "border-purple-300 bg-purple-50";
    case "action":
      return "border-emerald-300 bg-emerald-50";
    case "delay":
      return "border-sky-300 bg-sky-50";
    case "human":
      return "border-rose-300 bg-rose-50";
    default:
      return "border-slate-300 bg-slate-50";
  }
}

function describe(config: Record<string, unknown>, type: string): string {
  if (type === "trigger" || type === "trigger-event") {
    return `event: ${String(config.event ?? "—")}`;
  }
  if (type === "agent") {
    return `agent: ${String(config.agent ?? "—")}`;
  }
  if (type === "condition") {
    return `if ${String(config.expression ?? "true")}`;
  }
  if (type === "action") {
    return `${String(config.kind ?? "—")}`;
  }
  if (type === "delay") {
    return `${String(config.seconds ?? 0)}s`;
  }
  if (type === "human") {
    return String(config.reason ?? "approval");
  }
  return "";
}

export function WorkflowCanvas(props: WorkflowCanvasProps): React.JSX.Element {
  const canvasRef = React.useRef<HTMLDivElement>(null);
  const [dragOver, setDragOver] = React.useState(false);
  const [pendingFrom, setPendingFrom] =
    React.useState<string | null>(null);

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setDragOver(true);
  };
  const handleDragLeave = () => setDragOver(false);

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    const raw = e.dataTransfer.getData("application/x-workflow-node");
    if (!raw) return;
    let item: { type: NodeType | "trigger-event";
                defaults: Record<string, unknown>;
                label: string };
    try {
      item = JSON.parse(raw);
    } catch {
      return;
    }
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left - NODE_WIDTH / 2;
    const y = e.clientY - rect.top - NODE_HEIGHT / 2;
    const id = `${item.label}_${Date.now().toString(36)}`;
    const nodeType: NodeType = item.type === "trigger-event"
      ? "trigger" : item.type as NodeType;
    props.onAddNode(
      {
        id,
        type: nodeType,
        config: item.defaults,
        next_nodes: [],
      },
      { x: Math.max(0, x), y: Math.max(0, y) },
    );
  };

  const startConnect = (id: string) => setPendingFrom(id);
  const finishConnect = (toId: string) => {
    if (pendingFrom && pendingFrom !== toId) {
      props.onConnect(pendingFrom, toId);
    }
    setPendingFrom(null);
  };

  return (
    <div
      ref={canvasRef}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={(e) => {
        if (e.target === e.currentTarget) props.onSelect(null);
      }}
      data-testid="workflow-canvas"
      className={
        "relative h-full min-h-[600px] w-full overflow-auto bg-slate-100 " +
        (dragOver ? "ring-2 ring-indigo-300" : "")
      }
    >
      <svg
        className="pointer-events-none absolute inset-0 h-full w-full"
        style={{ zIndex: 0 }}
      >
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M0,0 L10,5 L0,10 z" fill="#475569" />
          </marker>
        </defs>
        {props.edges.map((edge, idx) => {
          const from = props.nodes.find((n) => n.id === edge.from_node);
          const to = props.nodes.find((n) => n.id === edge.to_node);
          if (!from || !to) return null;
          const x1 = from.position.x + NODE_WIDTH;
          const y1 = from.position.y + NODE_HEIGHT / 2;
          const x2 = to.position.x;
          const y2 = to.position.y + NODE_HEIGHT / 2;
          const mx = (x1 + x2) / 2;
          const d = `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
          return (
            <g key={idx}>
              <path
                d={d}
                stroke="#475569"
                strokeWidth={1.5}
                fill="none"
                markerEnd="url(#arrow)"
              />
              {edge.condition ? (
                <text
                  x={mx}
                  y={(y1 + y2) / 2 - 6}
                  textAnchor="middle"
                  className="fill-slate-700 text-[10px] font-semibold"
                >
                  {edge.condition}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>

      {props.nodes.map((node) => {
        const isActive = props.activeNodeIds?.has(node.id) ?? false;
        const isSelected = props.selectedNodeId === node.id;
        return (
          <div
            key={node.id}
            onClick={(e) => {
              e.stopPropagation();
              props.onSelect(node.id);
            }}
            data-testid={`node-${node.id}`}
            className={
              "absolute cursor-pointer select-none rounded-md border-2 p-2 text-xs shadow-sm transition " +
              nodeColor(node.type) +
              (isSelected ? " ring-2 ring-indigo-500" : "") +
              (isActive ? " animate-pulse" : "")
            }
            style={{
              left: node.position.x,
              top: node.position.y,
              width: NODE_WIDTH,
              minHeight: NODE_HEIGHT,
              zIndex: 1,
            }}
            draggable
            onDragEnd={(e) => {
              const rect = canvasRef.current?.getBoundingClientRect();
              if (!rect) return;
              const x = e.clientX - rect.left - NODE_WIDTH / 2;
              const y = e.clientY - rect.top - NODE_HEIGHT / 2;
              props.onMoveNode(node.id, { x: Math.max(0, x),
                                          y: Math.max(0, y) });
            }}
          >
            <div className="flex items-center justify-between font-semibold text-slate-700">
              <span>{node.id}</span>
              <span className="rounded bg-white px-1 py-0.5 text-[10px] uppercase text-slate-500">
                {node.type}
              </span>
            </div>
            <div className="mt-1 text-slate-600">
              {describe(node.config, node.type)}
            </div>
            <div className="mt-2 flex gap-1">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  startConnect(node.id);
                }}
                data-testid={`connect-${node.id}`}
                className="rounded bg-slate-700 px-1.5 py-0.5 text-[10px] font-bold text-white hover:bg-slate-900"
                title="Click then click target node to connect"
              >
                → connect
              </button>
              {pendingFrom ? (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    finishConnect(node.id);
                  }}
                  className="rounded bg-emerald-600 px-1.5 py-0.5 text-[10px] font-bold text-white"
                >
                  ⇢ here
                </button>
              ) : null}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  props.onDeleteNode(node.id);
                }}
                data-testid={`delete-${node.id}`}
                className="ml-auto rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-bold text-rose-700 hover:bg-rose-200"
              >
                ✕
              </button>
            </div>
          </div>
        );
      })}

      {pendingFrom ? (
        <div className="pointer-events-none absolute right-3 top-3 rounded bg-slate-900 px-2 py-1 text-xs text-white shadow">
          Connecting from <b>{pendingFrom}</b> — click a target node…
        </div>
      ) : null}
    </div>
  );
}