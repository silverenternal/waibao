"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SleepyCandidateCard } from "@/components/rediscovery/SleepyCandidateCard";
import {
  fetchSleepyCandidates,
  fetchStats,
  fetchStrategies,
  type SleepyCandidate,
  type RediscoveryStats,
} from "@/lib/api-rediscovery";

const STRATEGIES = [
  { value: "conservative", label: "保守", desc: "仅高潜力 (≥75%)" },
  { value: "standard", label: "标准 (默认)", desc: "中高潜力 (≥55%)" },
  { value: "aggressive", label: "激进", desc: "全量 (≥35%)" },
];

/**
 * 沉睡激活面板 (mothership / T2406).
 */
export default function RediscoveryPage() {
  const [strategy, setStrategy] = React.useState("standard");
  const [candidates, setCandidates] = React.useState<SleepyCandidate[]>([]);
  const [stats, setStats] = React.useState<RediscoveryStats | null>(null);
  const [loading, setLoading] = React.useState(false);

  const refresh = React.useCallback(async (s: string) => {
    setLoading(true);
    try {
      const [c, st] = await Promise.all([
        fetchSleepyCandidates(s),
        fetchStats(),
      ]);
      setCandidates(c.candidates);
      setStats(st);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refresh(strategy);
  }, [strategy, refresh]);

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">沉睡候选人激活</h1>
        <button
          className="text-sm text-blue-600 hover:underline"
          onClick={() => refresh(strategy)}
        >
          刷新
        </button>
      </div>
      <p className="text-sm text-slate-500">
        6+ 个月未活跃的候选人, 基于新职位 + 候选人画像评估激活潜力。
      </p>

      {/* 转化率统计 */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-4">
              <p className="text-xs text-slate-500 uppercase">总激活</p>
              <p className="text-2xl font-bold mt-1">{stats.total_activations}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-xs text-slate-500 uppercase">已转化</p>
              <p className="text-2xl font-bold text-emerald-600 mt-1">
                {stats.converted}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-xs text-slate-500 uppercase">综合转化率</p>
              <p className="text-2xl font-bold mt-1">
                {(stats.overall_conversion_rate * 100).toFixed(0)}%
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-xs text-slate-500 uppercase">策略数</p>
              <p className="text-2xl font-bold mt-1">
                {Object.keys(stats.by_strategy).length}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* 策略选择 */}
      <div className="flex gap-2 flex-wrap">
        {STRATEGIES.map((s) => (
          <button
            key={s.value}
            className={`px-3 py-1.5 rounded text-sm transition-colors ${
              strategy === s.value
                ? "bg-blue-500 text-white"
                : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
            onClick={() => setStrategy(s.value)}
          >
            {s.label} — <span className="text-xs opacity-70">{s.desc}</span>
          </button>
        ))}
      </div>

      {/* 分策略转化率 */}
      {stats && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">分策略转化率</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 text-xs uppercase border-b">
                  <th className="py-2">策略</th>
                  <th>激活数</th>
                  <th>转化数</th>
                  <th>转化率</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(stats.by_strategy).map(([k, v]) => (
                  <tr key={k} className="border-b">
                    <td className="py-2 font-medium">{k}</td>
                    <td>{v.total}</td>
                    <td>{v.converted}</td>
                    <td>{(v.rate * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* 沉睡候选人列表 */}
      <div className="space-y-2">
        <h2 className="text-lg font-semibold">
          沉睡候选人 ({candidates.length})
        </h2>
        {loading && <p className="text-sm text-slate-500">加载中…</p>}
        {!loading && candidates.length === 0 && (
          <p className="text-sm text-slate-500">当前策略下无沉睡候选人</p>
        )}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {candidates.map((c) => (
            <SleepyCandidateCard
              key={c.id}
              candidate={c}
              onActivated={() => refresh(strategy)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
