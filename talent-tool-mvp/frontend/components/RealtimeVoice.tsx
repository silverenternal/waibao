"use client";

/**
 * RealtimeVoice — T2201 client UI for GPT-4o Realtime.
 *
 * 包含:
 *   - 录音 (AudioContext + ScriptProcessor) + 实时波形条
 *   - 3D 头像 (简单的 SVG 化身,带情绪口型 + 表情)
 *   - 实时转写区 (流式拼接 delta)
 *   - 中断 / 继续 / 结束 按钮
 *   - 情绪自动检测 (从音频 RMS + ZCR 推断)
 *   - 指标 (latency, tokens, audio seconds)
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useRealtimeSession, type Emotion } from "@/hooks/useRealtimeSession";

interface AvatarProps {
  emotion: Emotion;
  audioLevel: number;
  speaking: boolean;
}

function Avatar3D({ emotion, audioLevel, speaking }: AvatarProps) {
  // 颜色随情绪
  const palette: Record<Emotion, { skin: string; cheek: string; eye: string }> = {
    calm: { skin: "#cde6ff", cheek: "#f7c6c6", eye: "#1e293b" },
    excited: { skin: "#ffd1a8", cheek: "#ff9aa2", eye: "#9a3412" },
    nervous: { skin: "#dde5ff", cheek: "#f6c4c4", eye: "#1e293b" },
    neutral: { skin: "#e2e8f0", cheek: "#f1d1d1", eye: "#0f172a" },
  };
  const p = palette[emotion];
  // 口型开合由 audioLevel 决定
  const mouthH = 4 + audioLevel * 18;
  // 眨眼
  const [blink, setBlink] = useState(false);
  useEffect(() => {
    const id = setInterval(() => {
      setBlink(true);
      setTimeout(() => setBlink(false), 130);
    }, 4200);
    return () => clearInterval(id);
  }, []);
  const eyeH = blink ? 1 : 4;
  return (
    <div className="relative w-40 h-40 mx-auto" aria-label="3D 虚拟面试官头像">
      <svg viewBox="0 0 120 120" className="w-full h-full">
        <defs>
          <radialGradient id="g-skin" cx="50%" cy="40%" r="60%">
            <stop offset="0%" stopColor={p.skin} stopOpacity="1" />
            <stop offset="100%" stopColor="#94a3b8" stopOpacity="0.6" />
          </radialGradient>
          <radialGradient id="g-cheek" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={p.cheek} stopOpacity="0.9" />
            <stop offset="100%" stopColor={p.cheek} stopOpacity="0" />
          </radialGradient>
        </defs>
        {/* 头部 */}
        <ellipse cx="60" cy="58" rx="38" ry="42" fill="url(#g-skin)" stroke="#475569" strokeWidth="1" />
        {/* 腮红 */}
        <ellipse cx="35" cy="72" rx="9" ry="5" fill="url(#g-cheek)" />
        <ellipse cx="85" cy="72" rx="9" ry="5" fill="url(#g-cheek)" />
        {/* 眼睛 */}
        <ellipse cx="46" cy="55" rx={3} ry={eyeH} fill={p.eye} />
        <ellipse cx="74" cy="55" rx={3} ry={eyeH} fill={p.eye} />
        {/* 嘴 */}
        <ellipse
          cx="60"
          cy={speaking ? 80 : 82}
          rx={10}
          ry={mouthH / 2}
          fill="#7f1d1d"
          opacity={speaking ? 1 : 0.7}
        />
        {/* 头发 */}
        <path d="M22 50 Q60 8 98 50 Q98 30 60 22 Q22 30 22 50Z" fill="#1e293b" opacity="0.85" />
        {/* 身体轮廓 */}
        <path d="M14 120 Q14 100 38 96 L82 96 Q106 100 106 120Z" fill="#1e293b" opacity="0.5" />
      </svg>
      {speaking && (
        <div className="absolute inset-0 rounded-full ring-4 ring-sky-300/40 animate-pulse" />
      )}
    </div>
  );
}

function WaveformBars({ level }: { level: number }) {
  const bars = 24;
  return (
    <div className="flex items-end justify-center gap-1 h-12" aria-hidden>
      {Array.from({ length: bars }).map((_, i) => {
        const phase = (i / bars) * Math.PI * 2;
        const h = 8 + Math.abs(Math.sin(phase + level * 4)) * 32 * (0.4 + level);
        return (
          <div
            key={i}
            className="w-1.5 bg-gradient-to-t from-sky-400 to-indigo-500 rounded"
            style={{ height: `${h}px` }}
          />
        );
      })}
    </div>
  );
}

interface RealtimeVoiceProps {
  instructions?: string;
  voice?: string;
  model?: string;
  onComplete?: (transcript: { role: string; text: string }[]) => void;
}

