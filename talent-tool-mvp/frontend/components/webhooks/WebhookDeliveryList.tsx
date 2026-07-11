"use client";

import * as React from "react";
import type { WebhookDelivery } from "@/lib/api-webhooks";

interface Props {
  deliveries: WebhookDelivery[];
  onReplayDeadLetters?: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  success: "bg-green-100 text-green-700",
  pending: "bg-amber-100 text-amber-700",
  failed_retrying: "bg-orange-100 text-orange-700",
  failed_dead_letter: "bg-red-100 text-red-700",
};

export function WebhookDeliveryList({ deliveries, onReplayDeadLetters }: Props) {
  const deadLetterCount = deliveries.filter(
    (d) => d.status === "failed_dead_letter",
  ).length;

  if (deliveries.length === 0) {
    return (
      <div className="rounded-lg border bg-white p-8 text-center text-slate-500 text-sm">
        暂无投递记录
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {deadLetterCount > 0 && onReplayDeadLetters && (
        <button
          onClick={onReplayDeadLetters}
          className="px-3 py-1.5 text-sm rounded-md bg-amber-600 text-white hover:bg-amber-700"
        >
          手动重发死信 ({deadLetterCount})
        </button>
      )}
      <div className="overflow-x-auto rounded-lg border bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 text-left text-xs uppercase text-slate-600">
              <th className="px-3 py-2">事件</th>
              <th className="px-3 py-2">状态</th>
              <th className="px-3 py-2">尝试</th>
              <th className="px-3 py-2">响应码</th>
              <th className="px-3 py-2">错误</th>
              <th className="px-3 py-2">时间</th>
            </tr>
          </thead>
          <tbody>
            {deliveries.map((d) => (
              <tr key={d.id} className="border-t align-top">
                <td className="px-3 py-2 font-mono text-xs">{d.event_type}</td>
                <td className="px-3 py-2">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      STATUS_COLORS[d.status] ?? "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {d.status}
                  </span>
                </td>
                <td className="px-3 py-2">{d.attempts}</td>
                <td className="px-3 py-2">{d.response_code ?? "-"}</td>
                <td className="px-3 py-2 text-xs text-slate-600 max-w-md truncate">
                  {d.last_error ?? "-"}
                </td>
                <td className="px-3 py-2 text-xs text-slate-500 whitespace-nowrap">
                  {d.last_attempt_at
                    ? new Date(d.last_attempt_at).toLocaleString()
                    : new Date(d.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default WebhookDeliveryList;
