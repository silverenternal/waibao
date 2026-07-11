"use client";

import * as React from "react";
import type {
  AtomicCondition,
  BuiltinTrigger,
  ConditionGroup,
  LogicalOp,
  RuleAction,
  RuleCondition,
  ComparisonOp,
} from "@/lib/api-rules";
import { RuleTriggerPicker } from "./RuleTriggerPicker";
import { RuleActionPicker } from "./RuleActionPicker";

interface Props {
  triggers: BuiltinTrigger[];
  initial?: {
    name?: string;
    description?: string;
    trigger?: string;
    condition?: RuleCondition;
    actions?: RuleAction[];
    cooldown_seconds?: number;
    tags?: string[];
    enabled?: boolean;
  };
  onSubmit: (body: {
    name: string;
    description: string;
    trigger: string;
    condition: RuleCondition;
    actions: RuleAction[];
    cooldown_seconds: number;
    tags: string[];
    enabled: boolean;
  }) => Promise<void>;
  submitLabel?: string;
}

const MAX_DEPTH = 3;

const COMPARISON_OPS: ComparisonOp[] = [
  "==",
  "!=",
  "<",
  "<=",
  ">",
  ">=",
  "in",
  "not_in",
  "contains",
  "starts_with",
  "exists",
];

const LOGICAL_OPS: LogicalOp[] = ["AND", "OR", "NOT"];

/**
 * 规则可视化编辑器 (T804).
 *
 * 嵌套条件最多 3 层 (UI 限制 = MAX_DEPTH).
 */
