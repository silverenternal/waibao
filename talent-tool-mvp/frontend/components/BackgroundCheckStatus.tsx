"use client";

/**
 * BackgroundCheckStatus (T1307)
 * 在工单/候选人详情里展示背调进行状态 + findings + 报告链接.
 */
import * as React from "react";
import {
  Shield,
  Check,
  AlertTriangle,
  AlertOctagon,
  Loader2,
  ExternalLink,
  CircleDashed,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  bgCheckApi,
  type BGCheckRecord,
  type BGCheckStatus,
} from "@/lib/api-background-check";

interface Props {
  checkId?: string;
  candidateId?: string;
  offerId?: string;
  refreshMs?: number;
  onUpdate?: (status: BGCheckStatus) => void;
}

const STATUS_CONFIG = {
  pending: {
    label: "Pending",
    color: "text-gray-600",
    bg: "bg-gray-50",
    icon: CircleDashed,
  },
  in_progress: {
    label: "In progress",
    color: "text-blue-600",
    bg: "bg-blue-50",
    icon: Loader2,
  },
  clear: {
    label: "Cleared",
    color: "text-emerald-600",
    bg: "bg-emerald-50",
    icon: Check,
  },
  consider: {
    label: "Needs review",
    color: "text-amber-600",
    bg: "bg-amber-50",
    icon: AlertTriangle,
  },
  suspended: {
    label: "Suspended",
    color: "text-red-600",
    bg: "bg-red-50",
    icon: AlertOctagon,
  },
} as const;

export function BackgroundCheckStatus({
  checkId,
  candidateId,
  offerId,
  refreshMs,
  onUpdate,
}: Props) {
  const [check, setCheck] = React.useState<BGCheckRecord | null>(null);
  const [status, setStatus] = React.useState<BGCheckStatus | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    if (!checkId && !candidateId) return;
    setLoading(true);
    setError(null);
    try {
      if (!checkId && candidateId) {
        const list = await bgCheckApi.list({ candidate_id: candidateId });
        const latest = (list.data || [])[0];
        if (latest) {
          setCheck(latest);
          const st = await bgCheckApi.status(latest.check_id);
          setStatus(st.data);
          onUpdate?.(st.data);
          return;
        }
        return;
      }
      if (checkId) {
        const st = await bgCheckApi.status(checkId);
        setStatus(st.data);
        onUpdate?.(st.data);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  }, [checkId, candidateId, onUpdate]);

  React.useEffect(() => {
    load();
  }, [load]);

  React.useEffect(() => {
    if (!refreshMs) return;
    const t = window.setInterval(load, refreshMs);
    return () => window.clearInterval(t);
  }, [refreshMs, load]);

  const triggerPreOffer = async () => {
    if (!candidateId) return;
    setError(null);
    try {
      const out = await bgCheckApi.triggerPreOffer({
        candidate_id: candidateId,
        offer_id: offerId,
      });
      setError(null);
      if (out.data?.data?.check_id) {
        await load();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "trigger failed");
    }
  };

  const cfg = status ? STATUS_CONFIG[status.status] : null;
  const Icon = cfg ? cfg.icon : Shield;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Shield className="h-5 w-5" />
          Background check
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {!checkId && !candidateId ? (
          <p className="text-sm text-gray-500">No candidate selected.</p>
        ) : status && cfg ? (
          <>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Icon
                  className={`h-5 w-5 ${cfg.color} ${
                    status.status === "in_progress" ? "animate-spin" : ""
                  }`}
                />
                <span
                  className={`rounded-full px-3 py-1 text-sm font-medium ${cfg.color} ${cfg.bg}`}
                >
                  {cfg.label}
                </span>
              </div>
              <span className="text-sm text-gray-500">
                {status.progress_pct.toFixed(0)}%
              </span>
            </div>

            {status.report_url && (
              <a
                href={status.report_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
              >
                Open report <ExternalLink className="h-3 w-3" />
              </a>
            )}

            {status.findings.length > 0 && (
              <div className="rounded border bg-amber-50 p-2 text-sm">
                <p className="font-medium text-amber-700">
                  {status.findings.length} finding(s)
                </p>
                <ul className="mt-1 space-y-1">
                  {status.findings.slice(0, 5).map((f, i) => (
                    <li key={i} className="text-amber-900">
                      <strong>{f.severity}</strong>: {f.description || f.code}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        ) : (
          <p className="text-sm text-gray-500">No check initiated.</p>
        )}

        {candidateId && !status && (
          <Button size="sm" variant="outline" onClick={triggerPreOffer}>
            Trigger pre-offer check
          </Button>
        )}

        <Button
          size="sm"
          variant="ghost"
          onClick={load}
          disabled={loading}
        >
          {loading ? (
            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
          ) : null}
          Refresh
        </Button>

        {error && (
          <p className="rounded bg-red-50 p-2 text-xs text-red-700">{error}</p>
        )}
      </CardContent>
    </Card>
  );
}
