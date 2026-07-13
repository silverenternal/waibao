"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

interface JDScore {
  completeness: number;
  attractiveness: number;
  fairness: number;
  marketing: number;
  total: number;
}

interface JDPackage {
  seo: { title: string; description: string; keywords: string[] };
  story_mode: string;
  culture_blurb: string;
  team_vibe: string;
  scores: JDScore;
  ab_variants: Array<{ variant: string; title: string }>;
}

export function JDScorer() {
  const [title, setTitle] = useState("前端工程师");
  const [description, setDescription] = useState("我们正在构建下一代产品。");
  const [cultureKw, setCultureKw] = useState("开放, 协作, 透明");
  const [teamSize, setTeamSize] = useState("10");
  const [result, setResult] = useState<JDPackage | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/v8_1_p2/jd-marketing/package", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          payload: {
            title,
            description,
            vision: "下一代产品",
            candidate_impact: "真正的改变",
            culture_keywords: cultureKw.split(",").map(s => s.trim()).filter(Boolean),
            team_size: parseInt(teamSize, 10),
            location: "B",
            salary_range: "20-40k",
            benefits: "期权, 弹性工作",
          },
        }),
      });
      if (r.ok) setResult(await r.json());
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>JD 营销化 · JD Marketing</CardTitle>
        <p className="text-sm text-muted-foreground">v8.1 T3705: 故事化 + SEO + A/B + 4 维评分</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs">岗位名</label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <label className="text-xs">团队规模</label>
            <Input value={teamSize} onChange={(e) => setTeamSize(e.target.value)} />
          </div>
        </div>
        <div>
          <label className="text-xs">描述</label>
          <Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div>
          <label className="text-xs">文化关键词(逗号分隔)</label>
          <Input value={cultureKw} onChange={(e) => setCultureKw(e.target.value)} />
        </div>
        <Button disabled={loading} onClick={run}>生成营销包</Button>

        {result && (
          <div className="space-y-3 rounded border p-3">
            <div>
              <div className="text-xs text-muted-foreground mb-1">故事化描述</div>
              <p className="text-sm">{result.story_mode}</p>
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-1">SEO Meta</div>
              <div className="text-sm">{result.seo.title}</div>
              <div className="text-xs text-muted-foreground">{result.seo.description}</div>
              <div className="flex gap-1 mt-1 flex-wrap">
                {result.seo.keywords.map((k, i) => (
                  <Badge key={i} variant="outline">{k}</Badge>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-1">A/B 标题变体</div>
              <div className="grid grid-cols-2 gap-2">
                {result.ab_variants.map(v => (
                  <div key={v.variant} className="rounded border p-2 text-sm">
                    <Badge variant="outline" className="mb-1">{v.variant}</Badge>
                    <div>{v.title}</div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-1">评分</div>
              <div className="space-y-1">
                {(["completeness", "attractiveness", "fairness", "marketing"] as const).map(k => (
                  <div key={k} className="flex items-center gap-2 text-xs">
                    <span className="w-24">{k}</span>
                    <Progress value={result.scores[k]} className="flex-1" />
                    <span className="font-mono w-12">{result.scores[k]}</span>
                  </div>
                ))}
                <div className="text-base font-semibold mt-1">总分: {result.scores.total}</div>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default JDScorer;
