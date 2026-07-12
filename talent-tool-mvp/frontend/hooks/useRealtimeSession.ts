"use client";

/**
 * useRealtimeSession — T2201 client-side hook for GPT-4o Realtime.
 *
 * Provides:
 *   - session creation (POST /api/realtime-v2/sessions)
 *   - WebSocket lifecycle (connect / disconnect / interrupt)
 *   - audio capture (AudioContext + PCM16 frames, 24kHz mono)
 *   - audio playback (queue incoming audio deltas)
 *   - text stream + transcript accumulation
 *   - emotion estimation from audio features (RMS + zero-crossing)
 *   - metrics (latency, audio seconds, token usage)
 *
 * Usage:
 *   const rt = useRealtimeSession();
 *   await rt.start();
 *   rt.pushText("hi");
 *   await rt.stop();
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type RealtimeEvent =
  | { type: "ready"; session_id: string; model: string; voice: string; ts: number }
  | { type: "connected"; session_id: string; user_id: string }
  | { type: "vad_speech_start" | "vad_speech_stop" | "audio_committed" | "closed" | "ready"; ts: number }
  | { type: "text_delta"; delta: string; response_id?: string; ts: number }
  | { type: "text_done"; text: string; response_id?: string; ts: number }
  | { type: "audio_delta"; audio: string; response_id?: string; ts: number }
  | { type: "response_done"; usage?: any; ts: number }
  | { type: "user_text"; text: string; ts: number }
  | { type: "function_call"; name: string; call_id: string; arguments: any; ts: number }
  | { type: "interrupted"; ts: number }
  | { type: "error"; message: string; ts?: number };

export type Emotion = "calm" | "excited" | "nervous" | "neutral";

export interface RealtimeMetrics {
  firstAudioLatencyMs: number | null;
  audioInputChunks: number;
  audioOutputChunks: number;
  functionCalls: number;
  interruptions: number;
  usage: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    audio_input_seconds: number;
    audio_output_seconds: number;
  };
}

export interface UseRealtimeSessionResult {
  state: "idle" | "connecting" | "ready" | "speaking" | "ended" | "error";
  sessionId: string | null;
  transcript: { role: "user" | "assistant"; text: string; ts: number }[];
  partialText: string;
  error: string | null;
  metrics: RealtimeMetrics;
  emotion: Emotion;
  audioLevel: number; // 0..1 RMS
  start: (opts?: { model?: string; voice?: string; instructions?: string }) => Promise<void>;
  stop: () => Promise<void>;
  interrupt: () => void;
  pushText: (text: string) => void;
  pushAudioLevel: (rms: number) => void;
}

const DEFAULT_MODEL = "gpt-4o-realtime-preview";
const DEFAULT_VOICE = "alloy";
const SAMPLE_RATE = 24000;
const FRAME_MS = 100; // 100ms frames

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("sb_token") || "";
}

function inferEmotion(rms: number, zcr: number): Emotion {
  if (rms < 0.01) return "calm";
  if (rms > 0.18 && zcr > 0.3) return "excited";
  if (rms < 0.06 && zcr > 0.25) return "nervous";
  return "neutral";
}

export function useRealtimeSession(): UseRealtimeSessionResult {
  const [state, setState] = useState<UseRealtimeSessionResult["state"]>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<UseRealtimeSessionResult["transcript"]>([]);
  const [partialText, setPartialText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [emotion, setEmotion] = useState<Emotion>("neutral");
  const [audioLevel, setAudioLevel] = useState(0);
  const [metrics, setMetrics] = useState<RealtimeMetrics>({
    firstAudioLatencyMs: null,
    audioInputChunks: 0,
    audioOutputChunks: 0,
    functionCalls: 0,
    interruptions: 0,
    usage: {
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
      audio_input_seconds: 0,
      audio_output_seconds: 0,
    },
  });

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const playbackQueueRef = useRef<Float32Array[]>([]);
  const playingRef = useRef(false);
  const stateRef = useRef(state);
  stateRef.current = state;
  const emotionHistoryRef = useRef<{ rms: number; zcr: number; t: number }[]>([]);
  const startedAtRef = useRef<number | null>(null);

  // --------------------------------------------------------------------
  // Audio playback
  // --------------------------------------------------------------------
  const ensurePlaybackCtx = useCallback(() => {
    if (!playbackCtxRef.current) {
      const AC: typeof AudioContext =
        (window as any).AudioContext || (window as any).webkitAudioContext;
      playbackCtxRef.current = new AC({ sampleRate: SAMPLE_RATE });
    }
    return playbackCtxRef.current;
  }, []);

  const enqueueAudio = useCallback(
    (b64: string) => {
      if (typeof window === "undefined") return;
      const bin = atob(b64);
      const len = bin.length;
      const buf = new Float32Array(len / 2);
      const view = new DataView(new ArrayBuffer(len));
      for (let i = 0; i < len; i++) view.setUint8(i, bin.charCodeAt(i));
      for (let i = 0; i < len / 2; i++) {
        const s = view.getInt16(i * 2, true);
        buf[i] = s / 32768;
      }
      playbackQueueRef.current.push(buf);
      setMetrics((m) => ({ ...m, audioOutputChunks: m.audioOutputChunks + 1 }));
      if (!playingRef.current) drainPlayback();
    },
    [],
  );

  const drainPlayback = useCallback(() => {
    const ctx = ensurePlaybackCtx();
    if (playbackQueueRef.current.length === 0) {
      playingRef.current = false;
      return;
    }
    playingRef.current = true;
    const buf = playbackQueueRef.current.shift()!;
    const audioBuf = ctx.createBuffer(1, buf.length, SAMPLE_RATE);
    audioBuf.copyToChannel(buf as Float32Array<ArrayBuffer>, 0);
    const src = ctx.createBufferSource();
    src.buffer = audioBuf;
    src.connect(ctx.destination);
    src.onended = () => drainPlayback();
    src.start();
    setMetrics((m) => ({
      ...m,
      usage: {
        ...m.usage,
        audio_output_seconds: m.usage.audio_output_seconds + buf.length / SAMPLE_RATE,
      },
    }));
  }, [ensurePlaybackCtx]);

  // --------------------------------------------------------------------
  // Audio capture
  // --------------------------------------------------------------------
  const startCapture = useCallback(async () => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      throw new Error("浏览器不支持麦克风,请改用文本输入");
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: SAMPLE_RATE, channelCount: 1, echoCancellation: true },
    });
    mediaStreamRef.current = stream;
    const ctx = ensurePlaybackCtx();
    audioCtxRef.current = ctx;
    const source = ctx.createMediaStreamSource(stream);
    sourceNodeRef.current = source;
    // Use ScriptProcessor (deprecated but widely supported); for production,
    // swap to AudioWorklet for better performance.
    const processor = ctx.createScriptProcessor(2048, 1, 1);
    processorRef.current = processor;
    let lastSent = 0;
    let zeroCrossings = 0;
    let lastSample = 0;
    let rmsAccum = 0;
    let rmsCount = 0;
    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      // Compute RMS + zero-crossing rate
      let sum = 0;
      zeroCrossings = 0;
      for (let i = 0; i < input.length; i++) {
        const v = input[i];
        sum += v * v;
        if ((v >= 0) !== (lastSample >= 0) && Math.abs(v - lastSample) > 0.001) {
          zeroCrossings += 1;
        }
        lastSample = v;
      }
      const rms = Math.sqrt(sum / input.length);
      const zcr = zeroCrossings / input.length;
      rmsAccum += rms;
      rmsCount += 1;
      setAudioLevel(Math.min(1, rms * 4));
      const now = performance.now();
      if (now - lastSent > FRAME_MS) {
        lastSent = now;
        // Convert to PCM16 base64
        const pcm = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
          const s = Math.max(-1, Math.min(1, input[i]));
          pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        const u8 = new Uint8Array(pcm.buffer);
        let bin = "";
        for (let i = 0; i < u8.length; i++) bin += String.fromCharCode(u8[i]);
        const b64 = btoa(bin);
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "audio", data: b64 }));
          setMetrics((m) => ({
            ...m,
            audioInputChunks: m.audioInputChunks + 1,
            firstAudioLatencyMs:
              m.firstAudioLatencyMs ??
              (startedAtRef.current
                ? Math.round(performance.now() - startedAtRef.current)
                : null),
            usage: {
              ...m.usage,
              audio_input_seconds:
                m.usage.audio_input_seconds + (input.length / SAMPLE_RATE),
            },
          }));
        }
      }
      // Update emotion every ~500ms
      const t = performance.now();
      emotionHistoryRef.current.push({ rms, zcr, t });
      emotionHistoryRef.current = emotionHistoryRef.current.filter(
        (h) => t - h.t < 1500,
      );
      if (emotionHistoryRef.current.length % 8 === 0) {
        const avgRms =
          emotionHistoryRef.current.reduce((s, h) => s + h.rms, 0) /
          Math.max(1, emotionHistoryRef.current.length);
        const avgZcr =
          emotionHistoryRef.current.reduce((s, h) => s + h.zcr, 0) /
          Math.max(1, emotionHistoryRef.current.length);
        setEmotion(inferEmotion(avgRms, avgZcr));
      }
    };
    source.connect(processor);
    processor.connect(ctx.destination); // required for some browsers
  }, [ensurePlaybackCtx]);

  const stopCapture = useCallback(() => {
    if (processorRef.current) {
      try {
        processorRef.current.disconnect();
      } catch {}
      processorRef.current = null;
    }
    if (sourceNodeRef.current) {
      try {
        sourceNodeRef.current.disconnect();
      } catch {}
      sourceNodeRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
  }, []);

  // --------------------------------------------------------------------
  // Connection lifecycle
  // --------------------------------------------------------------------
  const start = useCallback(
    async (opts?: { model?: string; voice?: string; instructions?: string }) => {
      setError(null);
      setState("connecting");
      setTranscript([]);
      setPartialText("");
      setMetrics({
        firstAudioLatencyMs: null,
        audioInputChunks: 0,
        audioOutputChunks: 0,
        functionCalls: 0,
        interruptions: 0,
        usage: {
          input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
          audio_input_seconds: 0,
          audio_output_seconds: 0,
        },
      });
      try {
        const token = getToken();
        const r = await fetch("/api/realtime-v2/sessions", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            model: opts?.model || DEFAULT_MODEL,
            voice: opts?.voice || DEFAULT_VOICE,
            instructions: opts?.instructions,
            modalities: ["audio", "text"],
            input_audio_format: "pcm16",
            output_audio_format: "pcm16",
          }),
        });
        if (!r.ok) throw new Error(`session create failed: ${r.status} ${await r.text()}`);
        const data = await r.json();
        setSessionId(data.id);
        startedAtRef.current = performance.now();
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        const host = window.location.hostname;
        const port = (window.location.port && window.location.port !== "3000")
          ? `:${window.location.port}`
          : ":8000";
        const wsUrl = `${proto}://${host}${port}/api/realtime-v2/ws/${data.id}?token=${encodeURIComponent(
          token.startsWith("dev:") || token.length === 0 ? "dev:me" : token,
        )}`;
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;
        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data) as RealtimeEvent;
            handleEvent(msg);
          } catch (err) {
            // ignore
          }
        };
        ws.onerror = () => {
          setError("WebSocket 错误");
          setState("error");
        };
        ws.onclose = () => {
          if (stateRef.current !== "ended") {
            setState("ended");
          }
        };
        // Start mic capture after socket opens
        await new Promise<void>((resolve) => {
          ws.onopen = () => resolve();
        });
        await startCapture();
      } catch (e: any) {
        setError(e?.message || "启动失败");
        setState("error");
      }
    },
    [startCapture],
  );

  const handleEvent = useCallback(
    (msg: RealtimeEvent) => {
      switch (msg.type) {
        case "connected":
          break;
        case "ready":
          setState("ready");
          break;
        case "vad_speech_start":
        case "vad_speech_stop":
        case "audio_committed":
          break;
        case "text_delta":
          setPartialText((t) => t + (msg as any).delta);
          setState("speaking");
          break;
        case "text_done":
          setTranscript((arr) => [
            ...arr,
            { role: "assistant", text: (msg as any).text, ts: (msg as any).ts },
          ]);
          setPartialText("");
          setState("ready");
          break;
        case "audio_delta":
          enqueueAudio((msg as any).audio);
          break;
        case "response_done":
          if ((msg as any).usage) {
            setMetrics((m) => ({
              ...m,
              usage: {
                ...m.usage,
                input_tokens: (msg as any).usage.input_tokens ?? m.usage.input_tokens,
                output_tokens: (msg as any).usage.output_tokens ?? m.usage.output_tokens,
                total_tokens:
                  ((msg as any).usage.input_tokens ?? 0) +
                  ((msg as any).usage.output_tokens ?? 0),
              },
            }));
          }
          setState("ready");
          break;
        case "user_text":
          setTranscript((arr) => [
            ...arr,
            { role: "user", text: (msg as any).text, ts: (msg as any).ts },
          ]);
          break;
        case "function_call":
          setMetrics((m) => ({ ...m, functionCalls: m.functionCalls + 1 }));
          break;
        case "interrupted":
          setMetrics((m) => ({ ...m, interruptions: m.interruptions + 1 }));
          setState("ready");
          break;
        case "closed":
          setState("ended");
          break;
        case "error":
          setError((msg as any).message);
          setState("error");
          break;
      }
    },
    [enqueueAudio],
  );

  const stop = useCallback(async () => {
    stopCapture();
    if (wsRef.current) {
      try {
        if (wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "stop" }));
        }
      } catch {}
      try {
        wsRef.current.close();
      } catch {}
      wsRef.current = null;
    }
    setState("ended");
  }, [stopCapture]);

  const interrupt = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "interrupt" }));
    }
  }, []);

  const pushText = useCallback((text: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "text", text }));
    }
  }, []);

  const pushAudioLevel = useCallback((rms: number) => {
    setAudioLevel(Math.min(1, rms * 4));
  }, []);

  useEffect(() => {
    return () => {
      stopCapture();
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {}
      }
    };
  }, [stopCapture]);

  return {
    state,
    sessionId,
    transcript,
    partialText,
    error,
    metrics,
    emotion,
    audioLevel,
    start,
    stop,
    interrupt,
    pushText,
    pushAudioLevel,
  };
}
