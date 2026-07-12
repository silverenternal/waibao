"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { LearningResourceList } from "@/components/plan/LearningResourceList";
import {
  searchLearningResources,
  recommendLearningResources,
  type LearningResource,
} from "@/lib/api-learning";

export default function LearningPage() {
  const [skill, setSkill] = useState("Python");
  const [items, setItems] = useState<LearningResource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"search" | "recommend">("search");

  async function loadSearch() {
    setLoading(true);
    setError(null);
    try {
      const rows = await searchLearningResources(skill);
      setItems(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadRecommend() {
    setLoading(true);
    setError(null);
    try {
      // 用逗号分隔输入多个 gap skills
      const skills = skill.split(/[,，\s]+/).filter(Boolean);
      const rows = await recommendLearningResources(skills);
      setItems(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submit() {
    if (mode === "search") await loadSearch();
    else await loadRecommend();
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">学习资源</h1>
        <p className="text-sm text-muted-foreground">
          聚合 Coursera / 极客时间 / 掘金小册 / 慕课网 / Bilibili 公开课
        </p>
      </header>

      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 p-4">
          <div className="flex-1 min-w-[200px]">
            <label className="mb-1 block text-xs text-muted-foreground">
              {mode === "search"
                ? "技能关键词"
                : "Gap skills (逗号分隔)"}
            </label>
            <Input
              value={skill}
              onChange={(e) => setSkill(e.target.value)}
              placeholder={
                mode === "search"
                  ? "例:Python / FastAPI / Kubernetes"
                  : "例:Python, FastAPI, Kubernetes"
              }
            />
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant={mode === "search" ? "default" : "outline"}
              onClick={() => setMode("search")}
            >
              单技能搜索
            </Button>
            <Button
              size="sm"
              variant={mode === "recommend" ? "default" : "outline"}
              onClick={() => setMode("recommend")}
            >
              Gap 推荐
            </Button>
          </div>
          <Button onClick={submit} disabled={loading}>
            {loading ? "查询中…" : "刷新"}
          </Button>
          {items.length > 0 && (
            <Badge variant="outline">共 {items.length} 条</Badge>
          )}
        </CardContent>
      </Card>

      {error && (
        <Card className="border-red-300 bg-red-50">
          <CardContent className="p-3 text-sm text-red-700">{error}</CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">推荐结果</CardTitle>
        </CardHeader>
        <CardContent>
          <LearningResourceList
            items={items}
            emptyText={
              mode === "search"
                ? "未找到相关资源 — 试试别的关键词"
                : "未找到推荐资源 — 试试更多 gap skills"
            }
          />
        </CardContent>
      </Card>
    </div>
  );
}