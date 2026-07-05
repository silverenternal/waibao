"use client";

import { useState } from "react";
import { useAgent } from "../realtime/SocketProvider";

type Emotion = "joy" | "sadness" | "anger" | "fear" | "surprise" | "disgust" | "neutral";

const EMOTION_LABEL: Record<Emotion, string> = {
  joy: "开心",
  sadness: "难过",
  anger: "愤怒",
  fear: "焦虑",
  surprise: "惊讶",
  disgust: "厌恶",
  neutral: "平静",
};

const EMOTION_COLOR: Record<Emotion, string> = {
  joy: "#10b981",
  sadness: "#6366f1",
  anger: "#ef4444",
  fear: "#f59e0b",
  surprise: "#8b5cf6",
  disgust: "#84cc16",
  neutral: "#94a3b8",
};

export default function JobseekerHome() {
  const { invoke, streaming, currentChunk, connected } = useAgent();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: string; text: string; emotion?: string }[]>([]);
  const [emotion, setEmotion] = useState<Emotion | null>(null);

  async function send() {
    if (!input.trim()) return;
    const userMsg = input;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: userMsg }]);

    // 1. 情感检测(快速)
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/emotion/detect?text=" + encodeURIComponent(userMsg), {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await r.json();
      setEmotion(data.emotion);
    } catch {}

    // 2. 调用 agent 流式响应
    try {
      const reply = await invoke(userMsg);
      setMessages((m) => [...m, { role: "agent", text: reply }]);
      setEmotion(null);
    } catch (e: any) {
      setMessages((m) => [...m, { role: "agent", text: "网络异常: " + e.message }]);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      {/* 顶部状态栏 */}
      <div className="bg-white border-b px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">我的空间</h1>
          <span className="text-xs text-slate-500">求职者知心朋友</span>
        </div>
        <div className="flex items-center gap-3">
          {emotion && (
            <span
              className="px-3 py-1 rounded-full text-xs text-white font-medium"
              style={{ background: EMOTION_COLOR[emotion] }}
            >
              {EMOTION_LABEL[emotion]}
            </span>
          )}
          <span
            className={`px-2 py-1 rounded text-xs ${
              connected ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
            }`}
          >
            {connected ? "已连接" : "未连接"}
          </span>
        </div>
      </div>

      {/* 主对话区 */}
      <div className="max-w-3xl mx-auto p-6 space-y-4">
        {/* 欢迎卡片 */}
        {messages.length === 0 && (
          <div className="bg-white rounded-2xl shadow-sm p-8 text-center">
            <div className="text-5xl mb-4">👋</div>
            <h2 className="text-2xl font-medium mb-2">你好,我是你的智能体助手</h2>
            <p className="text-slate-600 mb-6">可以跟我说工作内容、心情、困惑,我会倾听并给出建议。</p>
            <div className="grid grid-cols-2 gap-3">
              {[
                { icon: "📝", label: "写日记", text: "今天做了一个 AI 项目,挺有收获" },
                { icon: "💼", label: "查看匹配", text: "看看有哪些工作适合我" },
                { icon: "🎯", label: "职业规划", text: "我想做 AI 产品经理,该怎么规划" },
                { icon: "💬", label: "聊聊心情", text: "今天有点焦虑" },
              ].map((s) => (
                <button
                  key={s.label}
                  onClick={() => setInput(s.text)}
                  className="border rounded-xl p-4 hover:bg-slate-50 text-left"
                >
                  <div className="text-2xl">{s.icon}</div>
                  <div className="text-sm font-medium mt-1">{s.label}</div>
                  <div className="text-xs text-slate-500 mt-1">{s.text}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 对话历史 */}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`rounded-2xl p-4 ${
              m.role === "user" ? "bg-blue-50 ml-12" : "bg-white shadow-sm mr-12"
            }`}
          >
            <div className="text-xs text-slate-400 mb-1">
              {m.role === "user" ? "我" : "智能体"}
            </div>
            <div className="whitespace-pre-wrap">{m.text}</div>
          </div>
        ))}

        {/* 流式输出 */}
        {streaming && currentChunk && (
          <div className="bg-white shadow-sm rounded-2xl p-4 mr-12">
            <div className="text-xs text-slate-400 mb-1">智能体 · 实时</div>
            <div className="whitespace-pre-wrap">{currentChunk}</div>
            <div className="text-xs text-slate-400 mt-2 animate-pulse">▍</div>
          </div>
        )}
      </div>

      {/* 输入区 */}
      <div className="fixed bottom-0 inset-x-0 bg-white border-t p-4">
        <div className="max-w-3xl mx-auto flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send())}
            placeholder="跟智能体说点什么..."
            className="flex-1 px-4 py-3 rounded-xl border focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={streaming}
          />
          <button
            onClick={send}
            disabled={streaming || !input.trim()}
            className="px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50"
          >
            {streaming ? "等待中..." : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}