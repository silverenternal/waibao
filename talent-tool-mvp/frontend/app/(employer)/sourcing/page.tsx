"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CandidateCard } from "@/components/sourcing/CandidateCard";
import {
  searchCandidates,
  type SearchRequest,
  type SourcedCandidate,
} from "@/lib/api-sourcing";

const SENIORITY_OPTIONS = [
  { value: "", label: "不限" },
  { value: "junior", label: "初级" },
  { value: "mid", label: "中级" },
  { value: "senior", label: "高级" },
  { value: "staff", label: "专家" },
];

/**
 * AI 主动 Sourcing — 一键启动 + 候选人列表 (5 维评分) + 一键邀请 (T3002).
 */
export default function SourcingPage() {
  const [title, setTitle] = React.useState("后端工程师");
  const [skills, setSkills] = React.useState("Go, Kubernetes, Redis");
  const [location, setLocation] = React.useState("北京");
  const [seniority, setSeniority] = React.useState("senior");
  const [minYears, setMinYears] = React.useState(3);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [candidates, setCandidates] = React.useState<SourcedCandidate[]>([]);
  const [searched, setSearched] = React.useState(false);

  const launch = async () => {
    setLoading(true);
    setError(null);
    try {
      const body: SearchRequest = {
        title: title.trim(),
        skills: skills.split(",").map((s) => s.trim()).filter(Boolean),
        location: location.trim() || undefined,
        seniority: seniority || undefined,
        min_years: minYears,
        target: 100,
      };
      const res = await searchCandidates(body);
      setCandidates(res.candidates);
      setSearched(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "搜索失败");
    } finally {
      setLoading(false);
    }
  };

  const avgScore =
    candidates.length > 0
      ? Math.round(
          candidates.reduce((a, c) => a + c.match.overall, 0) / candidates.length,
        )
      : 0;

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">AI 主动 Sourcing</h1>
        <p className="text-sm text-slate-500">
          输入岗位画像, AI 主动从 GitHub 等渠道发掘候选人并按 5 维度打分。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">岗位画像</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label htmlFor="title">岗位名称</Label>
            <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1.5 lg:col-span-2">
            <Label htmlFor="skills">技能栈 (逗号分隔)</Label>
            <Input id="skills" value={skills} onChange={(e) => setSkills(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="location">城市</Label>
            <Input id="location" value={location} onChange={(e) => setLocation(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="seniority">资历</Label>
            <select
              id="seniority"
              className="w-full h-9 rounded-md border border-slate-200 px-3 text-sm"
              value={seniority}
              onChange={(e) => setSeniority(e.target.value)}
            >
              {SENIORITY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="minYears">最低年限</Label>
            <Input
              id="minYears"
              type="number"
              min={0}
              max={40}
              value={minYears}
              onChange={(e) => setMinYears(Number(e.target.value) || 0)}
            />
          </div>
          <div className="flex items-end">
            <Button onClick={launch} disabled={loading || !title.trim()} className="w-full">
              {loading ? "发掘中…" : "🚀 一键启动"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-rose-500">{error}</p>}

      {searched && (
        <div className="flex items-center gap-6 text-sm text-slate-600">
          <span>
            找到 <strong className="text-slate-900">{candidates.length}</strong> 名候选人
          </span>
          <span>
            平均匹配分 <strong className="text-slate-900">{avgScore}</strong>
          </span>
        </div>
      )}

      {loading && <p className="text-sm text-slate-500">AI 正在发掘候选人…</p>}
      {searched && !loading && candidates.length === 0 && (
        <p className="text-sm text-slate-500">未找到匹配候选人, 试试放宽条件。</p>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {candidates.map((c) => (
          <CandidateCard key={c.id} candidate={c} jobTitle={title} />
        ))}
      </div>
    </div>
  );
}
