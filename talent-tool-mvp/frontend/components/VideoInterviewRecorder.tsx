"use client";

/**
 * VideoInterviewRecorder — MediaRecorder 视频录制组件 (T1301).
 *
 * 用法:
 *   <VideoInterviewRecorder onRecorded={(videoBlob, videoUrl) => ...} maxDurationSec={120} />
 *
 * 流程:
 *   1. 请求摄像头 + 麦克风权限
 *   2. MediaRecorder 录像 (webm/vp8)
 *   3. 实时预览 + 录制计时
 *   4. 停止 → onRecorded callback(video Blob, optional ObjectURL)
 *
 * 失败 → 提示让候选人改用文本输入 (兜底)。
 */

import { useEffect, useRef, useState } from "react";

export interface VideoInterviewRecorderProps {
  maxDurationSec?: number;
  onRecorded: (blob: Blob, objectUrl: string) => void;
  onError?: (err: string) => void;
  /** 上传进度回调(0-1) */
  onUploadProgress?: (pct: number) => void;
  /** 是否在录制后自动上传到 /upload-url */
  autoUpload?: boolean;
  interviewId?: string;
}

type RecorderState = "idle" | "permission" | "recording" | "processing" | "done" | "error";

export default function VideoInterviewRecorder({
  maxDurationSec = 180,
  onRecorded,
  onError,
  onUploadProgress,
  autoUpload = false,
  interviewId,
}: VideoInterviewRecorderProps) {
  const [state, setState] = useState<RecorderState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);

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
  };

  useEffect(() => () => cleanup(), []);

  const start = async () => {
    setError(null);
    setState("permission");
    try {
      if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        throw new Error("当前浏览器不支持摄像头录制,请改用文本输入");
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 1280, height: 720, facingMode: "user" },
        audio: true,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.muted = true;
        await videoRef.current.play().catch(() => {});
      }

      const mr = new MediaRecorder(stream, {
        mimeType: pickVideoMime(),
        videoBitsPerSecond: 800_000,
      });
      mediaRecorderRef.current = mr;
      chunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || "video/webm" });
        const url = URL.createObjectURL(blob);
        setPreviewUrl(url);
        setState("processing");
        try {
          if (autoUpload && interviewId) {
            await uploadToBackend(blob, interviewId, mr.mimeType || "video/webm", onUploadProgress);
          }
          onRecorded(blob, url);
          setState("done");
        } catch (e: any) {
          const msg = e?.message || "上传失败";
          setError(msg);
          setState("error");
          onError?.(msg);
        }
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
      }, 250);
    } catch (e: any) {
      const msg = e?.message || "无法访问摄像头/麦克风";
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

  const reset = () => {
    setState("idle");
    setError(null);
    setElapsed(0);
    setPreviewUrl(null);
  };

  return (
    <div className="border rounded-xl p-4 bg-white shadow-sm space-y-3" data-testid="video-recorder">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">
          {state === "idle" && "准备录制"}
          {state === "permission" && "请求摄像头/麦克风权限..."}
          {state === "recording" && `录制中 (${elapsed}s / ${maxDurationSec}s)`}
          {state === "processing" && (autoUpload ? "上传中..." : "处理中...")}
          {state === "done" && "录制完成"}
          {state === "error" && "录制失败"}
        </div>
        <div className="space-x-2">
          {state === "idle" && (
            <button
              data-testid="video-start"
              onClick={start}
              className="px-3 py-1.5 text-sm rounded bg-rose-600 text-white hover:bg-rose-700"
            >
              开始录制
            </button>
          )}
          {state === "recording" && (
            <button
              data-testid="video-stop"
              onClick={stop}
              className="px-3 py-1.5 text-sm rounded bg-slate-800 text-white hover:bg-slate-900"
            >
              停止
            </button>
          )}
          {(state === "done" || state === "error") && (
            <button
              data-testid="video-reset"
              onClick={reset}
              className="px-3 py-1.5 text-sm rounded bg-slate-200 hover:bg-slate-300"
            >
              再来一次
            </button>
          )}
        </div>
      </div>

      <div className="aspect-video w-full bg-slate-900 rounded-lg overflow-hidden flex items-center justify-center relative">
        <video
          ref={videoRef}
          data-testid="video-preview"
          className="w-full h-full object-cover"
          playsInline
          autoPlay
          muted
        />
        {state === "recording" && (
          <div className="absolute top-3 right-3 flex items-center gap-2 bg-red-600/90 px-2 py-1 rounded text-xs text-white">
            <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
            REC {elapsed}s
          </div>
        )}
        {previewUrl && state !== "recording" && (
          <video src={previewUrl} controls className="w-full h-full object-cover" />
        )}
        {state === "permission" && <div className="text-white text-sm">正在授权...</div>}
        {state === "idle" && (
          <div className="text-white/60 text-xs text-center px-4">
            点击"开始录制"启动摄像头。视频仅用于 AI 评估,不会公开分享。
          </div>
        )}
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded" data-testid="video-error">
          {error} — 你也可以直接输入文字回答。
        </div>
      )}
    </div>
  );
}

function pickVideoMime(): string {
  if (typeof MediaRecorder === "undefined") return "video/webm";
  const candidates = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4"];
  for (const c of candidates) {
    if (MediaRecorder.isTypeSupported(c)) return c;
  }
  return "video/webm";
}

async function uploadToBackend(
  blob: Blob,
  interviewId: string,
  mime: string,
  onProgress?: (pct: number) => void
): Promise<void> {
  const token = localStorage.getItem("sb_token") || "";
  // 1) 申请 upload-url
  const t = await fetch(`/api/ai-interview/${interviewId}/upload-url?mime=${encodeURIComponent(mime)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!t.ok) throw new Error("无法申请上传 URL");
  const ticket = await t.json();
  // 2) PUT 到签名 URL
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(ticket.method || "PUT", ticket.upload_url, true);
    if (ticket.headers) {
      Object.entries(ticket.headers as Record<string, string>).forEach(([k, v]) => {
        xhr.setRequestHeader(k, v);
      });
    }
    xhr.setRequestHeader("Content-Type", mime);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(`upload failed: ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("network error"));
    xhr.send(blob);
  });
}
