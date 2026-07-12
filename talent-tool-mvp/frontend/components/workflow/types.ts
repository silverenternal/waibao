/**
 * v6.0 T2105 — Shared types for the workflow editor.
 *
 * The frontend mirrors the backend's `WorkflowDefinition` shape but
 * preserves canvas positions (x/y) so the React Flow-like UI can
 * round-trip the graph without server-side schema changes.
 */

export type NodeType =
  | "trigger"
  | "agent"
  | "condition"
  | "action"
  | "delay"
  | "human";

export interface WorkflowNode {
  id: string;
  type: NodeType;
  config: Record<string, unknown>;
  next_nodes: string[];
  /** Canvas position; only relevant for the editor, not the engine. */
  position?: { x: number; y: number };
}

export interface WorkflowEdge {
  from_node: string;
  to_node: string;
  condition?: string | null;
}

export interface WorkflowDefinition {
  name: string;
  version: string;
  description?: string;
  start_node?: string | null;
  variables?: Record<string, unknown>;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

export interface WorkflowRecord {
  id: number;
  name: string;
  description?: string;
  version?: string;
  definition: WorkflowDefinition;
  category?: string | null;
  is_template?: boolean;
  created_by?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface RunRecord {
  run_id: string;
  workflow_id: number;
  workflow_name: string;
  status:
    | "pending"
    | "running"
    | "paused"
    | "completed"
    | "failed"
    | "cancelled";
  input?: unknown;
  output?: unknown;
  variables?: Record<string, unknown>;
  nodes_executed?: string[];
  paused_at_node?: string | null;
  error?: string | null;
  started_at?: string;
  finished_at?: string | null;
}

export interface TemplateSummary {
  name: string;
  version: string;
  description: string;
  node_count: number;
  edge_count: number;
  start_node: string | null;
  definition: WorkflowDefinition;
}