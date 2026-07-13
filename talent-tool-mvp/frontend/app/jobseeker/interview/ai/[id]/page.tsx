"use client";

/**
 * /jobseeker/interview/ai/[id] — v9.1 AI 模拟面试官会话页
 *
 * 五大区域:
 *   1. 头部 + 阶段进度 + 实时模式开关
 *   2. 视频区(候选人摄像头 + 面试官 LiveKit/卡片)
 *   3. 当前题目 + 文本/语音输入
 *   4. 实时对话流(LiveTranscript) + 评分反馈浮层
 *   5. 结束 → 五维评分雷达报告(InterviewReport)
 *
 * 人格可在第一次提交前调整;提交后锁定,避免与后端会话状态错位。
 */

import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import InterviewReport, { type ReportData } from "@/components/interview/InterviewReport";
import InterviewPersonaPicker from "@/components/interview/InterviewPersonaPicker";
import LiveTranscript, { type TranscriptItem } from "@/components/interview/LiveTranscript";
import { useRealtimeSession } from "@/hooks/useRealtimeSession";

const LiveKitVideoStage = dynamic(() => import("@/components/interview/LiveKitVideoStage"), {
  ssr: false,
  loading: () => (
    <div className="aspect-video rounded-2xl bg-slate-100 animate-pulse flex items-center justify-center text-sm text-slate-400">
      准备视频面试…
    </div>
  ),
});

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

const STAGE_LABELS_FULL: Record<string, string> = {
  intro: "破冰 / 自我介绍",
  behavioral: "行为面试",
  technical: "技术深度",
  reverse_q: "反问环节",
  closing: "总结",
};

const STAGE_ORDER = ["intro", "behavioral", "technical", "reverse_q", "closing"];

const PERSONA_AVATAR: Record<string, string> = {
  friendly_warm: "🌸",
  rigorous_strict: "📐",
  challenging_pressure: "🔥",
  senior_experienced: "🧭",
  tech_expert: "🧪",
};

const HISTORY_KEY_PREFIX = "waibao_interviews_v1";

interface StoredMeta {
  id: string;
  persona: { id: string; label: string; voice?: string };
  role: string;
  role_label: string;
  total_questions: number;
  stages: { id: string; label: string; count: number }[];
}

