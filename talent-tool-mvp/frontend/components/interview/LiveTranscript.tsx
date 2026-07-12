"use client";

/**
 * LiveTranscript — T2202.
 *
 * Renders the rolling transcript for an in-progress interview.
 * Auto-scrolls on new items; highlights follow-up questions.
 */

import { useEffect, useRef } from "react";

export interface TranscriptItem {
  question: {
    id: string;
    stage: string;
    stage_label?: string;
    title: string;
    prompt: string;
    is_follow_up?: boolean;
  };
  answer?: {
    question_id: string;
    transcript: string;
    overall: number;
    band: string;
    feedback: string;
    strengths: string[];
    improvements: string[];
    dimensions: Record<string, number>;
  };
}

const BAND_COLOR: Record<string, string> = {
  weak: "bg-rose-100 text-rose-700",
  fair: "bg-amber-100 text-amber-700",
  good: "bg-sky-100 text-sky-700",
  excellent: "bg-emerald-100 text-emerald-700",
};

interface Props {
  items: TranscriptItem[];
  currentQuestionId?: string;
}

export default function LiveTranscript({ items, currentQuestionId }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [items.length]);

  return (
    <div
      ref={ref}
      className="h-96 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-3"
      data-testid="live-transcript"
    >
      {items.length === 0 && (
        <div className="text-slate-400 text-center py-16 text-sm">
          还没有内容,开始回答问题后会在这里显示
        </div>
      )}
      {items.map((it, idx) => {
        const isCurrent = it.question.id === currentQuestionId;
        return (
          <div
            key={it.question.id + "_" + idx}
            className={`rounded-xl border p-3 ${
              isCurrent
                ? "bg-sky-50 border-sky-300"
                : "bg-white border-slate-200"
            }`}
            data-testid={`transcript-item-${idx}`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">
                {it.question.stage_label || it.question.stage}
              </span>
              {it.question.is_follow_up && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">
                  追问
                </span>
              )}
              <span className="font-medium text-sm text-slate-800">
                {it.question.title}
              </span>
            </div>
            <p className="text-sm text-slate-600 mb-2">{it.question.prompt}</p>
            {it.answer && (
              <div className="mt-2 space-y-2">
                <div className="text-sm text-slate-700 bg-white border border-slate-200 rounded-lg p-2 whitespace-pre-wrap">
                  {it.answer.transcript}
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span
                    className={`px-1.5 py-0.5 rounded font-medium ${
                      BAND_COLOR[it.answer.band] || "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {it.answer.band} · {it.answer.overall.toFixed(1)}
                  </span>
                  <span className="text-slate-500">
                    沟通 {it.answer.dimensions?.communication?.toFixed(0) ?? "—"} ·{" "}
                    思维 {it.answer.dimensions?.thinking?.toFixed(0) ?? "—"} ·{" "}
                    技术 {it.answer.dimensions?.technical?.toFixed(0) ?? "—"}
                  </span>
                </div>
                {it.answer.feedback && (
                  <div className="text-xs text-slate-600 italic">"{it.answer.feedback}"</div>
                )}
                {(it.answer.strengths?.length ?? 0) > 0 && (
                  <div className="text-xs">
                    <span className="text-emerald-600 font-medium">亮点:</span>{" "}
                    {it.answer.strengths.join(" · ")}
                  </div>
                )}
                {(it.answer.improvements?.length ?? 0) > 0 && (
                  <div className="text-xs">
                    <span className="text-amber-600 font-medium">改进:</span>{" "}
                    {it.answer.improvements.join(" · ")}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
