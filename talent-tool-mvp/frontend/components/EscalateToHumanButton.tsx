"use client";

/**
 * EscalateToHumanButton — 一键升级 + 自动建议 HRBP (T704).
 *
 * 用法:
 *   <EscalateToHumanButton
 *     text="我对这个回答不满意"
 *     department="payroll"
 *     onEscalated={(ticket) => console.log(ticket)}
 *   />
 *
 * 流程:
 *   1. 用户点击 → 弹确认对话框
 *   2. POST /api/escalation → 创建工单 + 自动建议 HRBP
 *   3. 成功后展示工单号 + 工单详情链接
 */

import { useState } from "react";

export interface EscalateTicket {
  ticket_id: string;
  ticket_no?: string;
  priority: string;
  department: string;
  suggested_hrbp?: { user_id: string; name: string; role: string };
  assignee_id?: string;
  message: string;
}

export interface EscalateToHumanButtonProps {
  text: string;
  department?: string;
  suggestedPriority?: string;
  onEscalated?: (ticket: EscalateTicket) => void;
  className?: string;
  variant?: "primary" | "secondary";
  label?: string;
}

export default function EscalateToHumanButton({
  text,
  department,
  suggestedPriority,
  onEscalated,
  className = "",
  variant = "primary",
  label = "升级人工",
}: EscalateToHumanButtonProps) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ticket, setTicket] = useState<EscalateTicket | null>(null);

  async function submit() {
    if (!text.trim()) {
      setError("请填写问题描述");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/escalation", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          text,
          department: department || undefined,
          priority: suggestedPriority || undefined,
          suggested_hrbp: true,
        }),
      });
      const data = await r.json();
      if (!r.ok || !data.success) {
        throw new Error(data?.detail || data?.message || `HTTP ${r.status}`);
      }
      setTicket(data);
      onEscalated?.(data);
    } catch (e: any) {
      setError(e?.message || "升级失败");
    } finally {
      setSubmitting(false);
    }
  }

  function close() {
    setOpen(false);
    setError(null);
    // keep ticket until next open
  }

  const btnClass =
    variant === "primary"
      ? "bg-red-600 text-white hover:bg-red-700"
      : "bg-slate-200 text-slate-800 hover:bg-slate-300";

  return (
    <>
      <button
        data-testid="escalate-btn"
        onClick={() => setOpen(true)}
        className={`px-3 py-1.5 text-sm rounded ${btnClass} ${className}`}
      >
        🚨 {label}
      </button>

      {open && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"
          onClick={close}
        >
          <div
            className="bg-white rounded-lg shadow-lg max-w-md w-full p-5 space-y-4"
            onClick={(e) => e.stopPropagation()}
            data-testid="escalate-dialog"
          >
            {!ticket ? (
              <>
                <div className="text-lg font-semibold">确认升级人工?</div>
                <div className="text-sm text-slate-600">
                  我们会立即创建一个保密工单,并自动建议 HRBP 处理。
                </div>
                <div className="bg-slate-50 p-3 rounded text-sm">
                  <div className="font-medium">问题:</div>
                  <div className="text-slate-700 mt-1">{text.slice(0, 200)}</div>
                </div>
                {department && (
                  <div className="text-xs text-slate-500">
                    部门: {department} · 优先级: {suggestedPriority || "auto"}
                  </div>
                )}
                {error && (
                  <div className="text-sm text-red-600 bg-red-50 p-2 rounded">{error}</div>
                )}
                <div className="flex justify-end space-x-2">
                  <button
                    onClick={close}
                    disabled={submitting}
                    className="px-3 py-1.5 text-sm rounded bg-slate-200 hover:bg-slate-300 disabled:opacity-50"
                  >
                    取消
                  </button>
                  <button
                    data-testid="escalate-confirm"
                    onClick={submit}
                    disabled={submitting}
                    className="px-3 py-1.5 text-sm rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    {submitting ? "提交中..." : "确认升级"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="text-lg font-semibold text-green-700">✓ 升级成功</div>
                <div className="bg-green-50 p-3 rounded text-sm space-y-1" data-testid="escalate-result">
                  <div>
                    <span className="font-medium">工单号:</span> #{ticket.ticket_no || ticket.ticket_id}
                  </div>
                  <div>
                    <span className="font-medium">部门:</span> {ticket.department}
                  </div>
                  <div>
                    <span className="font-medium">优先级:</span> {ticket.priority}
                  </div>
                  {ticket.suggested_hrbp && (
                    <div>
                      <span className="font-medium">建议 HRBP:</span>{" "}
                      {ticket.suggested_hrbp.name} ({ticket.suggested_hrbp.role})
                    </div>
                  )}
                  <div className="text-slate-600 mt-2">{ticket.message}</div>
                </div>
                <div className="flex justify-between items-center">
                  <a
                    href={`/mothership/tickets/${ticket.ticket_id}`}
                    data-testid="escalate-ticket-link"
                    className="text-sm text-sky-600 underline"
                  >
                    查看工单详情 →
                  </a>
                  <button
                    onClick={close}
                    className="px-3 py-1.5 text-sm rounded bg-slate-200 hover:bg-slate-300"
                  >
                    关闭
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}