export default function AIInterviewSessionPage(props: { params: Promise<{ id: string }> }) {
  // Next.js 16: 客户端页面收到的 params 是 Promise,使用 React 19 的 use() 解开。
  // 这样能稳定拿到动态段 [id]。
  const { id: interviewId } = use(props.params);
  const router = useRouter();

  const [interview, setInterview] = useState<StoredMeta | null>(null);
  const [plan, setPlan] = useState<PlanQuestion[]>([]);
  const [current, setCurrent] = useState<PlanQuestion | null>(null);
  const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
  const [chatStream, setChatStream] = useState<{ from: "ai" | "user"; text: string; ts: number }[]>([]);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastEval, setLastEval] = useState<AnswerResp | null>(null);
  const [report, setReport] = useState<ReportData | null>(null);
  const [answeredCount, setAnsweredCount] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [, setRealtimeSessionId] = useState<string | null>(null);
  const [realtimeEnabled, setRealtimeEnabled] = useState(false);
  const [personaLocked, setPersonaLocked] = useState(false);
  const [showPersonaPicker, setShowPersonaPicker] = useState(false);
  const [cameraOn, setCameraOn] = useState(false);
  const [videoStream, setVideoStream] = useState<MediaStream | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const cameraRef = useRef<HTMLVideoElement | null>(null);

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
      } catch {
        /* ignore */
      }
    }
    Promise.all([
      fetch(`/api/ai-interview-v2/${interviewId}/plan`, {
        headers: { Authorization: `Bearer ${token}` },
      }).then((r) => r.json()),
      fetch(`/api/ai-interview-v2/${interviewId}/current`, {
        headers: { Authorization: `Bearer ${token}` },
      }).then((r) => r.json()),
    ])
      .then(([planData, curData]) => {
        if (planData?.questions) setPlan(planData.questions);
        if (curData?.current) {
          setCurrent(curData.current);
          setAnsweredCount(curData.answered_count || 0);
          setRemaining(curData.remaining || 0);
          // 推送一条"AI 提问"到实时对话流,模拟开场
          if ((curData.answered_count || 0) === 0) {
            setChatStream([
              {
                from: "ai",
                text: `${curData.current.title}\n${curData.current.prompt}`,
                ts: Date.now(),
              },
            ]);
          }
        }
        // 从后端拉取报告(可能是上一场已完成)
        fetch(`/api/ai-interview-v2/${interviewId}/report`, {
          headers: { Authorization: `Bearer ${token}` },
        })
          .then((r) => (r.ok ? r.json() : null))
          .then((data) => {
            if (data?.report) {
              setReport(data.report as ReportData);
              setPersonaLocked(true);
              persistHistory(data.report as ReportData);
            }
          })
          .catch(() => undefined);
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interviewId]);

  // 摄像头控制
  useEffect(() => {
    if (!cameraOn) {
      if (videoStream) {
        videoStream.getTracks().forEach((t) => t.stop());
        setVideoStream(null);
      }
      return;
    }
    let alive = true;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        if (!alive) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        setVideoStream(stream);
        if (cameraRef.current) {
          cameraRef.current.srcObject = stream;
        }
      } catch (e) {
        if (alive) {
          const msg = e instanceof Error ? e.message : "无法访问摄像头";
          setError(msg || "无法访问摄像头");
          setCameraOn(false);
        }
      }
    })();
    return () => {
      alive = false;
    };
    // videoStream is intentionally not in the dep list — the camera branch
    // only needs to start/stop on cameraOn flips; srcObject syncing is
    // handled in the dedicated effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraOn]);

  useEffect(() => {
    if (cameraRef.current && videoStream) {
      cameraRef.current.srcObject = videoStream;
    }
  }, [videoStream]);

  useEffect(() => {
    return () => {
      if (videoStream) {
        videoStream.getTracks().forEach((t) => t.stop());
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 实时对话流的 Realtime 转写追加
  useEffect(() => {
    if (!realtimeActive) return;
    if (rt.transcript && Array.isArray(rt.transcript) && rt.transcript.length > 0) {
      // 取最后一条 user/assistant 的 text
      const lastUser = [...rt.transcript].reverse().find((m) => m.role === "user");
      if (lastUser) {
        setChatStream((arr) => {
          const last = arr[arr.length - 1];
          if (last && last.from === "user" && last.text === lastUser.text) return arr;
          return [...arr, { from: "user" as const, text: lastUser.text, ts: Date.now() }];
        });
      }
      const lastAi = [...rt.transcript].reverse().find((m) => m.role === "assistant");
      if (lastAi) {
        setChatStream((arr) => {
          const last = arr[arr.length - 1];
          if (last && last.from === "ai" && last.text === lastAi.text) return arr;
          return [...arr, { from: "ai" as const, text: lastAi.text, ts: Date.now() }];
        });
      }
    }
  }, [rt.transcript, realtimeActive]);

  function persistHistory(reportData: ReportData) {
    if (typeof window === "undefined") return;
    try {
      const raw = localStorage.getItem(HISTORY_KEY_PREFIX);
      const arr: Array<Record<string, unknown>> = raw ? JSON.parse(raw) : [];
      const idx = arr.findIndex(
        (x) => (x as { id?: string }).id === reportData.interview_id || (x as { id?: string }).id === interviewId,
      );
      const record = {
        id: reportData.interview_id || interviewId,
        role: reportData.role,
        role_label: reportData.role,
        difficulty: interview?.total_questions ? "—" : "—",
        persona_id: reportData.persona_id,
        persona_label: reportData.persona_id,
        status: "finished" as const,
        started_at: arr[idx]?.started_at || new Date().toISOString(),
        finished_at: new Date().toISOString(),
        overall_score: reportData.overall_score,
        recommendation: reportData.recommendation,
        report: {
          overall_score: reportData.overall_score,
          recommendation: reportData.recommendation,
          summary: reportData.summary,
          radar: reportData.radar,
        },
      };
      if (idx >= 0) {
        arr[idx] = { ...arr[idx], ...record };
      } else {
        arr.unshift(record);
      }
      localStorage.setItem(HISTORY_KEY_PREFIX, JSON.stringify(arr));
    } catch {
      /* ignore */
    }
  }

  const submitAnswer = useCallback(async () => {
    if (!current) return;
    if (!answer.trim()) {
      setError("请先输入回答");
      return;
    }
    setSubmitting(true);
    setError(null);
    setPersonaLocked(true);
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
      setChatStream((arr) => [
        ...arr,
        { from: "user", text: answer, ts: Date.now() },
        {
          from: "ai",
          text: `已收到 · ${data.evaluation.band} · ${data.evaluation.overall.toFixed(1)} 分 · ${
            data.evaluation.feedback || "继续加油"
          }`,
          ts: Date.now(),
        },
      ]);
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
          setChatStream((arr) => [
            ...arr,
            {
              from: "ai",
              text: `追问:${current.title}\n${data.probing.follow_up_question || "能再多说一些吗?"}`,
              ts: Date.now(),
            },
          ]);
        } else {
          advance();
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, answer, interviewId]);

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
    setAnsweredCount((c) => c + 1);
    if (data.current) {
      setChatStream((arr) => [
        ...arr,
        {
          from: "ai",
          text: `${data.current.title}\n${data.current.prompt}`,
          ts: Date.now(),
        },
      ]);
    }
  }

  async function finish() {
    const token = localStorage.getItem("sb_token") || "";
    setSubmitting(true);
    try {
      const r = await fetch(`/api/ai-interview-v2/${interviewId}/finish`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) {
        setError("无法生成报告");
        return;
      }
      const data = await r.json();
      const reportData = data.report as ReportData;
      setReport(reportData);
      persistHistory(reportData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成报告失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function startRealtime() {
    const token = localStorage.getItem("sb_token") || "";
    try {
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
      await rt.start({ voice: data.persona?.voice || "alloy" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Realtime 启动失败");
    }
  }

  async function stopRealtime() {
    await rt.stop();
    setRealtimeEnabled(false);
  }

  const stageProgress = useMemo(() => {
    return STAGE_ORDER.map((k) => {
      const stageQ = plan.filter((p) => p.stage === k);
      const total = stageQ.length;
      const done = transcript.filter((t) => t.question.stage === k).length;
      const active = current?.stage === k;
      return { key: k, label: STAGE_LABELS_FULL[k] || k, total, done, active };
    });
  }, [plan, transcript, current]);

  // 报告视图
  if (report) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-sky-50">
        <header className="bg-white border-b px-6 py-4 flex items-center justify-between">
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <span aria-hidden>📊</span> 模拟面试报告
          </h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => router.push("/jobseeker/interview")}
              className="text-sm text-sky-600 hover:text-sky-800"
              data-testid="back-to-list"
            >
              ← 返回面试中心
            </button>
            <button
              onClick={() => router.push(`/jobseeker/interview-prep/${interview?.role || "backend_engineer"}`)}
              className="px-3 py-1.5 text-sm rounded-lg bg-slate-900 text-white"
            >
              角色练习
            </button>
          </div>
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

  const personaIcon = PERSONA_AVATAR[interview.persona?.id || ""] || "🤖";
  const totalQuestions = interview.total_questions || plan.length || 0;
  const canFinish = remaining === 0 && answeredCount > 0;
  const cameraCard = (
    <div
      className="relative aspect-video rounded-2xl bg-slate-900 text-white overflow-hidden flex items-center justify-center"
      aria-label="候选人视频画面"
    >
      {cameraOn && videoStream ? (
        <video
          ref={cameraRef}
          autoPlay
          muted
          playsInline
          className="w-full h-full object-cover"
          data-testid="camera-preview"
        />
      ) : (
        <div className="text-center space-y-2" data-testid="camera-placeholder">
          <div className="text-4xl" aria-hidden>
            👤
          </div>
          <p className="text-xs text-slate-400">摄像头未开启</p>
        </div>
      )}
      <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between text-[10px]">
        <span className="bg-black/40 px-2 py-0.5 rounded">你 · 候选人</span>
        <button
          onClick={() => setCameraOn((v) => !v)}
          className="px-2 py-0.5 rounded bg-white/20 hover:bg-white/30 backdrop-blur"
          data-testid="toggle-camera"
        >
          {cameraOn ? "关闭摄像头" : "开启摄像头"}
        </button>
      </div>
    </div>
  );

  const livekitCard = (
    <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden">
      <div className="px-4 py-3 border-b bg-slate-50 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">AI 面试官 · 视频</h3>
          <p className="text-xs text-slate-500">
            接入 LiveKit 房间 · {interview.persona?.label}
          </p>
        </div>
        <span className="text-xs px-2 py-0.5 rounded-full bg-violet-100 text-violet-700">
          {interview.persona?.id}
        </span>
      </div>
      <div className="p-3">
        <LiveKitVideoStage
          interviewId={interviewId}
          onLeave={() => router.push("/jobseeker/interview")}
        />
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-sky-50">
      <a
        href="#question-panel"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:bg-white focus:px-3 focus:py-2 focus:rounded"
      >
        跳到题目
      </a>

      <header className="bg-white border-b px-6 py-4 flex items-center justify-between sticky top-0 z-20">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <span aria-hidden>{personaIcon}</span> AI 模拟面试
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {interview.role_label} · 难度 {plan[0] ? "—" : "—"} · 已答 {answeredCount} / {totalQuestions}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!personaLocked && (
            <button
              onClick={() => setShowPersonaPicker((v) => !v)}
              className="px-3 py-1.5 text-xs rounded-full bg-slate-100 text-slate-700 hover:bg-slate-200"
              data-testid="open-persona"
            >
              切换人格
            </button>
          )}
          {!realtimeEnabled ? (
            <button
              onClick={startRealtime}
              className="px-3 py-1.5 text-xs rounded-full bg-sky-100 text-sky-700 hover:bg-sky-200"
              data-testid="start-realtime"
            >
              🎙 启用语音
            </button>
          ) : (
            <button
              onClick={stopRealtime}
              className="px-3 py-1.5 text-xs rounded-full bg-rose-100 text-rose-700 hover:bg-rose-200"
              data-testid="stop-realtime"
            >
              关闭语音
            </button>
          )}
          <button
            onClick={() => router.push("/jobseeker/interview")}
            className="text-xs text-slate-500 hover:text-slate-700"
          >
            ← 退出
          </button>
        </div>
      </header>

      {showPersonaPicker && (
        <section
          className="bg-white border-b px-6 py-5"
          aria-label="切换面试官人格"
        >
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
            ⚠ 切换人格仅在第一次提交回答前有效,提交后将锁定以保持会话一致性。
          </p>
          <InterviewPersonaPicker
            selected={interview.persona?.id || "friendly_warm"}
            onSelect={(id) => {
              // 仅本地缓存;后端切换需重新 /start(简化处理:仅显示)
              setInterview((prev) =>
                prev
                  ? { ...prev, persona: { ...prev.persona, id, label: id } }
                  : prev,
              );
              setShowPersonaPicker(false);
            }}
          />
        </section>
      )}

      <div className="max-w-6xl mx-auto p-6 space-y-4">
        {/* 阶段进度 */}
        <div className="bg-white rounded-2xl shadow-sm p-4">
          <div className="flex items-center gap-1 text-xs" role="list" aria-label="阶段进度">
            {stageProgress.map((sp, idx) => (
              <div
                key={sp.key}
                role="listitem"
                className={`flex-1 rounded-md p-1.5 text-center transition ${
                  sp.active
                    ? "bg-sky-100 text-sky-700"
                    : sp.done === sp.total && sp.total > 0
                    ? "bg-emerald-50 text-emerald-700"
                    : "bg-slate-50 text-slate-500"
                }`}
                data-testid={`stage-progress-${sp.key}`}
              >
                <div className="font-medium truncate">{sp.label}</div>
                <div className="opacity-70">
                  {sp.done}/{sp.total || "—"}
                </div>
                {idx < stageProgress.length - 1 && (
                  <span className="sr-only">下一阶段 {stageProgress[idx + 1].label}</span>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          {/* 左侧 · 视频区 */}
          <div className="lg:col-span-2 space-y-4">
            {livekitCard}
            {cameraCard}
            {realtimeActive && (
              <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-700 space-y-1">
                <p>
                  🎙 语音已启用 · 状态: <span className="font-medium">{rt.state}</span>
                </p>
                {rt.emotion && <p>情绪: {rt.emotion}</p>}
                <p className="text-slate-500">语音流将自动填入下方输入框。</p>
              </div>
            )}
            {lastEval && (
              <div
                className="bg-white rounded-2xl shadow-sm p-4 space-y-2"
                data-testid="last-eval"
              >
                <h3 className="text-sm font-semibold text-slate-800">上一次评分</h3>
                <div className="flex items-center gap-2 text-sm">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      lastEval.evaluation.band === "excellent"
                        ? "bg-emerald-100 text-emerald-700"
                        : lastEval.evaluation.band === "good"
                        ? "bg-sky-100 text-sky-700"
                        : lastEval.evaluation.band === "fair"
                        ? "bg-amber-100 text-amber-700"
                        : "bg-rose-100 text-rose-700"
                    }`}
                  >
                    {lastEval.evaluation.band} · {lastEval.evaluation.overall.toFixed(1)} 分
                  </span>
                </div>
                <p className="text-xs text-slate-600 italic">
                  「{lastEval.evaluation.feedback}」
                </p>
                <div className="grid grid-cols-5 gap-1 text-[10px] text-slate-500">
                  {Object.entries(lastEval.evaluation.dimensions || {}).map(([k, v]) => (
                    <div key={k} className="text-center bg-slate-50 rounded py-1">
                      <div className="font-medium text-slate-700">{Math.round(v)}</div>
                      <div>
                        {k === "technical"
                          ? "技"
                          : k === "communication"
                          ? "沟"
                          : k === "thinking"
                          ? "思"
                          : k === "potential"
                          ? "潜"
                          : "文"}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 右侧 · 题目 + 实时对话 + 转写 */}
          <div className="lg:col-span-3 space-y-4" ref={transcriptRef}>
            <section
              id="question-panel"
              className="bg-white rounded-2xl shadow-sm p-5 space-y-3"
              data-testid="current-question"
              aria-label="当前面试题"
            >
              {current ? (
                <>
                  <div className="flex items-center gap-2 flex-wrap">
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
                  <p className="text-slate-600 leading-relaxed">{current.prompt}</p>
                  {current.expected_points && current.expected_points.length > 0 && (
                    <details className="text-xs text-slate-500">
                      <summary className="cursor-pointer">参考要点</summary>
                      <ul className="mt-1 list-disc pl-4 space-y-0.5">
                        {current.expected_points.map((p, i) => (
                          <li key={i}>{p}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                  <textarea
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    rows={6}
                    placeholder="在此输入你的回答(支持 STAR 结构, 越具体越好)…"
                    className="w-full rounded-xl border border-slate-300 p-3 text-sm focus:border-sky-500 focus:ring-1 focus:ring-sky-200 outline-none"
                    data-testid="answer-textarea"
                    aria-label="回答输入框"
                  />
                  {error && (
                    <div className="bg-rose-50 text-rose-700 text-sm rounded p-2" role="alert">
                      {error}
                    </div>
                  )}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs text-slate-500">
                      剩余 {remaining} 题 · 提交后人格将锁定
                    </span>
                    <div className="flex gap-2">
                      {canFinish ? (
                        <button
                          onClick={finish}
                          disabled={submitting}
                          className="px-4 py-2 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 text-white font-medium disabled:opacity-50"
                          data-testid="finish-interview"
                        >
                          {submitting ? "生成报告中…" : "完成并生成报告"}
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
                </>
              ) : (
                <div className="text-center text-slate-500">
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
            </section>

            <section
              className="bg-white rounded-2xl shadow-sm p-5"
              aria-label="实时对话"
              data-testid="realtime-stream"
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-slate-800">实时对话</h3>
                <span className="text-[10px] text-slate-400">滚动到底部查看最新</span>
              </div>
              <div className="max-h-72 overflow-y-auto space-y-2 pr-1">
                {chatStream.length === 0 && (
                  <div className="text-xs text-slate-400 text-center py-8">
                    还没有对话内容,题目加载后会自动出现。
                  </div>
                )}
                {chatStream.map((m, i) => (
                  <div
                    key={i}
                    className={`flex gap-2 ${m.from === "user" ? "flex-row-reverse" : ""}`}
                  >
                    <div
                      className={`size-7 rounded-full flex items-center justify-center text-sm shrink-0 ${
                        m.from === "ai" ? "bg-sky-100" : "bg-slate-200"
                      }`}
                      aria-hidden
                    >
                      {m.from === "ai" ? personaIcon : "🧑"}
                    </div>
                    <div
                      className={`rounded-2xl px-3 py-2 text-sm max-w-[80%] whitespace-pre-wrap ${
                        m.from === "ai"
                          ? "bg-sky-50 text-slate-800 border border-sky-100"
                          : "bg-slate-900 text-white"
                      }`}
                    >
                      {m.text}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section aria-label="完整转写">
              <LiveTranscript items={transcript} currentQuestionId={current?.id} />
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
