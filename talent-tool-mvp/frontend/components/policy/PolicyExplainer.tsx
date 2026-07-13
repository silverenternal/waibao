"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

interface FAQ {
  q: string;
  a: string;
}

interface ExplainResult {
  plain_version: string;
  key_points: string[];
  faqs: FAQ[];
  risk_flags: string[];
  citations: string[];
}

export function PolicyExplainer() {
  const [title, setTitle] = useState("试用期制度");
  const [content, setContent] = useState(
    "用人单位在试用期内不得随意解除劳动合同。劳动者在试用期内的工资不得低于转正后工资的 80%,也不得低于当地最低工资标准。",
  );
  const [result, setResult] = useState<ExplainResult | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/v8_1_p2/policy-explainer/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, content }),
      });
      if (r.ok) setResult(await r.json());
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>制度 AI 解释 · Policy Explainer</CardTitle>
        <p className="text-sm text-muted-foreground">v8.1 T3706: 把法律语言转换为通俗解释</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-1">
            <label className="text-xs">制度名</label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
        </div>
        <div>
          <label className="text-xs">原文</label>
          <Textarea rows={4} value={content} onChange={(e) => setContent(e.target.value)} />
        </div>
        <Button disabled={loading} onClick={run}>解释</Button>

        {result && (
          <div className="space-y-3 rounded border p-3">
            <div>
              <div className="text-xs font-medium text-muted-foreground mb-1">通俗版</div>
              <p className="text-sm whitespace-pre-wrap">{result.plain_version}</p>
            </div>
            {result.key_points.length > 0 && (
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-1">要点</div>
                <ul className="text-sm list-disc pl-5">
                  {result.key_points.map((p, i) => <li key={i}>{p}</li>)}
                </ul>
              </div>
            )}
            {result.faqs.length > 0 && (
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-1">FAQ</div>
                <div className="space-y-2 text-sm">
                  {result.faqs.map((f, i) => (
                    <div key={i} className="border-l-2 border-blue-400 pl-2">
                      <div className="font-medium">{f.q}</div>
                      <div className="text-muted-foreground">{f.a}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {result.risk_flags.length > 0 && (
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-1">风险标记</div>
                <div className="flex gap-1 flex-wrap">
                  {result.risk_flags.map((r, i) => <Badge key={i} variant="destructive">{r}</Badge>)}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default PolicyExplainer;
