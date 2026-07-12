"use client";

/**
 * /jobseeker/interview/ai/[id] — T2202 AI 模拟面试官会话页.
 *
 * 5 阶段流程: intro → behavioral → technical → reverse_q → closing
 * 5 种人格 + 智能追问 + 5 维评分
 *
 * 进入页面前:用户在 /jobseeker/interview 选择人格 + 难度 + 岗位
 * 流程:
 *   1. 拉取 /plan 获取全部题目
 *   2. 拉取 /current 拿到当前题
 *   3. 用户回答(支持 Realtime 语音或文本)→ POST /answer
 *   4. 后端返回 评分 + probing 决策(可能插入追问)
 *   5. 用户点"下一题" → POST /advance
 *   6. 全部完成 → POST /finish → 显示报告
 */

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import InterviewReport, { type ReportData } from "@/components/interview/InterviewReport";
import LiveTranscript, { type TranscriptItem } from "@/components/interview/LiveTranscript";
import { useRealtimeSession } from "@/hooks/useRealtimeSession";

interface PlanQuestion {
  id: string;
  stage: string;
  stage_label: string;
  seq: number;
  stage_seq: number;
  title: string;
  prompt: string;
  expected_points?: string[];
  is_follow_up?: boolean;
}

interface AnswerResp {
  question_id: string;
  evaluation: {
    overall: number;
    dimensions: Record<string, number>;
    band: string;
    feedback: string;
    strengths: string[];
    improvements: string[];
    depth_score: number;
    coverage_signals: string[];
  };
  probing: {
    should_follow_up: boolean;
    follow_up_question: string | null;
    reason: string;
    depth_score: number;
  };
  next_question_id: string | null;
}

const STAGE_LABELS: Record<string, string> = {
  intro: "破冰 / 自我介绍",
  behavioral: "行为面试",
  technical: "技术深度",
  reverse_q: "反问环节",
  closing: "总结",
};

