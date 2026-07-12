"use client";

/**
 * 语音日记主页面 (T701).
 *
 * 流程:
 *   1. 用户点击 VoiceRecorder 录音
 *   2. 转写成功后自动用 transcript 提交 /api/voice/submit
 *   3. 触发 Daily Journal Agent + Emotion Agent
 *   4. 展示 AI 评分、建议、情绪标签
 *
 * 用户也可以改用文本输入兜底。
 */

import { useState } from "react";
import VoiceRecorder from "@/components/VoiceRecorder";
import {
  transcribeAudio,
  submitVoiceJournal,
  type VoiceSubmitResponse,
} from "@/lib/api-voice";

export default function VoiceJournalPage() {
  const [text, setText] = useState("");
  const [provider, setProvider] = useState<string>("");
  const [transcribeError, setTranscribeError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<VoiceSubmitResponse | null>(null);

  async function handleTranscript(transcript: string, usedProvider: string) {
    setTranscribeError(null);
    setText(transcript);
    setProvider(usedProvider);
    if (!transcript.trim()) {
      setTranscribeError("没有识别到内容,请重试或改用文本");
      return;
    }
    await submit(transcript, usedProvider);
  }

  async function submit(transcript: string, usedProvider: string) {
    setSubmitting(true);
    setResult(null);
    try {
      const data = await submitVoiceJournal(transcript, {
        provider: usedProvider,
      });
      setResult(data);
    } catch (e: any) {
      setTranscribeError(e?.message || "提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b px-6 py-4">
        <h1 className="text-xl font-semibold">🎙️ 语音日记</h1>
        <p className="text-sm text-slate-500 mt-1">
          说话即可,Whisper 自动转写,失败时降级到 aliyun_stt
        </p>
      </div>

      <div className="max-w-2xl mx-auto p-6 space-y-6">
        <VoiceRecorder
          onTranscript={handleTranscript}
          onError={(e) => setTranscribeError(e)}
        />

        {/* 文本兜底输入 */}
        <div className="bg-white border rounded-lg p-4 space-y-2">
          <label className="text-sm font-medium">或直接输入文字 (兜底)</label>
          <textarea
            data-testid="voice-text-fallback"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={5}
            className="w-full border rounded p-2 text-sm"
            placeholder="今天遇到什么? 心情如何?"
          />
          <div className="flex justify-between items-center">
            <div className="text-xs text-slate-500">
              {provider && <span>上次转写 provider: {provider}</span>}
            </div>
            <button
              data-testid="voice-submit-text"
              onClick={() => submit(text, "manual")}
              disabled={!text.trim() || submitting}
              className="px-3 py-1.5 text-sm rounded bg-sky-600 text-white disabled:bg-slate-300"
            >
              {submitting ? "提交中..." : "提交日记"}
            </button>
          </div>
        </div>

        {transcribeError && (
          <div className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded">
            {transcribeError}
          </div>
        )}

        {result && (
          <div className="bg-white border rounded-lg p-4 space-y-3" data-testid="voice-result">
            <div>
              <div className="text-sm font-medium">AI 评分</div>
              <div className="text-base">{result.journal.rating || "—"}</div>
            </div>
            {result.journal.advice && (
              <div>
                <div className="text-sm font-medium">建议</div>
                <div className="text-sm text-slate-700 whitespace-pre-wrap">
                  {result.journal.advice}
                </div>
              </div>
            )}
            {!!result.journal.warnings?.length && (
              <div>
                <div className="text-sm font-medium text-amber-700">提醒</div>
                <ul className="list-disc list-inside text-sm text-amber-700">
                  {result.journal.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
            {!!result.journal.action_items?.length && (
              <div>
                <div className="text-sm font-medium">行动项</div>
                <ul className="list-disc list-inside text-sm text-slate-700">
                  {result.journal.action_items.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
            {result.emotion?.summary && (
              <div>
                <div className="text-sm font-medium">情绪分析</div>
                <div className="text-sm text-slate-700">{result.emotion.summary}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}