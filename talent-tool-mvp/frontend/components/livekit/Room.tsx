"use client";

/**
 * LiveKit Room — T2204.
 *
 * 集成 livekit-client:
 *  - 视频 / 音频流
 *  - 加入 / 离开 / 静音
 *  - 屏幕共享
 *
 * 依赖:
 *   npm install livekit-client @livekit/components-react @livekit/components-styles
 *
 * 后端依赖:
 *   POST /api/livekit/token  返回 { token, livekit_url, room_name, identity }
 *
 * 设计:
 *  - 服务端渲染友好 (默认关闭自动连接)
 *  - 错误降级: 没有 livekit-client 时显示 mock UI
 *  - 支持屏幕共享 + 摄像头切换
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface Props {
  roomName: string;
  identity: string;
  authToken?: string;
  onLeave?: () => void;
  autoConnect?: boolean;
}

type Phase = "idle" | "connecting" | "connected" | "disconnected" | "error";

interface TokenInfo {
  token: string;
  livekit_url: string;
  room_name: string;
  identity: string;
  expires_at: number;
}

export default function LiveKitRoom({
  roomName,
  identity,
  authToken,
  onLeave,
  autoConnect = false,
}: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [tokenInfo, setTokenInfo] = useState<TokenInfo | null>(null);
  const [muted, setMuted] = useState(false);
  const [cameraOn, setCameraOn] = useState(true);
  const [screenSharing, setScreenSharing] = useState(false);
  const [participants, setParticipants] = useState<
    Array<{ identity: string; speaking: boolean }>
  >([]);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  // Hold livekit Room instance via any (livekit-client may not be installed)
  const roomRef = useRef<unknown>(null);

  const fetchToken = useCallback(async (): Promise<TokenInfo | null> => {
    try {
      const r = await fetch("/api/livekit/token", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({ room_name: roomName, identity, ttl_seconds: 3600 }),
      });
      if (!r.ok) throw new Error(await r.text());
      return (await r.json()) as TokenInfo;
    } catch (e) {
      setError(`token fetch failed: ${(e as Error).message}`);
      return null;
    }
  }, [roomName, identity, authToken]);

  const connect = useCallback(async () => {
    setPhase("connecting");
    setError(null);
    const tok = await fetchToken();
    if (!tok) {
      setPhase("error");
      return;
    }
    setTokenInfo(tok);

    // 动态 import livekit-client (客户端 + 安装时才尝试)
    try {
      // @ts-expect-error - 动态加载,若未安装会走 fallback
      const mod = await import("livekit-client").catch(() => null);
      if (!mod || !mod.Room) {
        setError("livekit-client 未安装,显示 mock 视频");
        setPhase("connected");
        return;
      }
      const Room_ = mod.Room as new (opts: Record<string, unknown>) => unknown;
      const room = new Room_({
        adaptiveStream: true,
        dynacast: true,
        publishDefaults: { simulcast: true },
      });
      roomRef.current = room;
      // 绑定事件
      const r = room as {
        on: (event: string, cb: (...args: unknown[]) => void) => void;
        connect: (url: string, token: string) => Promise<void>;
        localParticipant: { setCameraEnabled: (b: boolean) => Promise<void> };
      };
      r.on("connected", () => setPhase("connected"));
      r.on("disconnected", () => setPhase("disconnected"));
      r.on("participantConnected", (p: unknown) => {
        const pp = p as { identity?: string };
        setParticipants((prev) => [
          ...prev,
          { identity: pp.identity || "anon", speaking: false },
        ]);
      });
      r.on("participantDisconnected", (p: unknown) => {
        const pp = p as { identity?: string };
        setParticipants((prev) => prev.filter((x) => x.identity !== pp.identity));
      });

      await r.connect(tok.livekit_url, tok.token);
      await r.localParticipant.setCameraEnabled(true);
    } catch (e) {
      setError(`LiveKit 连接失败: ${(e as Error).message}`);
      setPhase("error");
    }
  }, [fetchToken]);

  const disconnect = useCallback(async () => {
    const room = roomRef.current as
      | { disconnect?: () => Promise<void> | void }
      | null;
    if (room?.disconnect) {
      try {
        await room.disconnect();
      } catch {
        // ignore
      }
    }
    roomRef.current = null;
    setPhase("disconnected");
    setParticipants([]);
    onLeave?.();
  }, [onLeave]);

  const toggleMute = useCallback(async () => {
    const room = roomRef.current as
      | { localParticipant?: { setMicrophoneEnabled?: (b: boolean) => Promise<void> } }
      | null;
    if (room?.localParticipant?.setMicrophoneEnabled) {
      await room.localParticipant.setMicrophoneEnabled(muted);
    }
    setMuted((m) => !m);
  }, [muted]);

  const toggleCamera = useCallback(async () => {
    const room = roomRef.current as
      | { localParticipant?: { setCameraEnabled?: (b: boolean) => Promise<void> } }
      | null;
    if (room?.localParticipant?.setCameraEnabled) {
      await room.localParticipant.setCameraEnabled(!cameraOn);
    }
    setCameraOn((c) => !c);
  }, [cameraOn]);

  const toggleScreenShare = useCallback(async () => {
    const room = roomRef.current as
      | {
          localParticipant?: {
            setScreenShareEnabled?: (b: boolean) => Promise<void>;
          };
        }
      | null;
    if (room?.localParticipant?.setScreenShareEnabled) {
      await room.localParticipant.setScreenShareEnabled(!screenSharing);
    }
    setScreenSharing((s) => !s);
  }, [screenSharing]);

  useEffect(() => {
    if (autoConnect) {
      connect();
    }
    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 本地视频预览 (mock 时显示摄像头)
  useEffect(() => {
    if (phase !== "connected") return;
    let stream: MediaStream | null = null;
    if (cameraOn && !tokenInfo) {
      navigator.mediaDevices
        ?.getUserMedia({ video: true, audio: !muted })
        .then((s) => {
          stream = s;
          if (videoRef.current) {
            videoRef.current.srcObject = s;
          }
        })
        .catch(() => undefined);
    }
    return () => {
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [phase, cameraOn, muted, tokenInfo]);

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-slate-900">LiveKit 房间</span>
          <span className="text-xs text-slate-500">
            {roomName} · {identity}
          </span>
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-xs ${
            phase === "connected"
              ? "bg-emerald-100 text-emerald-700"
              : phase === "error"
              ? "bg-rose-100 text-rose-700"
              : "bg-slate-100 text-slate-600"
          }`}
        >
          {phase === "idle" && "未连接"}
          {phase === "connecting" && "连接中…"}
          {phase === "connected" && "已连接"}
          {phase === "disconnected" && "已离开"}
          {phase === "error" && "错误"}
        </span>
      </div>

      <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-slate-900">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="h-full w-full object-cover"
        />
        {phase !== "connected" && (
          <div className="absolute inset-0 flex items-center justify-center text-slate-400">
            <div className="text-center">
              <div className="text-4xl">📡</div>
              <div className="mt-2 text-sm">
                {phase === "idle" && "点击下方按钮加入房间"}
                {phase === "connecting" && "正在连接…"}
                {phase === "error" && (error || "连接失败")}
                {phase === "disconnected" && "已断开"}
              </div>
            </div>
          </div>
        )}
      </div>

      {error && phase === "connected" && (
        <div className="rounded-md bg-amber-50 px-3 py-1.5 text-xs text-amber-700">
          {error} (显示 mock 视频)
        </div>
      )}

      {participants.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
            参与者 ({participants.length + 1})
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <span className="rounded-full bg-slate-900 px-2 py-0.5 text-xs text-white">
              {identity} (你)
            </span>
            {participants.map((p) => (
              <span
                key={p.identity}
                className={`rounded-full px-2 py-0.5 text-xs ${
                  p.speaking
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-slate-100 text-slate-700"
                }`}
              >
                {p.identity}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {phase === "idle" || phase === "disconnected" ? (
          <button
            type="button"
            onClick={connect}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          >
            加入房间
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={toggleMute}
              className={`rounded-lg px-3 py-2 text-sm ${
                muted
                  ? "bg-rose-100 text-rose-700"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              {muted ? "🔇 取消静音" : "🎤 静音"}
            </button>
            <button
              type="button"
              onClick={toggleCamera}
              className={`rounded-lg px-3 py-2 text-sm ${
                !cameraOn
                  ? "bg-rose-100 text-rose-700"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              {cameraOn ? "📹 关摄像头" : "📷 开摄像头"}
            </button>
            <button
              type="button"
              onClick={toggleScreenShare}
              className={`rounded-lg px-3 py-2 text-sm ${
                screenSharing
                  ? "bg-sky-100 text-sky-700"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              {screenSharing ? "🖥 停止共享" : "🖥 共享屏幕"}
            </button>
            <button
              type="button"
              onClick={disconnect}
              className="rounded-lg bg-rose-600 px-3 py-2 text-sm font-medium text-white hover:bg-rose-700"
            >
              离开
            </button>
          </>
        )}
      </div>
    </div>
  );
}