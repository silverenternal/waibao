"use client";

/**
 * T6106 — 硬条件匹配页 (甲方合同版).
 *
 * HR 输入岗位 ID, 调用 T6105 硬条件匹配引擎 (POST /api/matches/hard-filter/{id}),
 * 用 MatchResultCard 渲染结果. 甲方要求 "不淘汰只排序": 所有人保留, 按分数
 * 降序展示, 有缺口的卡片仍显示 (标黄 + 硬条件未达标提示).
 */
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { MatchResultCard } from "@/components/marketplace/MatchResultCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  runHardFilterMatch,
  type MatchResultItem,
} from "@/lib/api-hard-filter";
import { useCallback, useState } from "react";

export default function MatchPage() {
  const [roleId, setRoleId] = useState("");
  const [items, setItems] = useState<MatchResultItem[]>([]);
  const [passedHard, setPassedHard] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!roleId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await runHardFilterMatch(roleId.trim(), { topK: 50 });
      setItems(res.items);
      setPassedHard(res.passed_hard);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "匹配失败");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [roleId]);

  return (
    <ErrorBoundary>
      <main className="min-h-screen bg-slate-50">
        <div className="border-b bg-white px-6 py-4">
          <h1 className="text-xl font-semibold">🎯 硬条件匹配</h1>
          <p className="mt-1 text-sm text-slate-500">
            技能/学历/证书 硬条件 + 薪资/城市/到岗 高优先级 · 不淘汰, 只排序
          </p>
        </div>

        <div className="mx-auto max-w-6xl p-6">
          {/* 查询框 */}
          <div className="mb-6 rounded-2xl bg-white p-6 shadow-sm">
            <label className="text-sm text-slate-600">岗位 ID</label>
            <div className="mt-2 flex gap-2">
              <Input
                value={roleId}
                onChange={(e) => setRoleId(e.target.value)}
                placeholder="输入 role UUID"
                aria-label="岗位 ID"
                onKeyDown={(e) => {
                  if (e.key === "Enter") load();
                }}
              />
              <Button onClick={load} disabled={loading || !roleId.trim()}>
                {loading ? "匹配中..." : "匹配"}
              </Button>
            </div>
            {error && (
              <p className="mt-2 text-sm text-rose-600" role="alert">
                {error}
              </p>
            )}
            {total > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <Badge variant="secondary">共 {total} 人</Badge>
                <Badge variant="outline" className="text-emerald-600">
                  硬条件达标 {passedHard}
                </Badge>
                <Badge variant="outline" className="text-amber-600">
                  未达标 {total - passedHard}
                </Badge>
              </div>
            )}
          </div>

          {/* 结果网格 */}
          {items.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((r, i) => (
                <MatchResultCard
                  key={r.candidate_id || i}
                  result={r}
                  rank={i + 1}
                />
              ))}
            </div>
          ) : (
            !loading && (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-12 text-center text-sm text-slate-400">
                输入岗位 ID 后查看匹配结果
              </div>
            )
          )}
        </div>
      </main>
    </ErrorBoundary>
  );
}
