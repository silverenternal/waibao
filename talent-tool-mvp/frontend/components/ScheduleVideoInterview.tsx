"use client";

/**
 * ScheduleVideoInterview (T1305)
 * - 表单: candidate / host / 时间 / 时长 / 提供商 (zoom / tencent_meeting)
 * - 提交后调用 /api/video-interviews
 * - 成功 → 展示 join_url + host_url
 */
import * as React from "react";
import { useRouter } from "next/navigation";
import { Video, Loader2, Check, ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  videoInterviewApi,
  type VideoInterview,
} from "@/lib/api-video-interview";

interface Props {
  candidateId: string;
  employerId: string;
  hostEmail: string;
  onScheduled?: (interview: VideoInterview) => void;
}

export function ScheduleVideoInterview({
  candidateId,
  employerId,
  hostEmail,
  onScheduled,
}: Props) {
  const router = useRouter();
  const [topic, setTopic] = React.useState("Interview");
  const [startTime, setStartTime] = React.useState(() => {
    const d = new Date(Date.now() + 3600_000);
    return d.toISOString().slice(0, 16);
  });
  const [durationMin, setDurationMin] = React.useState(45);
  const [provider, setProvider] = React.useState<"zoom" | "tencent_meeting" | "mock">(
    "mock",
  );
  const [guestEmail, setGuestEmail] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [interview, setInterview] = React.useState<VideoInterview | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const participantEmails = [hostEmail];
      if (guestEmail.trim()) participantEmails.push(guestEmail.trim());
      const out = await videoInterviewApi.schedule({
        candidate_id: candidateId,
        employer_id: employerId,
        host_email: hostEmail,
        topic: topic.trim() || "Interview",
        start_time: new Date(startTime).toISOString(),
        duration_min: durationMin,
        preferred_provider: provider,
        participant_emails: participantEmails,
      });
      setInterview(out.data);
      onScheduled?.(out.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Schedule failed");
    } finally {
      setSubmitting(false);
    }
  };

  if (interview) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-emerald-700">
            <Check className="h-5 w-5" />
            Interview scheduled
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-gray-600">
            Provider: <code className="rounded bg-slate-100 px-1 py-0.5">{interview.provider}</code>
          </p>
          <p className="text-sm">
            <span className="font-medium">Topic:</span> {interview.topic}
          </p>
          <p className="text-sm">
            <span className="font-medium">Start:</span>{" "}
            {new Date(interview.start_time).toLocaleString()}
          </p>
          <div className="flex flex-col gap-2">
            <a
              href={interview.join_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-blue-600 hover:underline"
            >
              <Video className="h-4 w-4" /> Candidate join URL
              <ExternalLink className="h-3 w-3" />
            </a>
            {interview.host_url && (
              <a
                href={interview.host_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-blue-600 hover:underline"
              >
                <Video className="h-4 w-4" /> Host join URL
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
          <Button variant="outline" onClick={() => setInterview(null)}>
            Schedule another
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Video className="h-5 w-5" /> Schedule video interview
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Topic">
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              className="w-full rounded border px-3 py-2 text-sm"
              required
            />
          </Field>
          <Field label="Start time">
            <input
              type="datetime-local"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              className="w-full rounded border px-3 py-2 text-sm"
              required
            />
          </Field>
          <Field label="Duration (minutes)">
            <input
              type="number"
              value={durationMin}
              min={5}
              max={480}
              onChange={(e) => setDurationMin(parseInt(e.target.value, 10) || 30)}
              className="w-full rounded border px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Provider">
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value as typeof provider)}
              className="w-full rounded border px-3 py-2 text-sm"
            >
              <option value="mock">Mock (no real call)</option>
              <option value="zoom">Zoom (server-to-server OAuth)</option>
              <option value="tencent_meeting">Tencent Meeting (CN)</option>
            </select>
          </Field>
          <Field label="Candidate email (optional)">
            <input
              type="email"
              value={guestEmail}
              onChange={(e) => setGuestEmail(e.target.value)}
              className="w-full rounded border px-3 py-2 text-sm"
              placeholder="candidate@company.com"
            />
          </Field>

          {error && (
            <p className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>
          )}

          <Button type="submit" disabled={submitting}>
            {submitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Scheduling…
              </>
            ) : (
              "Schedule"
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-gray-700">{label}</span>
      {children}
    </label>
  );
}
