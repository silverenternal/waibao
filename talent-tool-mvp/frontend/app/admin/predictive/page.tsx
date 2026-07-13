"use client";

import * as React from "react";
import {
  predictiveApi,
  type PredictiveHealth,
  type RetrainResult,
} from "@/lib/api-predictive";

interface ModelStatus {
  attrition: { loaded: boolean; path: string | null };
  hire_success: { loaded: boolean };
  prophet_metric: string | null;
}

export default function AdminPredictivePage() {
  const [health, setHealth] = React.useState<PredictiveHealth | null>(null);
  const [status, setStatus] = React.useState<ModelStatus | null>(null);
  const [retrainResult, setRetrainResult] = React.useState<RetrainResult | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [n, setN] = React.useState(2000);
  const [error, setError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    try {
      const [h, m] = await Promise.all([
        predictiveApi.health(),
        predictiveApi.models(),
      ]);
      setHealth(h);
      setStatus(m as ModelStatus);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  const runRetrain = React.useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setRetrainResult(await predictiveApi.retrain(n));
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [n, refresh]);

  return (
    <div className="flex flex-col gap-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">预测模型管理</h1>
        <p className="text-sm text-muted-foreground">
          训练、加载、监控 LightGBM / Prophet 模型
        </p>
      </header>

      {error ? (
        <div className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm">
          {error}
        </div>
      ) : null}

      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <ModelCard
          title="Attrition (LightGBM)"
          loaded={status?.attrition.loaded ?? null}
          detail={status?.attrition.path ?? ""}
        />
        <ModelCard
          title="HireSuccess (LightGBM)"
          loaded={status?.hire_success.loaded ?? null}
          detail="hire_success_v1.pkl"
        />
        <ModelCard
          title="Prophet (时间序列)"
          loaded={status?.prophet_metric != null}
          detail={status?.prophet_metric ?? ""}
        />
      </section>

      <section className="rounded-lg border p-4">
        <h2 className="mb-3 text-base font-medium">手动重训</h2>
        <p className="mb-3 text-xs text-muted-foreground">
          默认每月由 Celery beat 自动触发;此处手动触发会基于合成数据快速重训两个模型。
        </p>
        <div className="mb-3 flex items-center gap-2">
          <label className="text-sm">样本数</label>
          <input
            type="number"
            value={n}
            onChange={(e) => setN(Number(e.target.value))}
            className="w-32 rounded border bg-background px-2 py-1 text-sm"
            min={100}
            max={20000}
            step={100}
          />
          <button
            className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground"
            onClick={runRetrain}
            disabled={busy}
          >
            {busy ? "训练中…" : "开始训练"}
          </button>
        </div>
        {retrainResult ? (
          <div className="rounded bg-muted/40 p-3 text-sm">
            <div>
              状态: <strong>{retrainResult.status}</strong> · 耗时:{" "}
              {retrainResult.duration_seconds.toFixed(1)}s
            </div>
            <div>Attrition AUC: {retrainResult.metrics.attrition.auc.toFixed(3)}</div>
            <div>
              HireSuccess RMSE: {retrainResult.metrics.hire_success.rmse.toFixed(4)}
            </div>
            <div>Prophet trained: {String(retrainResult.metrics.prophet_trained)}</div>
          </div>
        ) : null}
      </section>

      <section className="rounded-lg border p-4">
        <h2 className="mb-3 text-base font-medium">健康检查</h2>
        {health ? (
          <pre className="overflow-auto rounded bg-muted/40 p-3 text-xs">
            {JSON.stringify(health, null, 2)}
          </pre>
        ) : (
          <p className="text-sm text-muted-foreground">加载中…</p>
        )}
      </section>
    </div>
  );
}

function ModelCard(props: {
  title: string;
  loaded: boolean | null;
  detail: string;
}) {
  const tone =
    props.loaded === null
      ? "bg-muted text-muted-foreground"
      : props.loaded
      ? "bg-emerald-100 text-emerald-800"
      : "bg-amber-100 text-amber-800";
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">{props.title}</h3>
        <span
          className={`rounded px-2 py-0.5 text-xs ${tone}`}
        >
          {props.loaded === null
            ? "加载中"
            : props.loaded
            ? "已加载"
            : "未加载"}
        </span>
      </div>
      <p className="mt-2 break-all text-xs text-muted-foreground">
        {props.detail || "—"}
      </p>
    </div>
  );
}
