"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  FEATURE_LABEL,
  RISK_LEVEL_COLOR,
  RISK_LEVEL_LABEL,
  type AttritionRisk,
  type HireSuccess,
} from "@/lib/api-predictive";

export interface PredictionCardProps {
  kind: "attrition" | "hire_success";
  data: AttritionRisk | HireSuccess;
  onAction?: (action: string) => void;
}

function isAttrition(d: AttritionRisk | HireSuccess): d is AttritionRisk {
  return (d as AttritionRisk).risk_level !== undefined;
}

function AttritionBody({ risk }: { risk: AttritionRisk }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-3xl font-semibold tabular-nums">
            {(risk.risk_score * 100).toFixed(0)}
            <span className="ml-1 text-sm text-muted-foreground">/ 100</span>
          </div>
          <p className="text-xs text-muted-foreground">
            模型: {risk.model_used} · 推理 {risk.inference_ms.toFixed(1)} ms
          </p>
        </div>
        <Badge
          variant="outline"
          className={RISK_LEVEL_COLOR[risk.risk_level]}
        >
          {RISK_LEVEL_LABEL[risk.risk_level]}
        </Badge>
      </div>
      <p className="text-sm">{risk.explanation}</p>
      <div>
        <h4 className="mb-1 text-xs font-medium uppercase text-muted-foreground">
          关键因素
        </h4>
        <ul className="space-y-1 text-sm">
          {risk.factors.slice(0, 3).map((f) => (
            <li
              key={f.feature}
              className="flex items-center justify-between rounded bg-muted/40 px-2 py-1"
            >
              <span>{FEATURE_LABEL[f.feature] ?? f.feature}</span>
              <span
                className={
                  f.direction === "up"
                    ? "text-red-600"
                    : "text-emerald-600"
                }
              >
                {(f.impact * 100).toFixed(0)}%
              </span>
            </li>
          ))}
        </ul>
      </div>
      {risk.intervention.length ? (
        <div>
          <h4 className="mb-1 text-xs font-medium uppercase text-muted-foreground">
            干预建议
          </h4>
          <ul className="list-inside list-disc space-y-0.5 text-sm">
            {risk.intervention.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={() => undefined}
          className="bg-primary text-primary-foreground"
        >
          发送关怀
        </Button>
        <Button size="sm" variant="outline">
          查看时间线
        </Button>
      </div>
    </div>
  );
}

function HireSuccessBody({ score }: { score: HireSuccess }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-3xl font-semibold tabular-nums">
            {(score.success_score * 100).toFixed(0)}
            <span className="ml-1 text-sm text-muted-foreground">/ 100</span>
          </div>
          <p className="text-xs text-muted-foreground">
            模型: {score.model_used} · 推理 {score.inference_ms.toFixed(1)} ms
          </p>
        </div>
        <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
          入职成功概率
        </Badge>
      </div>
      <p className="text-sm">{score.explanation}</p>
      <div>
        <h4 className="mb-1 text-xs font-medium uppercase text-muted-foreground">
          关键驱动
        </h4>
        <ul className="space-y-1 text-sm">
          {score.drivers.slice(0, 3).map((d) => (
            <li
              key={d.feature}
              className="flex items-center justify-between rounded bg-muted/40 px-2 py-1"
            >
              <span>{FEATURE_LABEL[d.feature] ?? d.feature}</span>
              <span className="tabular-nums text-muted-foreground">
                {(d.impact * 100).toFixed(0)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function PredictionCard({ kind, data, onAction }: PredictionCardProps) {
  const title =
    kind === "attrition"
      ? isAttrition(data)
        ? `离职风险 — ${data.user_id}`
        : "离职风险"
      : isAttrition(data)
      ? "离职风险"
      : `入职成功 — ${data.candidate_id}`;

  React.useEffect(() => {
    onAction?.("view");
  }, [onAction]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {isAttrition(data) ? (
          <AttritionBody risk={data} />
        ) : (
          <HireSuccessBody score={data} />
        )}
      </CardContent>
    </Card>
  );
}
