"use client";

/**
 * /interviews/[id] (T1305) — 单场视频面试详情.
 * - 拉取 interview 详情 + recording
 * - 提供取消按钮
 * - 日历同步 (Google / Outlook)
 */
import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Trash2, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { VideoMeetingCard } from "@/components/VideoMeetingCard";
import { CalendarSync } from "@/components/CalendarSync";

import {
  videoInterviewApi,
  type VideoInterview,
} from "@/lib/api-video-interview";

export default function InterviewDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const [interview, setInterview] = React.useState<VideoInterview | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [canceling, setCanceling] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      const list = await videoInterviewApi.list({});
      const found = (list.data || []).find((iv) => iv.id === id);
      if (!found) {
        setError("Interview not found");
      } else {
        setInterview(found);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }, [id]);

  React.useEffect(() => {
    load();
  }, [load]);

  const onCancel = async () => {
    if (!interview) return;
    if (!confirm("Cancel this interview?")) return;
    setCanceling(true);
    try {
      await videoInterviewApi.cancel(interview.id);
      setInterview({ ...interview, status: "canceled" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancel failed");
    } finally {
      setCanceling(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center p-12 text-gray-400">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  if (!interview) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <Link href="/interviews" className="text-sm text-blue-600 hover:underline">
          <ArrowLeft className="mr-1 inline h-4 w-4" /> Back
        </Link>
        <div className="mt-6 rounded border bg-red-50 p-6 text-red-700">
          {error || "Not found"}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6">
      <div className="flex items-center justify-between">
        <Link
          href="/interviews"
          className="inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4" /> All interviews
        </Link>
        {interview.status !== "canceled" && interview.status !== "ended" && (
          <Button variant="destructive" onClick={onCancel} disabled={canceling}>
            {canceling ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="mr-2 h-4 w-4" />
            )}
            Cancel
          </Button>
        )}
      </div>

      <VideoMeetingCard interview={interview} />

      <CalendarSync
        employerId={interview.id /* fallback if employer not loaded */}
        videoInterviewId={interview.id}
        syncedTo={[]}
        accessTokens={{}}
      />
    </div>
  );
}
