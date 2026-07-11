/**
 * Experiment detail page (T805).
 *
 * 单实验的 overview / variants / 显著性结果 / 启停操作.
 */
"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ExperimentCard } from "@/components/experiments/ExperimentCard";
import { ResultsChart } from "@/components/experiments/ResultsChart";
import {
  abApi,
  type ExperimentRow,
  type ResultsSummary,
} from "@/lib/api-ab";

export default function ExperimentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [experiment, setExperiment] = React.useState<ExperimentRow | null>(null);
  const [results, setResults] = React.useState<ResultsSummary | null>(null);
  const [metricName, setMetricName] = React.useState<string>("");
  const [builtinMetrics, setBuiltinMetrics] = React.useState<string[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    abApi.listBuiltinMetrics().then((r) => setBuiltinMetrics(r.metrics)).catch(() => {});
  }, []);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      const exp = await abApi.getExperiment(id);
      setExperiment(exp);
      if (!metricName) setMetricName(exp.primary_metric);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Load failed");
    }
  }, [id, metricName]);

  React.useEffect(() => {
    load();
  }, [load]);

  React.useEffect(() => {
    if (!id || !metricName) return;
    abApi
      .getResults(id, metricName)
      .then(setResults)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Results failed"));
  }, [id, metricName]);

  const handleAction = async (action: "start" | "stop") => {
    if (!experiment) return;
    setBusy(true);
    try {
      if (action === "start") await abApi.startExperiment(experiment.id);
      else await abApi.stopExperiment(experiment.id);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!experiment) return;
    if (!confirm(`Delete experiment "${experiment.name}"?`)) return;
    setBusy(true);
    try {
      await abApi.deleteExperiment(experiment.id);
      router.push("/mothership/admin/experiments");
    } finally {
      setBusy(false);
    }
  };

  if (error && !experiment) {
    return (
      <div className="p-6">
        <Card>
          <CardContent className="text-sm text-destructive py-4">{error}</CardContent>
        </Card>
      </div>
    );
  }

  if (!experiment) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold">{experiment.name}</h1>
          <p className="text-sm text-muted-foreground">{experiment.description || "No description"}</p>
          <div className="flex items-center gap-2 mt-2">
            <Badge>{experiment.status}</Badge>
            <span className="text-xs text-muted-foreground">
              {experiment.variants.length} variants · primary metric <span className="font-mono">{experiment.primary_metric}</span>
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          {(experiment.status === "draft" || experiment.status === "stopped") && (
            <Button disabled={busy} onClick={() => handleAction("start")}>Start</Button>
          )}
          {experiment.status === "running" && (
            <Button variant="destructive" disabled={busy} onClick={() => handleAction("stop")}>Stop</Button>
          )}
          <Button variant="ghost" disabled={busy} onClick={handleDelete}>Delete</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <h2 className="text-sm font-medium text-muted-foreground mb-2">Variants</h2>
          <ExperimentCard
            experiment={experiment}
            onAction={() => Promise.resolve()}
            isLoading={busy}
          />
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Assignment preview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="text-xs text-muted-foreground">
              Hash bucketing routes users deterministically based on (experiment, user_id, salt).
              Variants are first created with status <code>draft</code> &mdash; activate with Start
              above to begin recording.
            </p>
            <div className="border rounded-md overflow-x-auto">
              <table className="w-full text-sm min-w-[400px]">
                <thead className="bg-muted text-xs">
                  <tr>
                    <th className="text-left px-2 py-2">Variant</th>
                    <th className="text-right px-2 py-2">Weight</th>
                    <th className="text-right px-2 py-2">Share</th>
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    const total = experiment.variants.reduce((s, v) => s + v.weight, 0) || 1;
                    return experiment.variants.map((v) => (
                      <tr key={v.name} className="border-t">
                        <td className="px-2 py-2">{v.name}</td>
                        <td className="text-right font-mono px-2 py-2">{v.weight}</td>
                        <td className="text-right font-mono px-2 py-2">
                          {((v.weight / total) * 100).toFixed(1)}%
                        </td>
                      </tr>
                    ));
                  })()}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-medium text-muted-foreground">Results</h2>
          <div className="w-56">
            <Select value={metricName} onValueChange={(v) => v && setMetricName(v)}>
              <SelectTrigger><SelectValue placeholder="Metric" /></SelectTrigger>
              <SelectContent>
                {(builtinMetrics.length ? builtinMetrics : [experiment.primary_metric]).map((m) => (
                  <SelectItem key={m} value={m}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        {results ? (
          <ResultsChart results={results} metricName={metricName} />
        ) : (
          <Skeleton className="h-48" />
        )}
      </div>
    </div>
  );
}
