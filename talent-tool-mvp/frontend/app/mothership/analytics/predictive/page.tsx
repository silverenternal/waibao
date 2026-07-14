"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import * as React from "react";
import { PredictionCard } from "@/components/predictive/PredictionCard";
import {
  predictiveApi,
  type AttritionRisk,
  type ForecastResult,
  type HireSuccess,
} from "@/lib/api-predictive";

type Tab = "attrition" | "hire_success" | "forecast";

export default function PredictiveAnalyticsPage() {
  const [tab, setTab] = React.useState<Tab>("attrition");
  const [userId, setUserId] = React.useState("u-demo-001");
  const [candidateId, setCandidateId] = React.useState("c-demo-001");
  const [attrition, setAttrition] = React.useState<AttritionRisk | null>(null);
  const [hire, setHire] = React.useState<HireSuccess | null>(null);
  const [forecast, setForecast] = React.useState<ForecastResult | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const runAttrition = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAttrition(await predictiveApi.attrition(userId));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [userId]);

  const runHire = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setHire(await predictiveApi.hireSuccess(candidateId));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [candidateId]);

  const runForecast = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setForecast(await predictiveApi.forecast({ horizonDays: 30 }));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <ErrorBoundary>(<div className="flex flex-col gap-6 p-6">
        <header>
          <h1 className="text-2xl font-semibold">预测分析</h1>
          <p className="text-sm text-muted-foreground">
            LightGBM (离职 / 入职成功) + Prophet (时间序列)
          </p>
        </header>
        <div className="flex gap-2 border-b">
          {(
            [
              { k: "attrition", label: "离职风险" },
              { k: "hire_success", label: "入职成功" },
              { k: "forecast", label: "时间序列预测" },
            ] as { k: Tab; label: string }[]
          ).map((t) => (
            <button
              key={t.k}
              className={`px-3 py-2 text-sm ${
                tab === t.k
                  ? "border-b-2 border-primary font-medium"
                  : "text-muted-foreground"
              }`}
              onClick={() => setTab(t.k)}
            >
              {t.label}
            </button>
          ))}
        </div>
        {error ? (
          <div className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm">
            {error}
          </div>
        ) : null}
        {tab === "attrition" ? (
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-lg border p-4">
              <h2 className="mb-2 text-sm font-medium">用户 ID</h2>
              <div className="flex gap-2">
                <input
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                  className="flex-1 rounded border bg-background px-2 py-1 text-sm"
                />
                <button
                  className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground"
                  onClick={runAttrition}
                  disabled={loading}
                >
                  {loading ? "运行中…" : "预测"}
                </button>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                特征: 情绪 / journal / 互动间隔 / 工单 / 任务完成率 / 司龄 / 晋升
              </p>
            </div>
            {attrition ? (
              <PredictionCard kind="attrition" data={attrition} />
            ) : (
              <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
                等待运行 — 单次推理目标 &lt; 100ms
              </div>
            )}
          </section>
        ) : null}
        {tab === "hire_success" ? (
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-lg border p-4">
              <h2 className="mb-2 text-sm font-medium">候选人 ID</h2>
              <div className="flex gap-2">
                <input
                  value={candidateId}
                  onChange={(e) => setCandidateId(e.target.value)}
                  className="flex-1 rounded border bg-background px-2 py-1 text-sm"
                />
                <button
                  className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground"
                  onClick={runHire}
                  disabled={loading}
                >
                  {loading ? "运行中…" : "预测"}
                </button>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                特征: 匹配分 / 渠道 / 资历 / 决策时长 / 3 项评估分数 / 城市 / 远程
              </p>
            </div>
            {hire ? (
              <PredictionCard kind="hire_success" data={hire} />
            ) : (
              <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
                等待运行 — LightGBM 回归
              </div>
            )}
          </section>
        ) : null}
        {tab === "forecast" ? (
          <section className="flex flex-col gap-4">
            <div className="rounded-lg border p-4">
              <h2 className="mb-2 text-sm font-medium">候选人流入预测</h2>
              <div className="flex gap-2">
                <button
                  className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground"
                  onClick={runForecast}
                  disabled={loading}
                >
                  {loading ? "运行中…" : "预测未来 30 天"}
                </button>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                模型: Prophet (daily + weekly seasonality)
              </p>
            </div>
            {forecast ? <ForecastChart forecast={forecast} /> : null}
          </section>
        ) : null}
      </div>)</ErrorBoundary>
  );
}

function ForecastChart({ forecast }: { forecast: ForecastResult }) {
  const width = 720;
  const height = 220;
  const padX = 24;
  const padY = 16;
  const data = forecast.points;
  if (data.length === 0) return null;
  const maxY = Math.max(
    1,
    ...data.map((p) => Math.max(p.yhat, p.yhat_upper))
  );
  const minY = Math.min(0, ...data.map((p) => p.yhat_lower));
  const range = maxY - minY;
  const xFor = (i: number) =>
    padX + (i / Math.max(1, data.length - 1)) * (width - 2 * padX);
  const yFor = (v: number) =>
    height - padY - ((v - minY) / range) * (height - 2 * padY);
  const linePath = data
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xFor(i)} ${yFor(p.yhat)}`)
    .join(" ");
  const upper = data
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xFor(i)} ${yFor(p.yhat_upper)}`)
    .join(" ");
  const lowerRev = [...data]
    .reverse()
    .map((p, idx) => {
      const i = data.length - 1 - idx;
      return `${idx === 0 ? "L" : "L"} ${xFor(i)} ${yFor(p.yhat_lower)}`;
    })
    .join(" ");
  const band = `${upper} ${lowerRev} Z`;
  return (
    <div className="rounded-lg border p-4">
      <div className="mb-2 flex items-center justify-between text-sm">
        <span>模型: {forecast.model_used}</span>
        <span>趋势斜率: {forecast.trend_slope.toFixed(3)}</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full">
        <path d={band} fill="hsl(var(--primary) / 0.15)" />
        <path d={linePath} fill="none" stroke="hsl(var(--primary))" strokeWidth={2} />
        {data.map((p, i) => (
          <circle
            key={i}
            cx={xFor(i)}
            cy={yFor(p.yhat)}
            r={1.5}
            fill="hsl(var(--primary))"
          />
        ))}
        {data.map((p, i) =>
          i % Math.ceil(data.length / 6) === 0 ? (
            <text
              key={i}
              x={xFor(i)}
              y={height - 2}
              textAnchor="middle"
              fontSize={9}
              fill="hsl(var(--muted-foreground))"
            >
              {p.ds.slice(5)}
            </text>
          ) : null
        )}
      </svg>
    </div>
  );
}
