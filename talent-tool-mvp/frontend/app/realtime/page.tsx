"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * /realtime — T2201 GPT-4o Realtime 实时语音对话主页.
 *
 * 3D 头像 + 实时波形 + 转写 + 情绪自动检测 + 中断/继续/结束.
 */

import { useState } from "react";
import RealtimeVoice from "@/components/RealtimeVoice";

const VOICES = [
  { value: "alloy", label: "Alloy (中性)" },
  { value: "ash", label: "Ash (稳重)" },
  { value: "ballad", label: "Ballad (温和)" },
  { value: "coral", label: "Coral (活泼)" },
  { value: "echo", label: "Echo (沉稳)" },
  { value: "sage", label: "Sage (理性)" },
  { value: "shimmer", label: "Shimmer (明亮)" },
  { value: "verse", label: "Verse (文学)" },
];

const SCENARIOS = [
  {
    value: "free",
    label: "自由对话",
    instructions:
      "你是一位友善的 AI 助手。请用简洁自然的中文回答用户的问题,保持对话节奏。",
  },
  {
    value: "interview_practice",
    label: "面试练习",
    instructions:
      "你是一位资深技术面试官。请用中文进行模拟面试,逐步深入地提问候选人的项目经验。",
  },
  {
    value: "english_coach",
    label: "英语口语教练",
    instructions:
      "You are a patient English speaking coach. Help the user practise English conversation, correcting mistakes gently.",
  },
  {
    value: "negotiation",
    label: "谈薪模拟",
    instructions:
      "你是一位招聘经理,正在与候选人沟通薪资。请自然、坦诚、循序渐进地推进对话。",
  },
];

export default function RealtimePage() {
  const [voice, setVoice] = useState("alloy");
  const [scenario, setScenario] = useState("free");
  const [finalTranscript, setFinalTranscript] = useState<
    { role: string; text: string }[]
  >([]);

  const scenarioObj = SCENARIOS.find((s) => s.value === scenario) ?? SCENARIOS[0];

  return (
    <ErrorBoundary>(<div className="min-h-screen bg-gradient-to-b from-slate-50 to-sky-50">
        <header className="bg-white border-b px-6 py-4">
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <span aria-hidden>🎙️</span> GPT-4o Realtime · 实时语音对话
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            基于 OpenAI Realtime API, 支持服务端 VAD / 工具调用 / 中断。
          </p>
        </header>
        <div className="max-w-4xl mx-auto p-6 space-y-6">
          <section className="bg-white rounded-2xl shadow-sm p-5 space-y-4">
            <div>
              <h2 className="text-sm font-semibold text-slate-800 mb-2">场景</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {SCENARIOS.map((s) => (
                  <button
                    key={s.value}
                    onClick={() => setScenario(s.value)}
                    aria-pressed={scenario === s.value}
                    className={`px-3 py-2 text-sm rounded-lg border transition ${
                      scenario === s.value
                        ? "border-sky-500 bg-sky-50 text-sky-700"
                        : "border-slate-200 hover:border-slate-400"
                    }`}
                    data-testid={`scenario-${s.value}`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-800 mb-2">声音</h2>
              <div className="flex flex-wrap gap-2">
                {VOICES.map((v) => (
                  <button
                    key={v.value}
                    onClick={() => setVoice(v.value)}
                    aria-pressed={voice === v.value}
                    className={`px-3 py-1.5 text-xs rounded-full border ${
                      voice === v.value
                        ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                        : "border-slate-200 hover:border-slate-400"
                    }`}
                  >
                    {v.label}
                  </button>
                ))}
              </div>
            </div>
          </section>

          <RealtimeVoice
            voice={voice}
            model="gpt-4o-realtime-preview"
            instructions={scenarioObj.instructions}
            onComplete={setFinalTranscript}
          />

          {finalTranscript.length > 0 && (
            <section className="bg-white rounded-2xl shadow-sm p-5 space-y-2">
              <h2 className="text-sm font-semibold text-slate-800">本场对话存档</h2>
              <div className="space-y-1 text-sm text-slate-700 max-h-64 overflow-y-auto">
                {finalTranscript.map((t, i) => (
                  <div
                    key={i}
                    className={`p-2 rounded ${
                      t.role === "user" ? "bg-sky-50" : "bg-slate-50"
                    }`}
                  >
                    <span className="text-xs text-slate-400 mr-2">
                      {t.role === "user" ? "你" : "AI"}
                    </span>
                    {t.text}
                  </div>
                ))}
              </div>
              <button
                onClick={() => setFinalTranscript([])}
                className="text-xs text-slate-500 hover:text-slate-800"
              >
                清空
              </button>
            </section>
          )}
        </div>
      </div>)</ErrorBoundary>
  );
}
