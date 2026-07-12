"use client";

/**
 * VideoResumePlayer — T2203.
 *
 * 播放视频简历 + 叠加 AI 评分(5 维度)+ 时间戳标注点击跳转.
 */

import { useRef, useState } from "react";

export interface VideoResumeAnalysis {
  source_url: string;
  frames_analyzed: number;
  scores: {
    communication: number;
    clarity: number;
    professionalism: number;
    confidence: number;
    warmth: number;
    overall: number;
  };
  non_verbal?: {
    expression?: string;
    eye_contact?: string;
    body_language?: string;
    notes?: string[];
  };
  strengths?: string[];
  suggestions?: string[];
  tags?: string[];
  analyzed_at?: string;
}

interface Props {
  videoUrl: string;
  analysis?: VideoResumeAnalysis | null;
  className?: string;
}

const DIMENSION_LABELS: Record<string, string> = {
  communication: "沟通能力",
  clarity: "表达清晰度",
  professionalism: "专业度",
  confidence: "自信度",
  warmth: "亲和力",
};

const DIMENSION_KEYS: Array<keyof VideoResumeAnalysis["scores"]> = [
  "communication",
  "clarity",
  "professionalism",
  "confidence",
  "warmth",
];

function scoreColor(score: number): string {
  if (score >= 0.8) return "text-emerald-600 bg-emerald-50 border-emerald-200";
  if (score >= 0.6) return "text-sky-600 bg-sky-50 border-sky-200";
  if (score >= 0.4) return "text-amber-600 bg-amber-50 border-amber-200";
  return "text-rose-600 bg-rose-50 border-rose-200";
}

export default function VideoResumePlayer({ videoUrl, analysis, className = "" }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [currentTime, setCurrentTime] = useState(0);

  const seekTo = (sec: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = sec;
      videoRef.current.play().catch(() => undefined);
    }
  };

  // 推导时间戳:基于 5 秒/帧均匀分布,标注 strengths 来自的相对位置
  const timestampHints = (() => {
    if (!analysis?.strengths?.length || !videoRef.current) return [];
    const duration = videoRef.current.duration || 60;
    const stride = Math.max(1, Math.floor(duration / analysis.strengths.length));
    return analysis.strengths.map((s, i) => ({
      timestamp: i * stride,
      text: s,
    }));
  })();

  return (
    <div className={`grid gap-4 md:grid-cols-3 ${className}`}>
      <div className="md:col-span-2">
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-black">
          <video
            ref={videoRef}
            src={videoUrl}
            controls
            className="aspect-video w-full"
            onTimeUpdate={(e) => setCurrentTime((e.target as HTMLVideoElement).currentTime)}
            playsInline
          />
        </div>

        {timestampHints.length > 0 && (
          <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              时间戳亮点
            </div>
            <div className="flex flex-col gap-1">
              {timestampHints.map((h, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => seekTo(h.timestamp)}
                  className="flex items-start gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-slate-50"
                >
                  <span className="mt-0.5 inline-flex shrink-0 items-center rounded bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-white">
                    {h.timestamp}s
                  </span>
                  <span className="text-slate-700">{h.text}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {analysis?.non_verbal && (
          <div className="mt-3 grid gap-2 rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-700 sm:grid-cols-3">
            <div>
              <div className="text-xs font-medium uppercase text-slate-500">表情</div>
              <div>{analysis.non_verbal.expression || "—"}</div>
            </div>
            <div>
              <div className="text-xs font-medium uppercase text-slate-500">眼神接触</div>
              <div>{analysis.non_verbal.eye_contact || "—"}</div>
            </div>
            <div>
              <div className="text-xs font-medium uppercase text-slate-500">肢体语言</div>
              <div>{analysis.non_verbal.body_language || "—"}</div>
            </div>
          </div>
        )}
      </div>

      <aside className="space-y-3">
        {analysis ? (
          <>
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                AI 综合评分
              </div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-3xl font-bold text-slate-900">
                  {Math.round(analysis.scores.overall * 100)}
                </span>
                <span className="text-sm text-slate-500">/ 100</span>
              </div>
              <div className="mt-1 text-xs text-slate-400">
                基于 {analysis.frames_analyzed} 帧 ·{" "}
                {analysis.analyzed_at
                  ? new Date(analysis.analyzed_at).toLocaleString()
                  : "刚刚"}
              </div>
            </div>

            <div className="space-y-2 rounded-2xl border border-slate-200 bg-white p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                5 维度评分
              </div>
              {DIMENSION_KEYS.map((k) => {
                const v = analysis.scores[k];
                return (
                  <div key={k} className="flex items-center gap-2">
                    <div className="w-20 shrink-0 text-xs text-slate-600">
                      {DIMENSION_LABELS[k]}
                    </div>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-slate-900"
                        style={{ width: `${Math.round(v * 100)}%` }}
                      />
                    </div>
                    <span
                      className={`inline-flex w-12 justify-center rounded-md border px-1.5 py-0.5 text-xs font-medium ${scoreColor(v)}`}
                    >
                      {Math.round(v * 100)}
                    </span>
                  </div>
                );
              })}
            </div>

            {analysis.strengths && analysis.strengths.length > 0 && (
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
                  优点
                </div>
                <ul className="mt-1 space-y-1 text-sm text-emerald-900">
                  {analysis.strengths.map((s, i) => (
                    <li key={i}>• {s}</li>
                  ))}
                </ul>
              </div>
            )}

            {analysis.suggestions && analysis.suggestions.length > 0 && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-amber-700">
                  建议
                </div>
                <ul className="mt-1 space-y-1 text-sm text-amber-900">
                  {analysis.suggestions.map((s, i) => (
                    <li key={i}>• {s}</li>
                  ))}
                </ul>
              </div>
            )}

            {analysis.tags && analysis.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {analysis.tags.map((t, i) => (
                  <span
                    key={i}
                    className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
                  >
                    #{t}
                  </span>
                ))}
              </div>
            )}
          </>
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
            暂无 AI 评分,提交视频后约 30 秒生成。
          </div>
        )}
        <div className="text-xs text-slate-400">当前播放位置: {currentTime.toFixed(1)}s</div>
      </aside>
    </div>
  );
}