export function RuleEditor({
  triggers,
  initial,
  onSubmit,
  submitLabel = "保存",
}: Props) {
  const [name, setName] = React.useState(initial?.name ?? "");
  const [description, setDescription] = React.useState(
    initial?.description ?? "",
  );
  const [trigger, setTrigger] = React.useState(initial?.trigger ?? "");
  const [condition, setCondition] = React.useState<RuleCondition>(
    initial?.condition ?? null,
  );
  const [actions, setActions] = React.useState<RuleAction[]>(
    initial?.actions ?? [],
  );
  const [cooldown, setCooldown] = React.useState(initial?.cooldown_seconds ?? 0);
  const [tags, setTags] = React.useState((initial?.tags ?? []).join(", "));
  const [enabled, setEnabled] = React.useState(initial?.enabled ?? true);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!name.trim()) {
      setErr("请填写规则名称");
      return;
    }
    if (!trigger) {
      setErr("请选择触发器");
      return;
    }
    setBusy(true);
    try {
      await onSubmit({
        name: name.trim(),
        description,
        trigger,
        condition,
        actions,
        cooldown_seconds: cooldown,
        tags: tags
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean),
        enabled,
      });
    } catch (e: any) {
      setErr(e?.message ?? "保存失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">
            规则名称
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded border-slate-300 border px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">
            触发器
          </label>
          <RuleTriggerPicker
            triggers={triggers}
            value={trigger}
            onChange={setTrigger}
          />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">
          描述 (可选)
        </label>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-full rounded border-slate-300 border px-3 py-2 text-sm"
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-xs font-medium text-slate-700">
            条件 (ConditionGroup,最多 {MAX_DEPTH} 层)
          </label>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => setCondition(_newGroup("AND"))}
              className="px-2 py-0.5 text-[11px] rounded border bg-white hover:bg-slate-50"
            >
              + AND 组
            </button>
            <button
              type="button"
              onClick={() => setCondition(null)}
              className="px-2 py-0.5 text-[11px] rounded border bg-white hover:bg-slate-50"
            >
              清空
            </button>
          </div>
        </div>
        {condition ? (
          <ConditionNode
            node={condition}
            depth={1}
            onChange={(next) => setCondition(next)}
            onRemove={() => setCondition(null)}
          />
        ) : (
          <div className="text-xs text-slate-500">
            无条件 (任何事件都触发)。
          </div>
        )}
      </div>

      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">
          动作
        </label>
        <RuleActionPicker value={actions} onChange={setActions} />
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">
            冷却秒数
          </label>
          <input
            type="number"
            min={0}
            value={cooldown}
            onChange={(e) => setCooldown(Number(e.target.value) || 0)}
            className="w-full rounded border-slate-300 border px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">
            标签 (逗号分隔)
          </label>
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            className="w-full rounded border-slate-300 border px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">
            启用
          </label>
          <label className="inline-flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            <span>{enabled ? "已启用" : "已禁用"}</span>
          </label>
        </div>
      </div>

      {err && (
        <div className="rounded bg-red-50 border border-red-200 p-2 text-xs text-red-700">
          {err}
        </div>
      )}

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={busy}
          className="px-3 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? "保存中..." : submitLabel}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// 嵌套条件节点
// ---------------------------------------------------------------------------

interface NodeProps {
  node: RuleCondition;
  depth: number;
  onChange: (next: RuleCondition) => void;
  onRemove?: () => void;
}

function ConditionNode({ node, depth, onChange, onRemove }: NodeProps) {
  if (!node) return null;

  if ("children" in node) {
    return (
      <ConditionGroupNode
        node={node}
        depth={depth}
        onChange={onChange}
        onRemove={onRemove}
      />
    );
  }
  return (
    <AtomicNode
      node={node}
      onChange={(n) => onChange(n)}
      onRemove={onRemove}
    />
  );
}

function ConditionGroupNode({
  node,
  depth,
  onChange,
  onRemove,
}: {
  node: ConditionGroup;
  depth: number;
  onChange: (next: ConditionGroup) => void;
  onRemove?: () => void;
}) {
  const canNest = depth < MAX_DEPTH;
  function updateChild(idx: number, child: RuleCondition) {
    if (!child) {
      removeChild(idx);
      return;
    }
    const next = node.children.map((c, i) => (i === idx ? child : c));
    onChange({ ...node, children: next });
  }
  function removeChild(idx: number) {
    onChange({ ...node, children: node.children.filter((_, i) => i !== idx) });
  }
  function addChild(kind: "atomic" | "group") {
    if (kind === "atomic") {
      onChange({
        ...node,
        children: [...node.children, _newAtomic()],
      });
    } else if (canNest) {
      onChange({
        ...node,
        children: [...node.children, _newGroup("AND")],
      });
    }
  }

  return (
    <div className="rounded border border-slate-300 bg-white p-2 space-y-2">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="text-slate-500">逻辑</span>
          <select
            value={node.op}
            onChange={(e) =>
              onChange({ ...node, op: e.target.value as LogicalOp })
            }
            className="border rounded px-1 py-0.5 font-mono"
          >
            {LOGICAL_OPS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
          <span className="text-slate-400">
            (深度 {depth}/{MAX_DEPTH})
          </span>
        </div>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => addChild("atomic")}
            className="px-1.5 py-0.5 text-[11px] border rounded hover:bg-slate-50"
          >
            + 原子
          </button>
          <button
            type="button"
            onClick={() => addChild("group")}
            disabled={!canNest}
            className="px-1.5 py-0.5 text-[11px] border rounded hover:bg-slate-50 disabled:opacity-40"
          >
            + 嵌套组
          </button>
          {onRemove && (
            <button
              type="button"
              onClick={onRemove}
              className="px-1.5 py-0.5 text-[11px] border rounded text-red-600 hover:bg-red-50"
            >
              移除
            </button>
          )}
        </div>
      </div>
      <div
        className={`pl-3 border-l-2 space-y-2 ${
          depth === 1
            ? "border-blue-300"
            : depth === 2
              ? "border-emerald-300"
              : "border-amber-300"
        }`}
      >
        {node.children.length === 0 && (
          <div className="text-[11px] text-slate-500">(空)</div>
        )}
        {node.children.map((c, i) => (
          <ConditionNode
            key={i}
            node={c}
            depth={depth + 1}
            onChange={(n) => updateChild(i, n)}
            onRemove={() => removeChild(i)}
          />
        ))}
      </div>
    </div>
  );
}

function AtomicNode({
  node,
  onChange,
  onRemove,
}: {
  node: AtomicCondition;
  onChange: (next: AtomicCondition) => void;
  onRemove?: () => void;
}) {
  return (
    <div className="flex items-center gap-1 text-xs">
      <input
        value={node.field}
        onChange={(e) => onChange({ ...node, field: e.target.value })}
        placeholder="field"
        className="flex-1 font-mono border rounded px-1 py-0.5"
      />
      <select
        value={node.op}
        onChange={(e) =>
          onChange({ ...node, op: e.target.value as ComparisonOp })
        }
        className="font-mono border rounded px-1 py-0.5"
      >
        {COMPARISON_OPS.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      <input
        value={JSON.stringify(node.value)}
        onChange={(e) => {
          try {
            onChange({ ...node, value: JSON.parse(e.target.value) });
          } catch {
            onChange({ ...node, value: e.target.value });
          }
        }}
        placeholder="value (JSON)"
        className="flex-1 font-mono border rounded px-1 py-0.5"
      />
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="px-1.5 py-0.5 border rounded text-red-600 hover:bg-red-50"
        >
          ×
        </button>
      )}
    </div>
  );
}

function _newAtomic(): AtomicCondition {
  return { op: "==", field: "", value: null };
}
function _newGroup(op: LogicalOp): ConditionGroup {
  return { op, children: [] };
}
