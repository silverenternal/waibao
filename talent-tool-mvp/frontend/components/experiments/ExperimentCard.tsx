/**
 * ExperimentCard (T805): 单个实验的 summary 卡片.
 */
"use client";

import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ExperimentRow, ExperimentStatus } from "@/lib/api-ab";

interface ExperimentCardProps {
  experiment: ExperimentRow;
  onAction: (action: "start" | "stop", experiment: ExperimentRow) => void;
  isLoading?: boolean;
}

function statusVariant(status: ExperimentStatus): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "running":
      return "default";
    case "completed":
      return "secondary";
    case "stopped":
      return "destructive";
    case "draft":
    default:
      return "outline";
  }
}

export function ExperimentCard({ experiment, onAction, isLoading }: ExperimentCardProps) {
  const variantSummary = experiment.variants.map((v) => `${v.name} (${v.weight})`).join(" / ");
  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="space-y-1">
          <Link
            href={`/mothership/admin/experiments/${experiment.id}`}
            className="hover:underline"
          >
            <CardTitle className="text-base">{experiment.name}</CardTitle>
          </Link>
          <p className="text-xs text-muted-foreground line-clamp-2">
            {experiment.description || "No description"}
          </p>
        </div>
        <Badge variant={statusVariant(experiment.status)}>{experiment.status}</Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="text-xs space-y-1">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Primary metric</span>
            <span className="font-mono">{experiment.primary_metric}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Variants</span>
            <span className="font-mono truncate max-w-[60%]" title={variantSummary}>
              {experiment.variants.length}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Started</span>
            <span>{experiment.started_at ? new Date(experiment.started_at).toLocaleDateString() : "—"}</span>
          </div>
        </div>

        <div className="flex gap-2 pt-1">
          {(experiment.status === "draft" || experiment.status === "stopped") && (
            <Button
              size="sm"
              variant="default"
              disabled={isLoading}
              onClick={() => onAction("start", experiment)}
            >
              Start
            </Button>
          )}
          {experiment.status === "running" && (
            <Button
              size="sm"
              variant="destructive"
              disabled={isLoading}
              onClick={() => onAction("stop", experiment)}
            >
              Stop
            </Button>
          )}
          <Link href={`/mothership/admin/experiments/${experiment.id}`}>
            <Button size="sm" variant="outline">Details</Button>
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
