/**
 * Experiments admin index (T805).
 *
 * 列出全部 A/B 实验并提供 create / start / stop 操作.
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ExperimentCard } from "@/components/experiments/ExperimentCard";
import { VariantEditor } from "@/components/experiments/VariantEditor";
import {
  abApi,
  type ExperimentRow,
  type ExperimentStatus,
  type VariantPayload,
} from "@/lib/api-ab";

export default function ExperimentsListPage() {
  const [experiments, setExperiments] = React.useState<ExperimentRow[] | null>(null);
  const [metrics, setMetrics] = React.useState<string[]>([]);
  const [filter, setFilter] = React.useState<"all" | ExperimentStatus>("all");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Create form state
  const [open, setOpen] = React.useState(false);
  const [formName, setFormName] = React.useState("");
  const [formDescription, setFormDescription] = React.useState("");
  const [formMetric, setFormMetric] = React.useState("match.score");
  const [formVariants, setFormVariants] = React.useState<VariantPayload[]>([
    { name: "control", weight: 50, config: {} },
    { name: "treatment", weight: 50, config: {} },
  ]);

  const refresh = React.useCallback(async () => {
    setError(null);
    try {
      const list = await abApi.listExperiments(filter === "all" ? undefined : filter);
      setExperiments(list);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }, [filter]);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  React.useEffect(() => {
    abApi.listBuiltinMetrics().then((r) => setMetrics(r.metrics)).catch(() => setMetrics([]));
  }, []);

  const handleCreate = async () => {
    if (!formName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await abApi.createExperiment({
        name: formName.trim(),
        description: formDescription,
        primary_metric: formMetric,
        variants: formVariants,
      });
      setOpen(false);
      setFormName("");
      setFormDescription("");
      setFormVariants([
        { name: "control", weight: 50, config: {} },
        { name: "treatment", weight: 50, config: {} },
      ]);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setBusy(false);
    }
  };

  const handleAction = async (
    action: "start" | "stop",
    exp: ExperimentRow
  ) => {
    setBusy(true);
    setError(null);
    try {
      if (action === "start") await abApi.startExperiment(exp.id);
      else await abApi.stopExperiment(exp.id);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `${action} failed`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold">A/B Experiments</h1>
          <p className="text-sm text-muted-foreground">
            Define and monitor experiments across matching, ranking, prompts and more.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Select value={filter} onValueChange={(v) => v && setFilter(v as ExperimentStatus | "all")}>
            <SelectTrigger className="w-32"><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="running">Running</SelectItem>
              <SelectItem value="stopped">Stopped</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
            </SelectContent>
          </Select>

          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger>
              <Button>New experiment</Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Create experiment</DialogTitle>
                <DialogDescription>
                  Experiments split traffic by hash bucket. Each variant receives a weighted
                  share of incoming users.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-1">
                  <Label className="text-xs">Name</Label>
                  <Input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="match_weights_v3" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Description</Label>
                  <Input value={formDescription} onChange={(e) => setFormDescription(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Primary metric</Label>
                  <Select value={formMetric} onValueChange={(v) => v && setFormMetric(v)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {(metrics.length ? metrics : ["match.score"]).map((m) => (
                        <SelectItem key={m} value={m}>{m}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Variants (weight)</Label>
                  <VariantEditor variants={formVariants} onChange={setFormVariants} />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
                <Button onClick={handleCreate} disabled={busy || !formName.trim()}>
                  Create
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {error && (
        <Card>
          <CardContent className="text-sm text-destructive py-3">{error}</CardContent>
        </Card>
      )}

      {experiments === null ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      ) : experiments.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">No experiments yet</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Create your first A/B experiment to start testing new variants. See the docs at{" "}
            <Link href="/docs/experiments" className="underline">
              /docs/experiments
            </Link>
            .
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {experiments.map((e) => (
            <ExperimentCard key={e.id} experiment={e} onAction={handleAction} isLoading={busy} />
          ))}
        </div>
      )}
    </div>
  );
}
