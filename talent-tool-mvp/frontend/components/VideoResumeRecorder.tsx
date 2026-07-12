"use client";

/**
 * VideoResumeRecorder — T2203.
 *
 * 录制 30~60 秒视频简历:
 *  - 实时预览 + 倒计时
 *  - 完成后预览 + 重新录制
 *  - 上传到 /api/uploads 后回传 video_url
 */

import { useEffect, useRef, useState } from "react";

interface Props {
  onUploaded?: (info: { video_url: string; duration_sec: number }) => void;
  minDuration?: number; // 默认 30s
  maxDuration?: number; // 默认 60s
  authToken?: string;
}

type Phase = "idle" | "recording" | "preview" | "uploading" | "done" | "error";

export default function VideoResumeRecorder({
  onUploaded,
  minDuration = 30,
  maxDuration = 60,
  authToken,
}: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [secondsLeft, setSecondsLeft] = useState(maxDuration);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const liveRef = useRef<HTMLVideoElement | null>(null);
  const previewRef = useRef<HTMLVideoElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      // cleanup
      if (tickRef.current) clearInterval(tickRef.current);
      stream?.getTracks().forEach((t) => t.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startCamera = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: { width: 1280, height: 720, facingMode: "user" },
        audio: true,
      });
      setStream(s);
      if (liveRef.current) {
        liveRef.current.srcObject = s;
        liveRef.current.muted = true;
        await liveRef.current.play();
      }
    } catch (e) {
      setErrorMsg(`无法访问摄像头:${(e as Error).message}`);
      setPhase("error");
    }
  };

  const stopCamera = () => {
    stream?.getTracks().forEach((t) => t.stop());
    setStream(null);
    if (liveRef.current) liveRef.current.srcObject = null;
  };

  const handleStart = async () => {
    setErrorMsg(null);
    setVideoUrl(null);
    setBlob(null);
    chunksRef.current = [];
    setSecondsLeft(maxDuration);
    setPhase("recording");
    await startCamera();
    const recorder = new MediaRecorder(stream!, { mimeType: "video/webm" });
    recorderRef.current = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      const b = new Blob(chunksRef.current, { type: "video/webm" });
      const url = URL.createObjectURL(b);
      setBlob(b);
      setVideoUrl(url);
      stopCamera();
      setPhase("preview");
    };
    recorder.start(1000);
    tickRef.current = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          if (tickRef.current) clearInterval(tickRef.current);
          recorder.stop();
          return 0;
        }
        return s - 1;
      });
    }, 1000);
  };

  const handleStop = () => {
    if (tickRef.current) clearInterval(tickRef.current);
    recorderRef.current?.stop();
  };

  const handleRetake = async () => {
    if (videoUrl) URL.revokeObjectURL(videoUrl);
    setVideoUrl(null);
    setBlob(null);
    setPhase("idle");
    setSecondsLeft(maxDuration);
  };

  const handleUpload = async () => {
    if (!blob) return;
    setPhase("uploading");
    try {
      const fd = new FormData();
      fd.append("file", blob, `video_resume_${Date.now()}.webm`);
      fd.append("kind", "video_resume");
      const r = await fetch("/api/uploads/video", {
        method: "POST",
        headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
        body: fd,
      });
      if (!r.ok) throw new Error(await r.text());
      const data = (await r.json()) as { url?: string; public_url?: string };
      const url = data.public_url || data.url || "";
      if (!url) throw new Error("no url in response");
      const duration = maxDuration - secondsLeft;
      onUploaded?.({ video_url: url, duration_sec: duration });
      setPhase("done");
    } catch (e) {
      setErrorMsg(`上传失败:${(e as Error).message}`);
      setPhase("error");
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-slate-900">录制视频简历</h3>
        <span className="text-xs text-slate-500">
          建议时长 {minDuration}~{maxDuration} 秒
        </span>
      </div>

      <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-slate-900">
        {phase === "recording" ? (
          <video ref={liveRef} className="h-full w-full object-cover" playsInline />
        ) : videoUrl ? (
          <video
            ref={previewRef}
            src={videoUrl}
            controls
            className="h-full w-full object-cover"
            playsInline
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-slate-400">
            <div className="text-center">
              <div className="text-4xl">🎥</div>
              <div className="mt-2 text-sm">点击下方按钮开始录制</div>
            </div>
          </div>
        )}

        {phase === "recording" && (
          <div className="absolute right-3 top-3 flex items-center gap-2 rounded-full bg-rose-600 px-3 py-1 text-xs font-medium text-white">
            <span className="h-2 w-2 animate-pulse rounded-full bg-white" />
            录制中 · {secondsLeft}s
          </div>
        )}
      </div>

      {errorMsg && (
        <div className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{errorMsg}</div>
      )}

      <div className="flex flex-wrap gap-2">
        {phase === "idle" && (
          <button
            type="button"
            onClick={handleStart}
            className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700"
          >
            开始录制
          </button>
        )}
        {phase === "recording" && (
          <button
            type="button"
            onClick={handleStop}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            停止 ({secondsLeft}s)
          </button>
        )}
        {phase === "preview" && (
          <>
            <button
              type="button"
              onClick={handleRetake}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              重新录制
            </button>
            <button
              type="button"
              onClick={handleUpload}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
            >
              上传视频
            </button>
          </>
        )}
        {phase === "uploading" && (
          <span className="text-sm text-slate-500">上传中…</span>
        )}
        {phase === "done" && (
          <span className="text-sm text-emerald-600">上传成功,可提交评估</span>
        )}
      </div>
    </div>
  );
}