"use client";

/**
 * /interviews (T1305) — Video interview list.
 * 拉 GET /api/video-interviews (按 employer_id / candidate_id 过滤),
 * 渲染 VideoMeetingCard + 可手工新建.
 */
import * as React from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, AlertCircle, Video as VideoIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

import {
  videoInterviewApi,
  type VideoInterview,
} from "@/lib/api-video-interview";
import { VideoMeetingCard } from "@/components/VideoMeetingCard";

interface Props {
  searchParams: { candidate_id?: string; employer_id?: string };
}

export default function InterviewsPage({ searchParams }: Props) {
  const [interviews, setInterviews] = React.useState<VideoInterview[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const out = await videoInterviewApi.list({
        candidate_id: searchParams.candidate_id,
        employer_id: searchParams.employer_id,
      });
      setInterviews(out.data || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [searchParams.candidate_id, searchParams.employer_id]);

  React.useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Link href="/tickets" className="text-sm text-gray-500">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-2xl font-semibold">Video interviews</h1>
        </div>
        <Button onClick={load} variant="outline" size="sm">
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            "Refresh"
          )}
        </Button>
      </div>

      {error && (
        <Card className="mb-4 border-red-200 bg-red-50">
          <CardContent className="p-3 text-red-700">
            <AlertCircle className="mr-1 inline h-4 w-4" /> {error}
          </CardContent>
        </Card>
      )}

      {loading && interviews.length === 0 ? (
        <div className="flex justify-center p-6 text-gray-500">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : interviews.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-center text-gray-500">
            <VideoIcon className="mx-auto mb-2 h-8 w-8 text-gray-400" />
            <p>No video interviews scheduled.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {interviews.map((iv) => (
            <Link
              key={iv.id}
              href={`/interviews/${iv.id}`}
              className="block hover:shadow"
            >
              <VideoMeetingCard interview={iv} />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
