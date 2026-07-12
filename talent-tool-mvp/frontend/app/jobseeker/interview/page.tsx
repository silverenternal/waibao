"use client";

/**
 * /interview — AI 面试入口 (T1301).
 *
 * 候选人选择岗位类别 → 创建一场面试 → 跳转 /interview/[id].
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

const ROLE_OPTIONS = [
  { value: "backend_engineer", label: "后端工程师" },
  { value: "frontend_engineer", label: "前端工程师" },
  { value: "fullstack_engineer", label: "全栈工程师" },
  { value: "mobile_engineer", label: "移动端工程师" },
  { value: "data_engineer", label: "数据工程师" },
  { value: "data_scientist", label: "数据科学家" },
  { value: "product_manager", label: "产品经理" },
  { value: "designer", label: "设计师" },
  { value: "marketing", label: "市场" },
  { value: "sales", label: "销售" },
];

const DIFFICULTY = [
  { value: "junior", label: "初中级" },
  { value: "mid", label: "中级" },
  { value: "senior", label: "高级" },
  { value: "lead", label: "资深/Lead" },
];

export default function InterviewLandingPage() {
  const router = useRouter();
  const [role, setRole] = useState("backend_engineer");
  const [difficulty, setDifficulty] = useState("mid");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function startInterview() {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/ai-interview/start", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          role,
          role_label: ROLE_OPTIONS.find((r) => r.value === role)?.label || role,
          difficulty,
          total_questions: 10,
        }),
      });
      if (!r.ok) {
        const detail = await r.text();
        throw new Error(detail || `HTTP ${r.status}`);
      }
      const data = await r.json();
      router.push(`/interview/${data.id}`);
    } catch (e: any) {
      setError(e?.message || "启动面试失败,请稍后再试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b px-6 py-4">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <span aria-hidden>🤖</span> AI 自动面试
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          基于 GPT-4V 视频理解 + Whisper 转写 + LLM 评估,10 道结构化题目。
        </p>
      </div>

      <div className="max-w-3xl mx-auto p-6 space-y-6">
        <section className="bg-white rounded-2xl shadow-sm p-6 space-y-5">
          <h2 className="text-base font-semibold text-slate-800">第 1 步 · 选择岗位</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3" data-testid="role-grid">
            {ROLE_OPTIONS.map((r) => (
              <button
                key={r.value}
                onClick={() => setRole(r.value)}
                aria-pressed={role === r.value}
                className={`px-3 py-2 text-sm rounded-lg border transition ${
                  role === r.value
                    ? "border-sky-500 bg-sky-50 text-sky-700"
                    : "border-slate-200 hover:border-slate-400"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </section>

        <section className="bg-white rounded-2xl shadow-sm p-6 space-y-4">
          <h2 className="text-base font-semibold text-slate-800">第 2 步 · 选择难度</h2>
          <div className="flex gap-2 flex-wrap" data-testid="difficulty-row">
            {DIFFICULTY.map((d) => (
              <button
                key={d.value}
                onClick={() => setDifficulty(d.value)}
                aria-pressed={difficulty === d.value}
                className={`px-4 py-2 text-sm rounded-full border ${
                  difficulty === d.value
                    ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                    : "border-slate-200 hover:border-slate-400"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </section>

        <section className="bg-white rounded-2xl shadow-sm p-6 space-y-3">
          <h2 className="text-base font-semibold text-slate-800">准备好了吗?</h2>
          <p className="text-sm text-slate-600 leading-relaxed">
            建议在安静、光线充足的环境中进行。点击开始后,
            <span className="font-medium">会依次展示 10 道题目</span>,
            可以用视频回答也可以用文字输入,模型会给出整体打分与改进建议。
          </p>
          <ul className="text-xs text-slate-500 list-disc pl-5 space-y-1">
            <li>每题没有固定时间,但建议在 90 秒内回答</li>
            <li>视频仅用于 AI 评估,不会对外公开</li>
            <li>可随时以文本方式兜底,不影响最终报告</li>
          </ul>

          {error && (
            <div className="bg-rose-50 text-rose-700 text-sm rounded p-3" data-testid="start-error">
              {error}
            </div>
          )}

          <button
            onClick={startInterview}
            disabled={loading}
            data-testid="start-interview"
            className="w-full px-6 py-3 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 text-white font-medium disabled:opacity-50"
          >
            {loading ? "准备面试中..." : "开始面试"}
          </button>
        </section>
      </div>
    </div>
  );
}
