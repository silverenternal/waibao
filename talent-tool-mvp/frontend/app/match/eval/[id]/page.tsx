"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { EvalComparison } from "@/components/match/EvalComparison";
import { StrengthsList } from "@/components/match/StrengthsList";
import { ConcernsList } from "@/components/match/ConcernsList";
import { EvalDiscuss } from "@/components/match/EvalDiscuss";
import { matchEvalApi, type EvalComparison as EvalData } from "@/lib/api-match-eval";

export default function MatchEvalPage() {
  const params = useParams<{ id: string }>();
  const matchId = params?.id ?? "";

  const [data, setData] = React.useState<EvalData | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [comment, setComment] = React.useState("");
  const [posting, setPosting] = React.useState(false);
  const [roomId, setRoomId] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    if (!matchId) return;
    setLoading(true);
    setErr(null);
    try {
      const r = await matchEvalApi.get(matchId);
      setData(r);
      setRoomId(r.discussion_room_id);
    } catch (e: any) {
      setErr(e?.message ?? "加载失败");
    } finally {
      setLoading(false);
    }
  }, [matchId]);

  React.useEffect(() => {
    load();
  }, [load]);

  const handlePost = async () => {
    if (!comment.trim()) return;
    setPosting(true);
    try {
      await matchEvalApi.postComment(matchId, { body: comment });
      setComment("");
      await load();
    } catch (e: any) {
      setErr(e?.message ?? "评论失败");
    } finally {
      setPosting(false);
    }
  };

  return (
    <div className="container mx-auto max-w-5xl p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">互评对照</h1>
          <p className="text-sm text-slate-500 mt-1">
            匹配 ID: <span className="font-mono">{matchId}</span>
          </p>
        </div>
        <Link
          href={`/match/${matchId}/explain`}
          className="inline-flex items-center px-4 py-2 rounded-md border border-slate-300 text-sm text-slate-700 hover:bg-slate-50"
        >
          ← 回到匹配解释
        </Link>
      </div>

      {err && (
        <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
          {err}
        </div>
      )}

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : data ? (
        <>
          <div className="flex items-center justify-between rounded-xl border bg-slate-50 p-4">
            <div className="flex-1">
              <div className="text-xs text-slate-500 mb-1">双方视角一致性</div>
              <div className="flex items-center gap-3">
                <Progress
                  value={Math.round(data.overall_alignment * 100)}
                  className="flex-1 max-w-md"
                />
                <span className="font-mono text-sm text-slate-700">
                  {(data.overall_alignment * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <EvalDiscuss
              matchId={matchId}
              existingRoomId={roomId}
              onDiscussed={(rid) => setRoomId(rid)}
            />
          </div>

          <EvalComparison
            candidateEval={data.candidate_eval}
            employerEval={data.employer_eval}
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-base">双方一致认可的优势</CardTitle>
                <Badge className="bg-emerald-100 text-emerald-800">
                  aligned strengths
                </Badge>
              </CardHeader>
              <CardContent>
                <StrengthsList items={data.aligned_strengths} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-base">双方一致关注的顾虑</CardTitle>
                <Badge className="bg-rose-100 text-rose-800">
                  aligned concerns
                </Badge>
              </CardHeader>
              <CardContent>
                <ConcernsList items={data.aligned_concerns} />
              </CardContent>
            </Card>
          </div>

          {data.divergent_dimensions.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">分歧维度</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  {data.divergent_dimensions.map((d) => (
                    <li key={d.dimension} className="flex items-center gap-3">
                      <span className="font-medium text-slate-700 w-24">
                        {d.dimension}
                      </span>
                      <span className="font-mono text-slate-600">
                        候选人 {d.candidate} / 雇主 {d.employer}
                      </span>
                      <Badge variant="outline">gap {d.gap.toFixed(1)}</Badge>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">讨论评论</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <ul className="space-y-2 max-h-64 overflow-y-auto">
                {data.comments.length === 0 && (
                  <li className="text-sm text-slate-400 italic">
                    暂无评论
                  </li>
                )}
                {data.comments.map((c) => (
                  <li
                    key={c.id}
                    className="rounded-md border bg-white p-3 text-sm"
                  >
                    <div className="text-xs text-slate-500 mb-1">
                      {c.author_role} ·{" "}
                      {new Date(c.created_at).toLocaleString()}
                      {c.dimension ? ` · 维度:${c.dimension}` : ""}
                    </div>
                    <div className="text-slate-800 whitespace-pre-wrap">
                      {c.body}
                    </div>
                  </li>
                ))}
              </ul>
              <div className="space-y-2">
                <Textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="输入评论…"
                  rows={3}
                />
                <div className="flex justify-end">
                  <Button onClick={handlePost} disabled={posting || !comment.trim()}>
                    {posting ? "发布中…" : "发布评论"}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}