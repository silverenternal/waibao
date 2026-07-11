"use client";

/**
 * VoiceRecorder — MediaRecorder + 实时波形 (T701).
 *
 * 用法:
 *   <VoiceRecorder onTranscript={(text, provider) => ...} />
 *
 * 流程:
 *   1. 请求麦克风权限
 *   2. MediaRecorder 录音 (webm/opus),同步 AnalyserNode 给 VoiceWaveform
 *   3. 停止 → 转 webm Blob → POST /api/voice/transcribe
 *   4. 拿到 transcript,回调上层;同时显示 provider (whisper / aliyun_stt)
 *
 * 失败/拒绝权限 → 提示改用文本输入 (兜底)。
 */

import { useEffect, useRef, useState } from "react";
import VoiceWaveform from "./VoiceWaveform";

export interface VoiceRecorderProps {
  onTranscript: (text: string, provider: string) => void;
  onError?: (err: string) => void;
  language?: string;
  maxDurationSec?: number;
}

type RecorderState = "idle" | "permission" | "recording" | "uploading" | "done" | "error";

export default function VoiceRecorder({
  onTranscript,
  onError,
  language = "auto",
  maxDurationSec = 180,
}: VoiceRecorderProps) {
  const [state, setState] = useState<RecorderState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);

  // 清理资源
  const cleanup = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    mediaRecorderRef.current = null;
    setAnalyser(null);
  };

  useEffect(() => () => cleanup(), []);

  const start = async () => {
    setError(null);
    setState("permission");
    try {
      if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        throw new Error("当前浏览器不支持麦克风录制,请改用文本输入");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // analyser
      const AC: typeof AudioContext =
        (window as any).AudioContext || (window as any).webkitAudioContext;
      const audioCtx = new AC();
      const src = audioCtx.createMediaStreamSource(stream);
      const an = audioCtx.createAnalyser();
      an.fftSize = 1024;
      src.connect(an);
      setAnalyser(an);

      // MediaRecorder
      const mr = new MediaRecorder(stream, {
        mimeType: pickMimeType(),
      });
      mediaRecorderRef.current = mr;
      chunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
        void upload(blob);
      };
      mr.start();

      setState("recording");
      const t0 = Date.now();
      timerRef.current = window.setInterval(() => {
        const sec = Math.floor((Date.now() - t0) / 1000);
        setElapsed(sec);
        if (sec >= maxDurationSec) {
          stop();
        }
      }, 200);
    } catch (e: any) {
      const msg = e?.message || "无法访问麦克风";
      setError(msg);
      setState("error");
      onError?.(msg);
    }
  };

  const stop = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    cleanup();
  };

  const upload = async (blob: Blob) => {
    setState("uploading");
    try {
      const token = localStorage.getItem("sb_token") || "";
      const fd = new FormData();
      const ext = blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
      fd.append("audio", blob, `voice.${ext}`);
      fd.append("language", language);
      const r = await fetch("/api/voice/transcribe", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      const data = await r.json();
      if (!r.ok || !data.success) {
        throw new Error(data?.detail || data?.error || "转写失败,请改用文本输入");
      }
      onTranscript(data.text || "", data.provider || "unknown");
      setState("done");
    } catch (e: any) {
      const msg = e?.message || "上传失败";
      setError(msg);
      setState("error");
      onError?.(msg);
    }
  };

  const reset = () => {
    setState("idle");
    setError(null);
    setElapsed(0);
  };

  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm space-y-3" data-testid="voice-recorder">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">
          {state === "idle" && "准备录音"}
          {state === "permission" && "请求麦克风权限..."}
          {state === "recording" && `录音中 (${elapsed}s / ${maxDurationSec}s)`}
          {state === "uploading" && "上传 + 转写中..."}
          {state === "done" && "转写完成"}
          {state === "error" && "录音失败"}
        </div>
        <div className="space-x-2">
          {state === "idle" && (
            <button
              data-testid="voice-start"
              onClick={start}
              className="px-3 py-1.5 text-sm rounded bg-sky-600 text-white hover:bg-sky-700"
            >
              开始录音
            </button>
          )}
          {state === "recording" && (
            <button
              data-testid="voice-stop"
              onClick={stop}
              className="px-3 py-1.5 text-sm rounded bg-red-600 text-white hover:bg-red-700"
            >
              停止
            </button>
          )}
          {(state === "done" || state === "error") && (
            <button
              data-testid="voice-reset"
              onClick={reset}
              className="px-3 py-1.5 text-sm rounded bg-slate-200 hover:bg-slate-300"
            >
              再来一次
            </button>
          )}
        </div>
      </div>

      <VoiceWaveform analyser={analyser} />

      {error && (
        <div className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded" data-testid="voice-error">
          {error} — 你也可以直接输入文字日记。
        </div>
      )}

      {state === "uploading" && (
        <div className="text-xs text-slate-500">正在调用 Whisper 转写;失败会自动降级到 aliyun_stt。</div>
      )}
    </div>
  );
}

function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "audio/webm";
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  for (const c of candidates) {
    if (MediaRecorder.isTypeSupported(c)) return c;
  }
  return "audio/webm";
}