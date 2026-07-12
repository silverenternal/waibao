"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  RISK_LEVEL_COLOR,
  RISK_LEVEL_LABEL,
  sendCareMessage,
  type AttritionRisk,
} from "@/lib/api-attrition";

export interface AttritionRiskCardProps {
  risk: AttritionRisk;
  onCare?: (userId: string) => void;
}

/**
 * 离职风险卡片 — 显示风险等级 + 关键因素 + 一键关怀.
 */
export function AttritionRiskCard({ risk, onCare }: AttritionRiskCardProps) {
  const [sending, setSending] = React.useState(false);
  const [sent, setSent] = React.useState(false);

  const handleCare = async () => {
    setSending(true);
    try {
      await sendCareMessage(
        risk.user_id,
        `您好,我们注意到您近期可能遇到一些挑战,想跟您聊聊,看看能提供什么帮助。`,
        "im"
      );
      setSent(true);
      onCare?.(risk.user_id);
    } finally {
      setSending(false);
    }
  };

  const pct = (risk.risk_score * 100).toFixed(0);
  const gaugeColor =
    risk.risk_level === "high"
      ? "bg-rose-500"
      : risk.risk_level === "medium"
        ? "bg-amber-500"
        : "bg-emerald-500";

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{risk.user_id}</CardTitle>
          <Badge className={RISK_LEVEL_COLOR[risk.risk_level]}>
            {RISK_LEVEL_LABEL[risk.risk_level]}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* 分数 gauge */}
        <div>
          <div className="flex items-baseline justify-between mb-1">
            <span className="text-xs text-slate-500">风险分数</span>
            <span className="text-2xl font-bold">{pct}%</span>
          </div>
          <div className="h-2 bg-slate-200 rounded overflow-hidden">
            <div
              className={`h-full ${gaugeColor} transition-all`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        {/* 解释 */}
        <p className="text-xs text-slate-600 leading-relaxed">
          {risk.explanation}
        </p>

        {/* Top 因素 */}
        {risk.factors.length > 0 && (
          <div className="space-y-1 pt-2 border-t">
            <div className="text-xs font-medium text-slate-700">关键因素:</div>
            {risk.factors.map((f, i) => (
              <div key={i} className="flex justify-between text-xs">
                <span className="text-slate-600 truncate">{f.description}</span>
                <span className="text-slate-400 ml-2">
                  {(f.contribution * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        )}

        {/* 模型 + 操作 */}
        <div className="flex items-center justify-between pt-2 border-t">
          <span className="text-xs text-slate-400">
            模型: {risk.model_used}
          </span>
          {risk.risk_level !== "low" && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleCare}
              disabled={sending || sent}
            >
              {sent ? "已发送" : sending ? "发送中…" : "一键关怀"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}