"use client";

/**
 * VideoMeetingCard — 渲染一场视频会议的链接卡 (T1305)
 * 支持 zoom / tencent_meeting / mock.
 */
import * as React from "react";
import { Video, Copy, ExternalLink } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { VideoInterview } from "@/lib/api-video-interview";

interface Props {
  interview: VideoInterview;
  showRecordingLink?: boolean;
  onCopy?: (text: string) => void;
}

export function VideoMeetingCard({
  interview,
  showRecordingLink = true,
  onCopy,
}: Props) {
  const [recording, setRecording] = React.useState<{
    play_url?: string | null;
    status: string;
    duration_seconds: number;
  } | null>(null);

  const fetchRecording = React.useCallback(async () => {
    try {
      const out = await fetch(
        `/api/video-interviews/${interview.id}/recording`,
      );
      if (!out.ok) return;
      const body = await out.json();
      if (body?.data) setRecording(body.data);
    } catch {
      // ignore
    }
  }, [interview.id]);

  React.useEffect(() => {
    if (interview.status === "ended" || interview.status === "started") {
      fetchRecording();
    }
  }, [interview.status, fetchRecording]);

  const copy = (text: string) => {
    if (navigator?.clipboard) {
      navigator.clipboard.writeText(text).catch(() => {});
    }
    onCopy?.(text);
  };

  const providerLabel =
    interview.provider === "zoom"
      ? "Zoom"
      : interview.provider === "tencent_meeting"
      ? "Tencent Meeting"
      : "Mock";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Video className="h-5 w-5" />
          {interview.topic || "Video interview"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <Row label="Provider">
          <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs">
            {providerLabel}
          </span>
        </Row>
        <Row label="Status">
          <span
            className={
              interview.status === "started"
                ? "text-blue-600"
                : interview.status === "ended"
                ? "text-gray-600"
                : interview.status === "canceled"
                ? "text-red-600"
                : "text-emerald-600"
            }
          >
            {interview.status}
          </span>
        </Row>
        <Row label="Start">
          {new Date(interview.start_time).toLocaleString()}
        </Row>
        <Row label="Duration">{interview.duration_min} min</Row>

        <div className="mt-3 space-y-2">
          <ActionRow
            label="Candidate link"
            href={interview.join_url}
          />
          {interview.host_url && (
            <ActionRow
              label="Host link"
              href={interview.host_url}
              onCopy={() => copy(interview.host_url || "")}
            />
          )}
        </div>

        {showRecordingLink && recording?.play_url && (
          <div className="mt-3 rounded border bg-purple-50 p-2 text-purple-900">
            <p className="font-medium">Recording available</p>
            <a
              href={recording.play_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-purple-700 hover:underline"
            >
              Play <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 text-gray-500">{label}</span>
      <span>{children}</span>
    </div>
  );
}

function ActionRow({
  label,
  href,
  onCopy,
}: {
  label: string;
  href: string;
  onCopy?: () => void;
}) {
  return (
    <div className="flex items-center gap-2 rounded border px-2 py-1.5">
      <span className="text-xs text-gray-500">{label}</span>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="flex-1 truncate text-blue-600 underline"
      >
        {href}
      </a>
      {onCopy && (
        <button
          type="button"
          onClick={onCopy}
          className="rounded p-1 hover:bg-slate-100"
          title="Copy"
        >
          <Copy className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