export default function AIInterviewSessionPage() {
  const params = useParams();
  const router = useRouter();
  const interviewId = (params?.id as string) || "";

  const [interview, setInterview] = useState<{
    id: string;
    persona: { id: string; label: string; voice: string };
    role: string;
    role_label: string;
    total_questions: number;
    stages: { id: string; label: string; count: number }[];
  } | null>(null);
  const [plan, setPlan] = useState<PlanQuestion[]>([]);
  const [current, setCurrent] = useState<PlanQuestion | null>(null);
  const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastEval, setLastEval] = useState<AnswerResp | null>(null);
  const [report, setReport] = useState<ReportData | null>(null);
  const [answeredCount, setAnsweredCount] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [realtimeSessionId, setRealtimeSessionId] = useState<string | null>(null);
  const [realtimeEnabled, setRealtimeEnabled] = useState(false);
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  // Local realtime session (only mounted when user enables it)
  const rt = useRealtimeSession();
  const realtimeActive = realtimeEnabled && rt.state !== "idle" && rt.state !== "ended";

  // Fetch interview info
  useEffect(() => {
    if (!interviewId) return;
    const token = localStorage.getItem("sb_token") || "";
    // Reconstruct from sessionStorage
    const cached = sessionStorage.getItem(`interview_${interviewId}`);
    if (cached) {
      try {
        setInterview(JSON.parse(cached));
      } catch {}
    }
    fetch(`/api/ai-interview-v2/${interviewId}/plan`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.questions) setPlan(data.questions);
      });
    refreshCurrent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interviewId]);

  function refreshCurrent() {
    const token = localStorage.getItem("sb_token") || "";
    fetch(`/api/ai-interview-v2/${interviewId}/current`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        setCurrent(data.current);
        setAnsweredCount(data.answered_count || 0);
        setRemaining(data.remaining || 0);
      });
  }

  async function submitAnswer() {
    if (!current) return;
    if (!answer.trim()) {
      setError("请先输入回答");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch(`/api/ai-interview-v2/${interviewId}/answer`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          question_id: current.id,
          transcript: answer,
          duration_sec: 0,
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      const data: AnswerResp = await r.json();
      setLastEval(data);
      // Append to transcript
      setTranscript((arr) => [
        ...arr,
        {
          question: {
            id: current.id,
            stage: current.stage,
            stage_label: current.stage_label,
            title: current.title,
            prompt: current.prompt,
            is_follow_up: current.is_follow_up,
          },
          answer: {
            question_id: current.id,
            transcript: answer,
            overall: data.evaluation.overall,
            band: data.evaluation.band,
            feedback: data.evaluation.feedback,
            strengths: data.evaluation.strengths,
            improvements: data.evaluation.improvements,
            dimensions: data.evaluation.dimensions,
          },
        },
      ]);
      setAnswer("");
      // Reload plan to include possible follow-up
      const r2 = await fetch(`/api/ai-interview-v2/${interviewId}/plan`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data2 = await r2.json();
      if (data2.questions) {
        setPlan(data2.questions);
        // If probing inserted a follow-up, the server told us next_question_id;
        // otherwise advance to next unanswered
        if (data.probing?.should_follow_up) {
          setCurrent({
            id: data.next_question_id || current.id,
            stage: current.stage,
            stage_label: current.stage_label,
            seq: current.seq,
            stage_seq: current.stage_seq + 1,
            title: `追问:${current.title}`,
            prompt: data.probing.follow_up_question || "能再多说一些吗?",
            is_follow_up: true,
          });
        } else {
          advance();
        }
      }
    } catch (e: any) {
      setError(e?.message || "提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function advance() {
    const token = localStorage.getItem("sb_token") || "";
    const r = await fetch(`/api/ai-interview-v2/${interviewId}/advance`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({}),
    });
    const data = await r.json();
    setCurrent(data.current);
    setRemaining(data.remaining || 0);
  }

  async function finish() {
    const token = localStorage.getItem("sb_token") || "";
    const r = await fetch(`/api/ai-interview-v2/${interviewId}/finish`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!r.ok) {
      setError("无法生成报告");
      return;
    }
    const data = await r.json();
    setReport(data.report as ReportData);
  }

  async function startRealtime() {
    const token = localStorage.getItem("sb_token") || "";
    const r = await fetch(`/api/ai-interview-v2/realtime-session`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ interview_id: interviewId, force_mock: true }),
    });
    if (!r.ok) {
      setError("无法创建 Realtime 会话");
      return;
    }
    const data = await r.json();
    setRealtimeSessionId(data.session_id);
    setRealtimeEnabled(true);
    await rt.start({ voice: data.persona.voice });
  }

  if (report) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-sky-50">
        <header className="bg-white border-b px-6 py-4 flex items-center justify-between">
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <span aria-hidden>🤖</span> 模拟面试报告
          </h1>
          <button
            onClick={() => router.push("/jobseeker/interview")}
            className="text-sm text-sky-600 hover:text-sky-800"
          >
            返回面试列表
          </button>
        </header>
        <div className="max-w-5xl mx-auto p-6">
          <InterviewReport report={report} />
        </div>
      </div>
    );
  }

  if (!interview) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500">
        加载面试中…
      </div>
    );
  }

  const stageProgress = STAGE_LABELS;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-sky-50">
      <header className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <span aria-hidden>🤖</span> AI 模拟面试
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            人格: {interview.persona.label} · 岗位: {interview.role_label}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span>
            已答 {answeredCount} / {interview.total_questions}
          </span>
          {!realtimeEnabled ? (
            <button
              onClick={startRealtime}
              className="px-3 py-1 rounded-full bg-sky-100 text-sky-700 hover:bg-sky-200"
              data-testid="start-realtime"
            >
              启用语音
            </button>
          ) : (
            <button
              onClick={async () => {
                await rt.stop();
                setRealtimeEnabled(false);
              }}
              className="px-3 py-1 rounded-full bg-rose-100 text-rose-700 hover:bg-rose-200"
              data-testid="stop-realtime"
            >
              关闭语音
            </button>
          )}
        </div>
      </header>

      <div className="max-w-6xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3 space-y-4">
          {/* Stage progress */}
          <div className="bg-white rounded-2xl shadow-sm p-4">
            <div className="flex items-center gap-1 text-xs">
              {Object.entries(stageProgress).map(([k, label], idx, arr) => {
                const stageQ = plan.filter((p) => p.stage === k);
                const total = stageQ.length;
                const done = transcript.filter((t) => t.question.stage === k).length;
                const active = current?.stage === k;
                return (
                  <div
                    key={k}
                    className={`flex-1 rounded-md p-1.5 text-center ${
                      active
                        ? "bg-sky-100 text-sky-700"
                        : done === total && total > 0
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-slate-50 text-slate-500"
                    }`}
                    data-testid={`stage-progress-${k}`}
                  >
                    <div className="font-medium">{label}</div>
                    <div className="opacity-70">
                      {done}/{total || "—"}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Current question */}
          {current ? (
            <div className="bg-white rounded-2xl shadow-sm p-5 space-y-3" data-testid="current-question">
              <div className="flex items-center gap-2">
                <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">
                  {current.stage_label}
                </span>
                {current.is_follow_up && (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">
                    追问
                  </span>
                )}
                <span className="text-xs text-slate-400">
                  第 {current.stage_seq} 题
                </span>
              </div>
              <h2 className="text-lg font-semibold text-slate-800">{current.title}</h2>
              <p className="text-slate-600">{current.prompt}</p>
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                rows={6}
                placeholder="在此输入你的回答(支持 STAR 结构, 越具体越好)…"
                className="w-full rounded-xl border border-slate-300 p-3 text-sm focus:border-sky-500 focus:ring-1 focus:ring-sky-200 outline-none"
                data-testid="answer-textarea"
              />
              {realtimeActive && (
                <div className="rounded-lg border border-sky-200 bg-sky-50 p-2 text-xs text-sky-700">
                  语音已启用 · 状态: {rt.state} · 情绪: {rt.emotion} · 文本流(如有)将作为补充。
                </div>
              )}
              {error && (
                <div className="bg-rose-50 text-rose-700 text-sm rounded p-2">{error}</div>
              )}
              <div className="flex flex-wrap items-center justify-end gap-2">
                {remaining === 0 && answeredCount > 0 ? (
                  <button
                    onClick={finish}
                    className="px-4 py-2 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 text-white font-medium"
                    data-testid="finish-interview"
                  >
                    完成并生成报告
                  </button>
                ) : (
                  <button
                    onClick={submitAnswer}
                    disabled={submitting}
                    className="px-4 py-2 rounded-xl bg-sky-500 text-white font-medium disabled:opacity-50"
                    data-testid="submit-answer"
                  >
                    {submitting ? "提交中…" : "提交并下一题"}
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-2xl shadow-sm p-5 text-center text-slate-500">
              所有题目已答完。点击下方按钮生成报告。
              <div className="mt-3">
                <button
                  onClick={finish}
                  className="px-5 py-2 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 text-white font-medium"
                  data-testid="finish-interview"
                >
                  生成报告
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="lg:col-span-2 space-y-4" ref={transcriptRef}>
          <LiveTranscript
            items={transcript}
            currentQuestionId={current?.id}
          />
        </div>
      </div>
    </div>
  );
}
