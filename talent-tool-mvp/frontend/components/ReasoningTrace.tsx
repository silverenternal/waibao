"use client";

import { useState } from "react";

type Step = {
  step: number;
  thought: string;
  action?: string;
  observation?: string;
};

type ReasoningProps = {
  steps: Step[];
  defaultOpen?: boolean;
};

/**
 * 推理过程可视化组件
 * 让用户看到 agent 是怎么思考的,而不是黑盒
 */
export function ReasoningTrace({ steps, defaultOpen = false }: ReasoningProps) {
  const [open, setOpen] = useState(defaultOpen);

  if (!steps || steps.length === 0) return null;

  return (
    <div className="mt-3 border-t pt-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-700"
      >
        <span className={`transition-transform ${open ? "rotate-90" : ""}`}>▶</span>
        🧠 查看推理过程 ({steps.length} 步)
      </button>

      {open && (
        <div className="mt-3 space-y-2 text-sm">
          {steps.map((s, i) => (
            <div key={i} className="border rounded-lg p-3 bg-slate-50">
              <div className="text-xs text-slate-400 mb-1">Step {s.step}</div>
              {s.thought && (
                <div className="mb-2">
                  <span className="text-purple-600 font-medium">💭 Thought:</span>{" "}
                  <span className="text-slate-700">{s.thought}</span>
                </div>
              )}
              {s.action && (
                <div className="mb-2">
                  <span className="text-blue-600 font-medium">🔧 Action:</span>{" "}
                  <code className="bg-blue-100 px-1.5 py-0.5 rounded text-xs">
                    {s.action}
                  </code>
                </div>
              )}
              {s.observation && (
                <div>
                  <span className="text-green-600 font-medium">👁 Observation:</span>{" "}
                  <span className="text-slate-700 text-xs whitespace-pre-wrap">
                    {s.observation.length > 200
                      ? s.observation.slice(0, 200) + "..."
                      : s.observation}
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * 置信度可视化(可与 ReasoningTrace 配合使用)
 */
export function ConfidenceBar({ value, label }: { value: number; label?: string }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 80 ? "bg-green-500" : pct >= 60 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2 text-xs">
      {label && <span className="text-slate-500">{label}</span>}
      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-slate-600">{pct}%</span>
    </div>
  );
}

/**
 * 偏见提醒卡片 — 给老板/HR 看的委婉偏见提示
 */
export function BiasCard({
  biases,
}: {
  biases: { type: string; concern: string; suggestion: string }[];
}) {
  if (!biases || biases.length === 0) return null;
  return (
    <div className="mt-3 p-4 bg-amber-50 border border-amber-200 rounded-lg">
      <div className="flex items-center gap-2 text-amber-800 font-medium mb-2">
        💡 我注意到几个可能值得重新考虑的地方
      </div>
      <ul className="space-y-2 text-sm text-amber-900">
        {biases.map((b, i) => (
          <li key={i}>
            <span className="font-medium">{b.type}:</span> {b.concern}
            <div className="ml-4 mt-1 text-amber-700 italic">建议: {b.suggestion}</div>
          </li>
        ))}
      </ul>
      <div className="mt-2 text-xs text-amber-600">
        我不是指责,而是想帮您扩大候选人池。研究表明,无明确标准的偏好会显著降低招聘质量。
      </div>
    </div>
  );
}