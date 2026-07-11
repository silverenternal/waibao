"use client";

/**
 * VoiceWaveform — 轻量波形可视化组件 (T701).
 *
 * 纯 Canvas + AnalyserNode,不需要外部图表库。
 * - 接收 analyser 引用,渲染实时波形条
 * - 同时支持静态的 peak bars (录音回放)
 *
 * Props:
 *   - analyser: MediaStreamAudioSourceNode AnalyserNode | null
 *   - peaks?:    number[]   (0..1, 用于回放/历史峰值)
 *   - height?:   number     (px)
 *   - color?:    string
 */

import { useEffect, useRef } from "react";

export interface VoiceWaveformProps {
  analyser?: AnalyserNode | null;
  peaks?: number[];
  height?: number;
  color?: string;
  className?: string;
}

export default function VoiceWaveform({
  analyser,
  peaks,
  height = 64,
  color = "#0ea5e9",
  className = "",
}: VoiceWaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const drawFromAnalyser = () => {
      if (!analyser) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const w = canvas.width;
      const h = canvas.height;
      const buf = new Uint8Array(analyser.fftSize);
      analyser.getByteTimeDomainData(buf);

      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = color + "22";
      ctx.fillRect(0, 0, w, h);

      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      const step = w / buf.length;
      for (let i = 0; i < buf.length; i++) {
        const v = buf[i] / 128.0; // 0..2
        const y = (v * h) / 2;
        if (i === 0) ctx.moveTo(0, y);
        else ctx.lineTo(i * step, y);
      }
      ctx.stroke();
      rafRef.current = requestAnimationFrame(drawFromAnalyser);
    };

    const drawFromPeaks = () => {
      if (!peaks || peaks.length === 0) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = color;
      const barWidth = Math.max(2, w / peaks.length - 1);
      for (let i = 0; i < peaks.length; i++) {
        const barHeight = Math.max(2, peaks[i] * h * 0.9);
        const x = i * (barWidth + 1);
        const y = (h - barHeight) / 2;
        ctx.fillRect(x, y, barWidth, barHeight);
      }
    };

    if (analyser) {
      drawFromAnalyser();
    } else if (peaks && peaks.length > 0) {
      drawFromPeaks();
    }

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [analyser, peaks, color]);

  return (
    <canvas
      ref={canvasRef}
      width={480}
      height={height}
      data-testid="voice-waveform"
      className={`w-full rounded bg-slate-100 ${className}`}
      style={{ height }}
    />
  );
}