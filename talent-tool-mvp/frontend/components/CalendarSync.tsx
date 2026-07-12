"use client";

/**
 * CalendarSync (T1305)
 * 显示 Google / Outlook 双向同步状态;允许手动触发同步.
 */
import * as React from "react";
import { Calendar, Check, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export type CalendarProvider = "google" | "outlook";

interface Props {
  candidateId?: string;
  employerId: string;
  videoInterviewId: string;
  syncedTo: CalendarProvider[];
  accessTokens: Partial<Record<CalendarProvider, string>>;
}

export function CalendarSync({
  candidateId,
  employerId,
  videoInterviewId,
  syncedTo,
  accessTokens,
}: Props) {
  const [synced, setSynced] = React.useState<CalendarProvider[]>(syncedTo);
  const [busy, setBusy] = React.useState<CalendarProvider | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const sync = async (provider: CalendarProvider) => {
    const token = accessTokens[provider];
    if (!token) {
      setError(`${provider} access token missing`);
      return;
    }
    setBusy(provider);
    try {
      const res = await fetch(
        `/api/video-interviews/${videoInterviewId}/calendar/sync`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider,
            access_token: token,
            candidate_id: candidateId,
            employer_id: employerId,
          }),
        },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "sync failed");
      }
      if (!synced.includes(provider)) {
        setSynced([...synced, provider]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "sync error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Calendar className="h-5 w-5" /> Calendar sync
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ProviderRow
          name="google"
          label="Google Calendar"
          synced={synced.includes("google")}
          busy={busy === "google"}
          hasToken={Boolean(accessTokens.google)}
          onSync={() => sync("google")}
        />
        <ProviderRow
          name="outlook"
          label="Microsoft Outlook"
          synced={synced.includes("outlook")}
          busy={busy === "outlook"}
          hasToken={Boolean(accessTokens.outlook)}
          onSync={() => sync("outlook")}
        />
        {error && (
          <p className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>
        )}
      </CardContent>
    </Card>
  );
}

function ProviderRow({
  label,
  synced,
  busy,
  hasToken,
  onSync,
}: {
  name: CalendarProvider;
  label: string;
  synced: boolean;
  busy: boolean;
  hasToken: boolean;
  onSync: () => void;
}) {
  return (
    <div className="flex items-center justify-between rounded border p-2">
      <div className="flex items-center gap-2 text-sm">
        {synced ? (
          <Check className="h-4 w-4 text-emerald-600" />
        ) : (
          <X className="h-4 w-4 text-gray-400" />
        )}
        <span>{label}</span>
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={onSync}
        disabled={busy || !hasToken || synced}
      >
        {busy ? "Syncing…" : synced ? "Synced" : "Sync now"}
      </Button>
    </div>
  );
}
