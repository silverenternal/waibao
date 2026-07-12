"use client";

/**
 * /interview/[id] — AI 面试会话页 (T1301).
 *
 * 流程:
 *   1. 拉取 questions
 *   2. 逐题作答(视频或纯文本)
 *   3. 全部完成 → 点击"完成面试"生成报告 → 显示 InterviewFeedback
 */

import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { InterviewQuestion } from "@/components/InterviewQuestion";
import { InterviewFeedback } from "@/components/InterviewFeedback";
import VideoInterviewRecorder from "@/components/VideoInterviewRecorder";

interface QuestionData {
  id: string;
  seq: number;
  category: string;
  title: string;
  prompt: string;
  expected_points?: string[];
  difficulty?: string;
  qtype?: string;
  skills?: string[];
}

interface AnswerData {
  seq: number;
  question_id: string;
  overall: number;
  band: string;
  dimensions: Record<string, number>;
  strengths: string[];
  improvements: string[];
  feedback: string;
  transcript_provider: string;
  video_url?: string;
}

const BAND_COLOR: Record<string, string> = {
  weak: "bg-rose-100 text-rose-700",
  fair: "bg-amber-100 text-amber-700",
  good: "bg-sky-100 text-sky-700",
  excellent: "bg-emerald-100 text-emerald-700",
};

