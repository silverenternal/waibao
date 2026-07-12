"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Bell, Plus, Trash2, Pause, Play } from "lucide-react";
import { SubscriptionForm } from "@/components/SubscriptionForm";
import { SubscriptionMatchList } from "@/components/SubscriptionMatch";
import type { Subscription, JobMatch } from "@/lib/types";

export default function SubscriptionsPage() {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [matches, setMatches] = useState<Record<string, JobMatch[]>>({});
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { subscriptions } = await apiClient.subscriptions.list();
      setSubs(subscriptions);
      // 顺手拉每个订阅的匹配预览
      const entries = await Promise.all(
        subscriptions.map(async (s) => {
          try {
            const m = await apiClient.subscriptions.matches(s.id, 5);
            return [s.id, m.matches] as const;
          } catch {
            return [s.id, []] as const;
          }
        }),
      );
      setMatches(Object.fromEntries(entries));
    } catch (err) {
      console.error("[subscriptions] load failed", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onCreate = async (body: {
    name: string;
    criteria: Subscription["criteria"];
    channels: string[];
  }) => {
    setSubmitting(true);
    try {
      await apiClient.subscriptions.create(body);
      setOpen(false);
      await load();
    } finally {
      setSubmitting(false);
    }
  };

  const onToggle = async (s: Subscription) => {
    await apiClient.subscriptions.update(s.id, { enabled: !s.enabled });
    await load();
  };

  const onDelete = async (s: Subscription) => {
    if (!confirm(`Delete subscription "${s.name}"?`)) return;
    await apiClient.subscriptions.delete(s.id);
    await load();
  };

  return (
    <div className="space-y-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Bell className="h-5 w-5 text-blue-600" />
            Job subscriptions
          </h1>
          <p className="text-sm text-muted-foreground">
            We&apos;ll push matching jobs to your chosen channels.
          </p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger>
            <Button>
              <Plus className="h-4 w-4 mr-1" /> New subscription
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>New subscription</DialogTitle>
              <DialogDescription>
                Tell us what you&apos;re looking for. We&apos;ll notify you when a
                match appears.
              </DialogDescription>
            </DialogHeader>
            <SubscriptionForm
              onSubmit={onCreate}
              submitting={submitting}
              onCancel={() => setOpen(false)}
            />
          </DialogContent>
        </Dialog>
      </header>

      {loading ? (
        <Skeleton className="h-[200px] w-full" />
      ) : subs.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center">
            <Bell className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">
              You don&apos;t have any subscriptions yet. Create one to start
              receiving matching jobs.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {subs.map((s) => (
            <SubscriptionCard
              key={s.id}
              sub={s}
              matches={matches[s.id] ?? []}
              onToggle={() => onToggle(s)}
              onDelete={() => onDelete(s)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SubscriptionCard({
  sub,
  matches,
  onToggle,
  onDelete,
}: {
  sub: Subscription;
  matches: JobMatch[];
  onToggle: () => void;
  onDelete: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              {sub.name}
              {!sub.enabled && (
                <Badge variant="secondary" className="text-[10px]">
                  paused
                </Badge>
              )}
            </CardTitle>
            <div className="text-xs text-muted-foreground mt-1 flex flex-wrap gap-2">
              {sub.criteria.role && <span>role: {sub.criteria.role}</span>}
              {sub.criteria.city && <span>city: {sub.criteria.city}</span>}
              {sub.criteria.salary_min ? (
                <span>
                  min {sub.criteria.currency} {sub.criteria.salary_min}
                </span>
              ) : null}
              {sub.criteria.seniority && (
                <span>seniority: {sub.criteria.seniority}</span>
              )}
            </div>
            {(sub.criteria.skills?.length ?? 0) > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {(sub.criteria.skills ?? []).map((sk) => (
                  <Badge key={sk} variant="outline" className="text-[10px]">
                    {sk}
                  </Badge>
                ))}
              </div>
            )}
          </div>
          <div className="flex gap-1">
            <Button size="icon" variant="ghost" onClick={onToggle} aria-label="toggle">
              {sub.enabled ? (
                <Pause className="h-4 w-4" />
              ) : (
                <Play className="h-4 w-4" />
              )}
            </Button>
            <Button
              size="icon"
              variant="ghost"
              onClick={onDelete}
              aria-label="delete"
              className="text-red-600"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <SubscriptionMatchList
          matches={matches}
          subscriptionName={sub.name}
        />
      </CardContent>
    </Card>
  );
}