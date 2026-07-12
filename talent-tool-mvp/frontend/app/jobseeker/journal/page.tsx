"use client";

import { useEffect, useState } from "react";

type JournalEntry = {
  id: string;
  journal_date: string;
  content: string;
  mood_score: number | null;
  ai_rating: string | null;
  ai_advice: string | null;
  ai_warnings: string[];
  ai_action_items: string[];
};

export default function JournalPage() {
  const [content, setContent] = useState("");
  const [mood, setMood] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [timeline, setTimeline] = useState<JournalEntry[]>([]);
  const [latestAI, setLatestAI] = useState<{ rating?: string; advice?: string; warnings?: string[]; action_items?: string[] } | null>(null);

  async function loadTimeline() {
    const token = localStorage.getItem("sb_token") || "";
    const r = await fetch("/api/journal/timeline?days=30", {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await r.json();
    setTimeline(data.data || []);
  }

  useEffect(() => { loadTimeline(); }, []);

  async function submit() {
    if (!content.trim()) return;
    setSubmitting(true);
    setLatestAI(null);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/journal", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content, mood_score: mood }),
      });
      const data = await r.json();
      setLatestAI(data.artifacts || {});
      setContent("");
      setMood(0);
      await loadTimeline();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b px-6 py-4">
        <h1 className="text-xl font-semibold">📝 工作日记</h1>
        <p className="text-sm text-slate-500 mt-1">每天写点东西,智能体会给你建议</p>
      </div>

      <div className="max-w-3xl mx-auto p-6 space-y-6">
        {/* 撰写区 */}
        <div className="bg-white rounded-2xl shadow-sm p-6">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="今天做了什么?有什么收获或困惑?"
            className="w-full border rounded-xl p-4 min-h-32 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <div className="mt-3 flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              心情
              <input
                type="range"
                min={-1}
                max={1}
                step={0.1}
                value={mood}
                onChange={(e) => setMood(parseFloat(e.target.value))}
              />
              <span className="text-slate-600">
                {mood > 0.3 ? "😊" : mood < -0.3 ? "😔" : "😐"} ({mood.toFixed(1)})
              </span>
            </label>
            <button
              onClick={submit}
              disabled={submitting || !content.trim()}
              className="ml-auto px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50"
            >
              {submitting ? "AI 思考中..." : "提交"}
            </button>
          </div>

          {/* AI 评价 */}
          {latestAI && (
            <div className="mt-5 p-4 bg-blue-50 rounded-xl space-y-2">
              <div className="flex items-center gap-2">
                <span className="font-medium">📌 评价:</span>
                <span
                  className={`px-2 py-0.5 rounded text-xs ${
                    latestAI.rating === "excellent"
                      ? "bg-green-200 text-green-800"
                      : latestAI.rating === "good"
                      ? "bg-blue-200 text-blue-800"
                      : "bg-orange-200 text-orange-800"
                  }`}
                >
                  {latestAI.rating || "good"}
                </span>
              </div>
              {latestAI.advice && (
                <div>
                  <span className="font-medium">💡 建议:</span> {latestAI.advice}
                </div>
              )}
              {latestAI.warnings && latestAI.warnings.length > 0 && (
                <div>
                  <span className="font-medium">⚠️ 注意:</span> {latestAI.warnings.join(" / ")}
                </div>
              )}
              {latestAI.action_items && latestAI.action_items.length > 0 && (
                <div>
                  <span className="font-medium">🎯 明天:</span> {latestAI.action_items.join(" / ")}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 时间线 */}
        <div>
          <h2 className="text-lg font-semibold mb-3">最近 30 天</h2>
          <div className="space-y-3">
            {timeline.map((j) => (
              <div key={j.id} className="bg-white rounded-xl shadow-sm p-4">
                <div className="flex justify-between items-center text-sm text-slate-500 mb-2">
                  <span>{j.journal_date}</span>
                  <span>
                    {j.mood_score !== null && (
                      <span className="mr-2">
                        {j.mood_score > 0.3 ? "😊" : j.mood_score < -0.3 ? "😔" : "😐"} {j.mood_score.toFixed(1)}
                      </span>
                    )}
                    {j.ai_rating && (
                      <span
                        className={`px-2 py-0.5 rounded text-xs ${
                          j.ai_rating === "excellent"
                            ? "bg-green-100 text-green-700"
                            : j.ai_rating === "good"
                            ? "bg-blue-100 text-blue-700"
                            : "bg-orange-100 text-orange-700"
                        }`}
                      >
                        {j.ai_rating}
                      </span>
                    )}
                  </span>
                </div>
                <div className="text-sm">{j.content}</div>
                {j.ai_advice && (
                  <div className="mt-2 text-sm text-slate-600 border-t pt-2">
                    <span className="font-medium">智能体:</span> {j.ai_advice}
                  </div>
                )}
              </div>
            ))}
            {timeline.length === 0 && (
              <div className="text-center py-12 text-slate-400">还没有日记,开始写第一篇吧</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}