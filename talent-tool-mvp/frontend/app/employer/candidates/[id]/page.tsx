"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * /employer/candidates/[id] — 候选人详情页 (T2203).
 *
 * 含视频简历区域: 显示已上传视频 + AI 5 维度评分.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import VideoResumePlayer, { type VideoResumeAnalysis } from "@/components/VideoResumePlayer";

interface CandidateVideoResume {
  id: string;
  video_url: string;
  duration_sec: number;
  created_at: string;
  analysis?: VideoResumeAnalysis | null;
  status: string;
}

interface Candidate {
  id: string;
  name: string;
  headline?: string;
  email?: string;
  skills?: string[];
  soft_skills?: Record<string, number>;
  video_resumes?: CandidateVideoResume[];
}

const DIMENSION_LABELS: Record<string, string> = {
  communication: "沟通能力",
  clarity: "表达清晰度",
  professionalism: "专业度",
  confidence: "自信度",
  warmth: "亲和力",
};

export default function CandidateDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    const token = localStorage.getItem("sb_token") || "";
    fetch(`/api/candidates/${id}`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((data) => {
        if (alive) {
          setCandidate(data.candidate || data);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (alive) {
          setError(typeof e === "string" ? e : "加载失败");
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [id]);

  if (loading) return <div className="p-6 text-sm text-slate-500">加载中…</div>;
  if (error) return <div className="p-6 text-sm text-rose-600">{error}</div>;
  if (!candidate) return <div className="p-6 text-sm text-slate-500">未找到候选人</div>;

  const videoResume = candidate.video_resumes?.[0];
  const softSkills = candidate.soft_skills || {};

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-6xl space-y-6 p-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-bold text-slate-900">{candidate.name}</h1>
          {candidate.headline && (
            <p className="text-sm text-slate-500">{candidate.headline}</p>
          )}
        </header>
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h2 className="mb-3 text-lg font-semibold text-slate-900">技能概览</h2>
          <div className="flex flex-wrap gap-2">
            {(candidate.skills || []).map((s, i) => (
              <span
                key={i}
                className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
              >
                {s}
              </span>
            ))}
            {!candidate.skills?.length && (
              <span className="text-sm text-slate-400">暂无技能数据</span>
            )}
          </div>
        </section>
        {Object.keys(softSkills).length > 0 && (
          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <h2 className="mb-3 text-lg font-semibold text-slate-900">软技能评分</h2>
            <div className="space-y-2">
              {Object.entries(DIMENSION_LABELS).map(([k, label]) => {
                const v = softSkills[k] || 0;
                return (
                  <div key={k} className="flex items-center gap-2">
                    <div className="w-24 text-xs text-slate-600">{label}</div>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-slate-900"
                        style={{ width: `${Math.round(v * 100)}%` }}
                      />
                    </div>
                    <span className="w-10 text-right text-xs text-slate-700">
                      {Math.round(v * 100)}
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="mt-2 text-xs text-slate-400">
              综合文本简历 (85%) + 视频简历 (15%) 加权平均
            </div>
          </section>
        )}
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h2 className="mb-3 text-lg font-semibold text-slate-900">视频简历</h2>
          {videoResume ? (
            <VideoResumePlayer
              videoUrl={videoResume.video_url}
              analysis={videoResume.analysis}
            />
          ) : (
            <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
              候选人尚未提交视频简历
            </div>
          )}
        </section>
      </div>)</ErrorBoundary>
  );
}