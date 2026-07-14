"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MetricTile } from "@/components/shared/metric-tile";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { ChannelRoiChart } from "@/components/charts/channel-roi-chart";
import {
  DollarSign,
  Trophy,
  BarChart3,
  TrendingUp,
} from "lucide-react";
import type {
  ChannelAttributionResponse,
  ChannelRoiReport,
} from "@/lib/types";

const MODELS = [
  { value: "first_touch", label: "First-touch" },
  { value: "last_touch", label: "Last-touch" },
  { value: "multi_touch", label: "Multi-touch (linear)" },
] as const;

export default function ChannelsPage() {
  const [days, setDays] = useState(30);
  const [model, setModel] = useState<(typeof MODELS)[number]["value"]>(
    "last_touch",
  );
  const [channels, setChannels] = useState<ChannelAttributionResponse | null>(
    null,
  );
  const [roiReport, setRoiReport] = useState<ChannelRoiReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [ch, roi] = await Promise.all([
          apiClient.analytics.channels(days, model),
          apiClient.analytics.channelRoi(days).catch(() => null),
        ]);
        if (!cancelled) {
          setChannels(ch);
          setRoiReport(roi);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("[channels] load failed", err);
          setChannels(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [days, model]);

  const totalCost =
    channels?.channels.reduce((s, c) => s + c.cost_cents, 0) ?? 0;
  const totalRevenue =
    channels?.channels.reduce((s, c) => s + c.revenue_cents, 0) ?? 0;
  const totalHires =
    channels?.channels.reduce((s, c) => s + c.hires, 0) ?? 0;

  return (
    <ErrorBoundary>(<div className="space-y-6 p-6">
        <header className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Channel ROI
            </h1>
            <p className="text-sm text-muted-foreground">
              First-touch / last-touch / multi-touch attribution.
            </p>
          </div>
          <div className="flex gap-3 items-end">
            <div className="space-y-1">
              <Label className="text-xs">Period</Label>
              <Select
                value={String(days)}
                onValueChange={(v) => setDays(Number(v))}
              >
                <SelectTrigger className="w-[150px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="7">7 days</SelectItem>
                  <SelectItem value="30">30 days</SelectItem>
                  <SelectItem value="90">90 days</SelectItem>
                  <SelectItem value="180">6 months</SelectItem>
                  <SelectItem value="365">12 months</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Model</Label>
              <Select
                value={model}
                onValueChange={(v) =>
                  setModel(v as (typeof MODELS)[number]["value"])
                }
              >
                <SelectTrigger className="w-[200px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODELS.map((m) => (
                    <SelectItem key={m.value} value={m.value}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </header>
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <MetricTile
            label="Total cost"
            value={`¥${(totalCost / 100).toFixed(0)}`}
            icon={<DollarSign className="h-4 w-4" />}
            loading={loading}
          />
          <MetricTile
            label="Total revenue"
            value={`¥${(totalRevenue / 100).toFixed(0)}`}
            icon={<TrendingUp className="h-4 w-4" />}
            loading={loading}
          />
          <MetricTile
            label="Total hires"
            value={totalHires}
            icon={<Trophy className="h-4 w-4" />}
            loading={loading}
          />
          <MetricTile
            label="Best channel"
            value={channels?.best_channel ?? "—"}
            icon={<BarChart3 className="h-4 w-4" />}
            loading={loading}
          />
        </section>
        <Card>
          <CardHeader>
            <CardTitle>ROI by channel</CardTitle>
          </CardHeader>
          <CardContent>
            {loading || !channels ? (
              <Skeleton className="h-[260px] w-full" />
            ) : (
              <ChannelRoiChart channels={channels.channels} />
            )}
          </CardContent>
        </Card>
        <Tabs defaultValue="channels">
          <TabsList>
            <TabsTrigger value="channels">Channel table</TabsTrigger>
            <TabsTrigger value="models">All models</TabsTrigger>
          </TabsList>
          <TabsContent value="channels">
            <Card>
              <CardContent className="pt-6">
                {loading || !channels ? (
                  <Skeleton className="h-[200px] w-full" />
                ) : (
                  <ChannelTable channels={channels.channels} />
                )}
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="models">
            <Card>
              <CardContent className="pt-6">
                {!roiReport ? (
                  <p className="text-sm text-muted-foreground py-4 text-center">
                    ROI comparison is admin-only; sign in as admin to view all
                    models.
                  </p>
                ) : (
                  <AllModelsView report={roiReport} />
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>)</ErrorBoundary>
  );
}

function ChannelTable({
  channels,
}: {
  channels: NonNullable<ChannelAttributionResponse["channels"]>;
}) {
  if (channels.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4 text-center">
        No channel data in this period.
      </p>
    );
  }
  return (
    <div className="rounded-md border overflow-x-auto">
      <table className="w-full text-sm min-w-[640px]">
        <thead>
          <tr className="border-b bg-muted text-left">
            <th className="px-3 py-2 font-medium">Channel</th>
            <th className="px-3 py-2 font-medium text-right">Candidates</th>
            <th className="px-3 py-2 font-medium text-right">Hires</th>
            <th className="px-3 py-2 font-medium text-right">Cost</th>
            <th className="px-3 py-2 font-medium text-right">Revenue</th>
            <th className="px-3 py-2 font-medium text-right">ROI</th>
            <th className="px-3 py-2 font-medium text-right">Cost / hire</th>
          </tr>
        </thead>
        <tbody>
          {channels.map((c) => (
            <tr key={c.channel} className="border-b last:border-0">
              <td className="px-3 py-2 font-medium">{c.channel}</td>
              <td className="px-3 py-2 text-right">{c.candidates}</td>
              <td className="px-3 py-2 text-right">{c.hires}</td>
              <td className="px-3 py-2 text-right">
                ¥{(c.cost_cents / 100).toFixed(0)}
              </td>
              <td className="px-3 py-2 text-right">
                ¥{(c.revenue_cents / 100).toFixed(0)}
              </td>
              <td
                className={`px-3 py-2 text-right font-medium ${
                  c.roi >= 1
                    ? "text-emerald-600"
                    : c.roi >= 0
                      ? "text-blue-600"
                      : "text-red-600"
                }`}
              >
                {c.roi.toFixed(2)}
              </td>
              <td className="px-3 py-2 text-right">
                {c.cost_per_hire > 0 ? `¥${(c.cost_per_hire / 100).toFixed(0)}` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AllModelsView({ report }: { report: ChannelRoiReport }) {
  const models = Object.keys(report.by_model || {});
  if (models.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4 text-center">
        No model data.
      </p>
    );
  }
  return (
    <div className="space-y-4">
      {models.map((model) => {
        const items = report.by_model[model] ?? [];
        return (
          <div key={model}>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-sm font-medium capitalize">
                {model.replace("_", "-")}
              </span>
              <span className="text-xs text-muted-foreground">
                best: {report.best_channel_by_model?.[model] ?? "—"}
              </span>
            </div>
            <ChannelTable channels={items} />
          </div>
        );
      })}
    </div>
  );
}