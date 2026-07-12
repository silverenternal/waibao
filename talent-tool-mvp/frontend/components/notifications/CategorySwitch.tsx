"use client";

/**
 * T2304 — 单类别 × 优先级的开关矩阵.
 *
 * Props:
 *  - category: matching/ticket/emotion/system/recruiting
 *  - label: 显示名
 *  - priorities: 优先级列表 (高/中/低)
 *  - channels: 通道列表
 *  - matrix: 当前 (priority, channel) 开关状态
 *  - onToggle: (priority, channel, enabled) => void
 *
 * 设计: 表格行=优先级, 列=通道. 单元格为 Switch.
 */

import * as React from "react";
import { Mail, Smartphone, Globe, Hash, MessageCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

export type ChannelKey = "smtp" | "dingtalk" | "feishu" | "im" | "web";
export type PriorityKey = "high" | "medium" | "low";

export interface CategorySwitchProps {
  category: string;
  label: string;
  description?: string;
  priorities: PriorityKey[];
  channels: ChannelKey[];
  /**
   * matrix[p][c] = boolean (是否启用)
   * 默认 true (全开).
   */
  matrix: Record<PriorityKey, Record<ChannelKey, boolean>>;
  onToggle: (priority: PriorityKey, channel: ChannelKey, enabled: boolean) => void;
  /** 可选: 显示该类别的频率摘要 (例如 weekly digest) */
  badge?: string;
}

const CHANNEL_ICONS: Record<ChannelKey, React.ReactNode> = {
  smtp: <Mail className="h-4 w-4" aria-hidden="true" />,
  dingtalk: <Hash className="h-4 w-4" aria-hidden="true" />,
  feishu: <MessageCircle className="h-4 w-4" aria-hidden="true" />,
  im: <Smartphone className="h-4 w-4" aria-hidden="true" />,
  web: <Globe className="h-4 w-4" aria-hidden="true" />,
};

const CHANNEL_LABELS: Record<ChannelKey, string> = {
  smtp: "邮件",
  dingtalk: "钉钉",
  feishu: "飞书",
  im: "IM",
  web: "Web",
};

const PRIORITY_LABELS: Record<PriorityKey, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

const PRIORITY_BADGE: Record<PriorityKey, string> = {
  high: "destructive",
  medium: "default",
  low: "secondary",
};

export function CategorySwitch(props: CategorySwitchProps) {
  const {
    category,
    label,
    description,
    priorities,
    channels,
    matrix,
    onToggle,
    badge,
  } = props;

  const rowKey = `cs-${category}`;

  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950"
      data-category={category}
      data-testid={`category-switch-${category}`}
    >
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
            {label}
          </h3>
          {description && (
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              {description}
            </p>
          )}
        </div>
        {badge && <Badge variant="outline">{badge}</Badge>}
      </header>

      <div className="overflow-x-auto">
        <table className="w-full text-sm" role="grid" aria-label={label}>
          <thead>
            <tr>
              <th className="px-2 py-2 text-left font-medium text-slate-500">
                优先级
              </th>
              {channels.map((c) => (
                <th
                  key={`${rowKey}-h-${c}`}
                  className="px-2 py-2 text-center font-medium text-slate-500"
                  scope="col"
                >
                  <span className="inline-flex items-center gap-1">
                    {CHANNEL_ICONS[c]}
                    {CHANNEL_LABELS[c]}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {priorities.map((p) => (
              <tr key={`${rowKey}-${p}`} className="border-t border-slate-100">
                <th
                  scope="row"
                  className="px-2 py-2 text-left font-medium text-slate-700 dark:text-slate-200"
                >
                  <Badge variant={PRIORITY_BADGE[p] as never}>
                    {PRIORITY_LABELS[p]}
                  </Badge>
                </th>
                {channels.map((c) => {
                  const enabled = matrix[p]?.[c] ?? true;
                  return (
                    <td key={`${rowKey}-${p}-${c}`} className="px-2 py-2 text-center">
                      <button
                        type="button"
                        role="switch"
                        aria-checked={enabled}
                        aria-label={`${label} ${PRIORITY_LABELS[p]} ${CHANNEL_LABELS[c]}`}
                        onClick={() => onToggle(p, c, !enabled)}
                        data-priority={p}
                        data-channel={c}
                        className={cn(
                          "relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500",
                          enabled
                            ? "bg-indigo-600"
                            : "bg-slate-300 dark:bg-slate-700",
                        )}
                      >
                        <span
                          className={cn(
                            "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
                            enabled ? "translate-x-4" : "translate-x-0.5",
                          )}
                        />
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default CategorySwitch;