export default function RealtimeVoice({
  instructions,
  voice = "alloy",
  model = "gpt-4o-realtime-preview",
  onComplete,
}: RealtimeVoiceProps) {
  const rt = useRealtimeSession();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const isActive = rt.state !== "idle" && rt.state !== "ended" && rt.state !== "error";

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [rt.transcript.length, rt.partialText]);

  useEffect(() => {
    if (rt.state === "ended" && onComplete) {
      onComplete(rt.transcript);
    }
  }, [rt.state, onComplete, rt.transcript]);

  const emotionLabel: Record<Emotion, string> = useMemo(
    () => ({
      calm: "平静",
      excited: "兴奋",
      nervous: "紧张",
      neutral: "中性",
    }),
    [],
  );

  return (
    <div className="rounded-2xl bg-white shadow-sm p-6 space-y-5" data-testid="realtime-voice">
      <div className="grid md:grid-cols-2 gap-6 items-center">
        <div>
          <Avatar3D
            emotion={rt.emotion}
            audioLevel={rt.audioLevel}
            speaking={rt.state === "speaking"}
          />
          <div className="mt-3 text-center">
            <span className="inline-flex items-center gap-1 text-xs text-slate-500">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> 情绪 ·
              {emotionLabel[rt.emotion]}
            </span>
          </div>
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-sm text-slate-500">
              状态:
              <span className="ml-1 font-medium text-slate-800">
                {rt.state === "idle" && "未开始"}
                {rt.state === "connecting" && "连接中…"}
                {rt.state === "ready" && "待机"}
                {rt.state === "speaking" && "回答中"}
                {rt.state === "ended" && "已结束"}
                {rt.state === "error" && "错误"}
              </span>
            </div>
            <div className="text-xs text-slate-400">
              {rt.metrics.firstAudioLatencyMs !== null
                ? `首响 ${rt.metrics.firstAudioLatencyMs}ms`
                : "—"}
            </div>
          </div>
          <WaveformBars level={rt.audioLevel} />
          <div className="grid grid-cols-2 gap-2 text-xs text-slate-500">
            <div>输入 chunks: {rt.metrics.audioInputChunks}</div>
            <div>输出 chunks: {rt.metrics.audioOutputChunks}</div>
            <div>Tokens: {rt.metrics.usage.total_tokens}</div>
            <div>中断: {rt.metrics.interruptions}</div>
            <div>音频(入): {rt.metrics.usage.audio_input_seconds.toFixed(1)}s</div>
            <div>音频(出): {rt.metrics.usage.audio_output_seconds.toFixed(1)}s</div>
          </div>
        </div>
      </div>

      <div
        ref={scrollRef}
        className="h-56 overflow-y-auto rounded-xl border bg-slate-50 p-3 text-sm space-y-2"
        data-testid="realtime-transcript"
      >
        {rt.transcript.length === 0 && !rt.partialText && (
          <div className="text-slate-400 text-center py-12">
            点击"开始"启动实时对话 …
          </div>
        )}
        {rt.transcript.map((t, i) => (
          <div
            key={i}
            className={`flex ${t.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-3 py-2 ${
                t.role === "user"
                  ? "bg-sky-500 text-white"
                  : "bg-white border border-slate-200 text-slate-800"
              }`}
            >
              {t.text}
            </div>
          </div>
        ))}
        {rt.partialText && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-2xl px-3 py-2 bg-white border border-slate-200 text-slate-800">
              {rt.partialText}
              <span className="ml-1 inline-block w-1.5 h-3 align-middle bg-slate-400 animate-pulse" />
            </div>
          </div>
        )}
      </div>

      {rt.error && (
        <div className="bg-rose-50 text-rose-700 text-sm rounded p-2" data-testid="realtime-error">
          {rt.error}
        </div>
      )}

      <div className="flex flex-wrap gap-2 justify-center">
        {!isActive && (
          <button
            onClick={() => rt.start({ voice, model, instructions })}
            className="px-5 py-2 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 text-white font-medium"
            data-testid="realtime-start"
          >
            {rt.state === "connecting" ? "连接中…" : "开始"}
          </button>
        )}
        {isActive && (
          <>
            <button
              onClick={() => rt.interrupt()}
              className="px-4 py-2 rounded-xl bg-amber-100 text-amber-800"
              data-testid="realtime-interrupt"
            >
              中断
            </button>
            <button
              onClick={() => rt.stop()}
              className="px-4 py-2 rounded-xl bg-rose-100 text-rose-700"
              data-testid="realtime-stop"
            >
              结束
            </button>
          </>
        )}
      </div>

      {/* 文本兜底输入 */}
      {isActive && (
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="(可选) 输入文字打断或补充"
            className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.currentTarget.value) {
                rt.pushText(e.currentTarget.value);
                e.currentTarget.value = "";
              }
            }}
          />
        </div>
      )}
    </div>
  );
}
