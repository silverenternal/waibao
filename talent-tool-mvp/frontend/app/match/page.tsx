"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import { useEffect, useState } from "react";

type Match = {
  id: string;
  candidate_id: string;
  role_id: string;
  candidate_to_role: number;
  role_to_candidate: number;
  harmonic_score: number;
  status: string;
};

export default function MatchPage() {
  const [roleId, setRoleId] = useState("");
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!roleId) return;
    setLoading(true);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch(`/api/two-way-match/for-role/${roleId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await r.json();
      setMatches(data || []);
    } finally { setLoading(false); }
  }

  return (
    <ErrorBoundary>(<div className="min-h-screen bg-slate-50">
        <div className="bg-white border-b px-6 py-4">
          <h1 className="text-xl font-semibold">🤝 双向匹配</h1>
          <p className="text-sm text-slate-500 mt-1">求职者 ↔ 用人单位 双向打分</p>
        </div>
        <div className="max-w-4xl mx-auto p-6">
          <div className="bg-white rounded-2xl shadow-sm p-6 mb-6">
            <label className="text-sm text-slate-600">岗位 ID</label>
            <div className="mt-2 flex gap-2">
              <input
                value={roleId}
                onChange={(e) => setRoleId(e.target.value)}
                placeholder="输入 role UUID"
                className="flex-1 border rounded-lg p-2"
              />
              <button onClick={load} disabled={loading || !roleId} className="px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">
                {loading ? "查询中..." : "查询"}
              </button>
            </div>
          </div>

          <div className="space-y-3">
            {matches.map((m, i) => (
              <div key={m.id} className="bg-white rounded-xl shadow-sm p-5">
                <div className="flex items-center justify-between mb-3">
                  <div className="text-sm text-slate-500">排名 #{i + 1}</div>
                  <span className="text-xs px-2 py-0.5 bg-slate-100 rounded">{m.status}</span>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <div className="text-xs text-slate-500">求职者→岗位</div>
                    <div className="text-xl font-bold text-blue-600">{(m.candidate_to_role * 100).toFixed(0)}%</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">岗位→求职者</div>
                    <div className="text-xl font-bold text-green-600">{(m.role_to_candidate * 100).toFixed(0)}%</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">调和值</div>
                    <div className="text-xl font-bold text-purple-600">{(m.harmonic_score * 100).toFixed(0)}%</div>
                  </div>
                </div>
                <div className="mt-3 h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-blue-500 via-green-500 to-purple-500"
                    style={{ width: `${m.harmonic_score * 100}%` }}
                  />
                </div>
              </div>
            ))}
            {matches.length === 0 && !loading && (
              <div className="text-center py-12 text-slate-400">输入岗位 ID 后查看匹配结果</div>
            )}
          </div>
        </div>
      </div>)</ErrorBoundary>
  );
}