export default function InterviewSessionPage() {
  const params = useParams();
  const router = useRouter();
  const interviewId = (params?.id as string) || "";

  const [questions, setQuestions] = useState<QuestionData[]>([]);
  const [answers, setAnswers] = useState<Record<string, AnswerData>>({});
  const [activeIdx, setActiveIdx] = useState(0);
  const [transcriptText, setTranscriptText] = useState("");
  const [videoUrl, setVideoUrl] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const token = () => localStorage.getItem("sb_token") || "";

  useEffect(() => {
    if (!interviewId) return;
    (async () => {
      try {
        const r = await fetch(`/api/ai-interview/${interviewId}/questions`, {
          headers: { Authorization: `Bearer ${token()}` },
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        setQuestions(data.questions || []);
      } catch (e: any) {
        setError(e?.message || "加载面试失败");
      } finally {
        setLoading(false);
      }
    })();
  }, [interviewId]);

  const activeQ = questions[activeIdx];
  const activeAnswer = activeQ ? answers[activeQ.id] : undefined;

  async function submitAnswerText() {
    if (!activeQ) return;
    if (!transcriptText.trim()) return;
    setSubmitting(true);
    try {
      const r = await fetch(`/api/ai-interview/${interviewId}/answer-text`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ seq: activeQ.seq, transcript: transcriptText, video_url: videoUrl }),
      });
      if (!r.ok) throw new Error(await r.text());
      const data: AnswerData = await r.json();
      setAnswers((prev) => ({ ...prev, [activeQ.id]: data }));
    } catch (e: any) {
      setError(e?.message || "提交答案失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitAnswerVideo(blob: Blob) {
    if (!activeQ) return;
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("seq", String(activeQ.seq));
      fd.append("video", blob, `q${activeQ.seq}.webm`);
      const r = await fetch(`/api/ai-interview/${interviewId}/answer`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token()}` },
        body: fd,
      });
      if (!r.ok) throw new Error(await r.text());
      const data: AnswerData = await r.json();
      setAnswers((prev) => ({ ...prev, [activeQ.id]: data }));
    } catch (e: any) {
      setError(e?.message || "上传视频失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function finishInterview() {
    setSubmitting(true);
    try {
      const r = await fetch(`/api/ai-interview/${interviewId}/finish`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token()}` },
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setReport(data.report);
    } catch (e: any) {
      setError(e?.message || "生成报告失败");
    } finally {
      setSubmitting(false);
    }
  }

  function goNext() {
    if (activeIdx + 1 < questions.length) {
      setActiveIdx(activeIdx + 1);
      setTranscriptText("");
      setVideoUrl(undefined);
    }
  }

  function goPrev() {
    if (activeIdx > 0) {
      setActiveIdx(activeIdx - 1);
      // 不清答案缓存
      setTranscriptText(answers[questions[activeIdx - 1]?.id]?.transcript_provider ? "" : "");
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-400">加载中...</div>
    );
  }
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center px-6">
        <div className="max-w-md bg-rose-50 text-rose-700 p-5 rounded-xl">
          {error}
          <button
            onClick={() => router.push("/jobseeker/interview")}
            className="mt-3 px-4 py-2 bg-rose-600 text-white rounded"
          >
            回到首页
          </button>
        </div>
      </div>
    );
  }
  if (report) {
    return (
      <div className="min-h-screen bg-slate-50">
        <div className="bg-white border-b px-6 py-4 flex items-center justify-between">
          <h1 className="text-xl font-semibold">面试报告</h1>
          <div className="flex gap-2">
            <button
              onClick={() => router.push("/jobseeker/interview")}
              className="px-3 py-1.5 text-sm bg-slate-200 hover:bg-slate-300 rounded"
            >
              再来一场
            </button>
          </div>
        </div>
        <div className="max-w-4xl mx-auto p-6 space-y-6">
          <InterviewFeedback report={report} />
          <section className="border rounded-2xl bg-white p-6 shadow-sm space-y-3">
            <h3 className="text-base font-semibold text-slate-800">逐题回顾</h3>
            <div className="space-y-3">
              {questions.map((q) => (
                <InterviewQuestion
                  key={q.id}
                  question={q}
                  answer={answers[q.id]}
                  showVideoUrl={answers[q.id]?.video_url}
                />
              ))}
            </div>
          </section>
        </div>
      </div>
    );
  }

  if (!activeQ) return null;

  const answeredCount = questions.filter((q) => answers[q.id]).length;
  const allAnswered = answeredCount === questions.length;

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">AI 面试中 ({activeIdx + 1} / {questions.length})</h1>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-slate-500">
            已答 {answeredCount}/{questions.length}
          </span>
          <button
            onClick={() => router.push("/jobseeker/interview")}
            className="px-3 py-1 text-xs rounded bg-slate-200 hover:bg-slate-300"
          >
            退出
          </button>
        </div>
      </div>

      <div className="max-w-3xl mx-auto p-6 space-y-5">
        {/* 进度条 */}
        <div className="w-full h-1 bg-slate-200 rounded">
          <div
            className="h-full bg-sky-500 transition-all"
            style={{ width: `${((activeIdx + 1) / questions.length) * 100}%` }}
          />
        </div>

        {/* 当前题目 */}
        <InterviewQuestion question={activeQ} answer={activeAnswer} />

        {/* 录入区 */}
        {!activeAnswer ? (
          <section className="bg-white rounded-2xl shadow-sm p-5 space-y-4">
            <h3 className="text-base font-semibold text-slate-800">你的回答</h3>
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-xs text-slate-600 font-medium">视频回答</label>
                <VideoInterviewRecorder
                  maxDurationSec={120}
                  onRecorded={(_, url) => setVideoUrl(url)}
                  interviewId={interviewId}
                  autoUpload
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs text-slate-600 font-medium">或文本回答</label>
                <textarea
                  data-testid="answer-text"
                  className="w-full border rounded-xl p-3 min-h-32 focus:outline-none focus:ring-2 focus:ring-sky-500"
                  placeholder="建议使用 STAR 法则(Situation / Task / Action / Result)组织答案。"
                  value={transcriptText}
                  onChange={(e) => setTranscriptText(e.target.value)}
                />
                <button
                  data-testid="submit-text"
                  onClick={submitAnswerText}
                  disabled={submitting || !transcriptText.trim()}
                  className="w-full px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 text-white disabled:opacity-50"
                >
                  {submitting ? "提交中..." : "提交文本回答"}
                </button>
              </div>
            </div>
          </section>
        ) : (
          <section className="bg-sky-50 border border-sky-200 rounded-2xl p-5">
            <div className="flex items-center justify-between">
              <div className="text-sm text-sky-700">
                <span className={`px-2 py-0.5 rounded ${BAND_COLOR[activeAnswer.band] || BAND_COLOR.fair}`}>
                  {activeAnswer.band}
                </span>
                <span className="ml-2 font-semibold">{activeAnswer.overall} 分</span>
              </div>
              <button
                onClick={goNext}
                disabled={activeIdx + 1 === questions.length}
                className="px-4 py-1.5 text-sm bg-sky-600 text-white rounded disabled:opacity-50"
                data-testid="next-q"
              >
                {activeIdx + 1 === questions.length ? "已答完" : "下一题 →"}
              </button>
            </div>
            {activeAnswer.feedback && (
              <p className="mt-2 text-sm text-sky-900">{activeAnswer.feedback}</p>
            )}
          </section>
        )}

        {/* 导航 */}
        <div className="flex justify-between text-sm">
          <button
            onClick={goPrev}
            disabled={activeIdx === 0}
            className="px-4 py-2 rounded bg-slate-200 hover:bg-slate-300 disabled:opacity-50"
          >
            ← 上一题
          </button>
          {allAnswered && (
            <button
              onClick={finishInterview}
              disabled={submitting}
              data-testid="finish-interview"
              className="px-6 py-2 rounded-lg bg-gradient-to-r from-emerald-500 to-teal-600 text-white font-medium disabled:opacity-50"
            >
              {submitting ? "生成报告中..." : "生成最终报告"}
            </button>
          )}
        </div>

        {/* 快速跳转 */}
        <div className="bg-white border rounded-2xl p-4">
          <div className="text-xs text-slate-500 mb-2">题目导航</div>
          <div className="flex flex-wrap gap-2">
            {questions.map((q, idx) => {
              const done = !!answers[q.id];
              const active = idx === activeIdx;
              return (
                <button
                  key={q.id}
                  onClick={() => setActiveIdx(idx)}
                  className={`w-8 h-8 rounded-full text-xs flex items-center justify-center ${
                    active
                      ? "bg-sky-600 text-white"
                      : done
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-slate-100 text-slate-500"
                  }`}
                >
                  {idx + 1}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
