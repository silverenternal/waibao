"use client";

/**
 * /jobseeker/interview — AI 面试入口 (T1301 + T2202).
 *
 * 候选人选择岗位 + 难度 + 人格 → 创建一场 5 阶段模拟面试 → 跳转 /jobseeker/interview/ai/[id].
 *
 * T2202 增强:
 *   - 5 种面试官人格 (friendly_warm / rigorous_strict / challenging_pressure /
 *     senior_experienced / tech_expert)
 *   - 启用 Realtime 语音的选项
 *   - 难度选项
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import InterviewPersonaPicker from "@/components/interview/InterviewPersonaPicker";

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
  const [personaId, setPersonaId] = useState("friendly_warm");
  const [realtime, setRealtime] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function startInterview() {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/ai-interview-v2/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          role,
          role_label: ROLE_OPTIONS.find((rr) => rr.value === role)?.label || role,
          difficulty,
          persona_id: personaId,
          realtime,
        }),
      });
      if (!r.ok) {
        const detail = await r.text();
        throw new Error(detail || `HTTP ${r.status}`);
      }
      const data = await r.json();
      // Persist the interview meta for the next page to display
      try {
        sessionStorage.setItem(
          `interview_${data.id}`,
          JSON.stringify({
            id: data.id,
            persona: data.persona,
            role: data.role,
            role_label: data.role_label,
            total_questions: data.total_questions,
            stages: data.stages,
          }),
        );
      } catch {}
      router.push(`/jobseeker/interview/ai/${data.id}`);
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
          <span aria-hidden>🤖</span> AI 模拟面试
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          5 阶段流程 + 5 种面试官人格 + 智能追问,可选启用 GPT-4o Realtime 语音。
        </p>
      </div>

      <div className="max-w-4xl mx-auto p-6 space-y-6">
        <section className="bg-white rounded-2xl shadow-sm p-6 space-y-4">
          <h2 className="text-base font-semibold text-slate-800">第 1 步 · 选择面试官人格</h2>
          <InterviewPersonaPicker selected={personaId} onSelect={setPersonaId} />
        </section>

        <section className="bg-white rounded-2xl shadow-sm p-6 space-y-4">
          <h2 className="text-base font-semibold text-slate-800">第 2 步 · 选择岗位</h2>
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
          <h2 className="text-base font-semibold text-slate-800">第 3 步 · 选择难度</h2>
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
          <h2 className="text-base font-semibold text-slate-800">第 4 步 · 模式</h2>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={realtime}
              onChange={(e) => setRealtime(e.target.checked)}
              className="rounded"
              data-testid="realtime-toggle"
            />
            启用 GPT-4o Realtime 语音对话(可选)
          </label>
          <p className="text-xs text-slate-500 leading-relaxed">
            启用后,候选人可以通过麦克风与 AI 面试官实时对话。文本回答仍可作为兜底。
          </p>
        </section>

        <section className="bg-white rounded-2xl shadow-sm p-6 space-y-3">
          <h2 className="text-base font-semibold text-slate-800">准备好了吗?</h2>
          <p className="text-sm text-slate-600 leading-relaxed">
            点击开始后,系统将依次展示 <span className="font-medium">5 个阶段</span> 的题目:
            破冰 → 行为 → 技术 → 反问 → 总结。
            系统会根据你的回答深度智能追问,生成 5 维评分报告。
          </p>

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
