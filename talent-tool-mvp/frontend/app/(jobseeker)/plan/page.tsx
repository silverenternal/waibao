"use client";

import { useEffect, useState } from "react";

type Plan = {
  short_term: any[];
  mid_term: any[];
  long_term: any[];
  learning_paths: any[];
  recommended_roles: any[];
  market_insights: any;
  skill_gaps: any[];
  milestones: any[];
};

export default function CareerPlanPage() {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(false);

  async function generate() {
    setLoading(true);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/career-plan/generate", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await r.json();
      setPlan(data.plan);
    } finally {
      setLoading(false);
    }
  }

  async function loadCurrent() {
    const token = localStorage.getItem("sb_token") || "";
    const r = await fetch("/api/career-plan/current", {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await r.json();
    if (data && data.short_term) setPlan(data);
  }

  useEffect(() => { loadCurrent(); }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">🎯 职业规划</h1>
          <p className="text-sm text-slate-500 mt-1">智能体基于你的画像和需求生成</p>
        </div>
        <button
          onClick={generate}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50"
        >
          {loading ? "生成中..." : plan ? "重新生成" : "生成规划"}
        </button>
      </div>

      <div className="max-w-4xl mx-auto p-6">
        {!plan && !loading && (
          <div className="text-center py-20 text-slate-400">
            点击右上角"生成规划"按钮,智能体会根据你的画像和需求生成多层次规划
          </div>
        )}

        {plan && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* 短期 */}
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <h2 className="font-semibold text-green-700 mb-3">📅 短期(3个月内)</h2>
              <ul className="space-y-3">
                {(plan.short_term || []).map((x, i) => (
                  <li key={i} className="border-l-4 border-green-400 pl-3">
                    <div className="font-medium text-sm">{x.title}</div>
                    <div className="text-xs text-slate-500 mt-1">{x.detail}</div>
                    <div className="text-xs text-slate-400 mt-1">{x.duration}</div>
                  </li>
                ))}
              </ul>
            </div>

            {/* 中期 */}
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <h2 className="font-semibold text-blue-700 mb-3">🚀 中期(1年内)</h2>
              <ul className="space-y-3">
                {(plan.mid_term || []).map((x, i) => (
                  <li key={i} className="border-l-4 border-blue-400 pl-3">
                    <div className="font-medium text-sm">{x.title}</div>
                    <div className="text-xs text-slate-500 mt-1">{x.detail}</div>
                    <div className="text-xs text-slate-400 mt-1">{x.duration}</div>
                  </li>
                ))}
              </ul>
            </div>

            {/* 长期 */}
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <h2 className="font-semibold text-purple-700 mb-3">🌟 长期(3年+)</h2>
              <ul className="space-y-3">
                {(plan.long_term || []).map((x, i) => (
                  <li key={i} className="border-l-4 border-purple-400 pl-3">
                    <div className="font-medium text-sm">{x.title}</div>
                    <div className="text-xs text-slate-500 mt-1">{x.detail}</div>
                    <div className="text-xs text-slate-400 mt-1">{x.duration}</div>
                  </li>
                ))}
              </ul>
            </div>

            {/* 推荐岗位 */}
            {plan.recommended_roles?.length > 0 && (
              <div className="bg-white rounded-2xl shadow-sm p-5 md:col-span-2">
                <h2 className="font-semibold mb-3">💼 推荐岗位</h2>
                <div className="space-y-2">
                  {plan.recommended_roles.map((r, i) => (
                    <div key={i} className="border rounded-lg p-3 flex justify-between">
                      <div>
                        <div className="font-medium">{r.title}</div>
                        <div className="text-xs text-slate-500">{r.reason}</div>
                      </div>
                      <div className="text-sm font-medium text-blue-600">
                        {Math.round((r.match_score || 0) * 100)}%
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 技能缺口 */}
            {plan.skill_gaps?.length > 0 && (
              <div className="bg-white rounded-2xl shadow-sm p-5">
                <h2 className="font-semibold mb-3">📚 技能缺口</h2>
                <ul className="space-y-2">
                  {plan.skill_gaps.map((g, i) => (
                    <li key={i} className="flex justify-between text-sm">
                      <span>{g.skill}</span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded ${
                          g.importance === "high"
                            ? "bg-red-100 text-red-700"
                            : g.importance === "medium"
                            ? "bg-yellow-100 text-yellow-700"
                            : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {g.importance}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 市场行情 */}
            {plan.market_insights && (
              <div className="bg-white rounded-2xl shadow-sm p-5 md:col-span-3">
                <h2 className="font-semibold mb-3">📊 市场行情</h2>
                <div className="text-xs text-slate-600">
                  <pre className="bg-slate-50 p-3 rounded overflow-auto">
                    {JSON.stringify(plan.market_insights, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}