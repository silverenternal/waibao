"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";

interface VerificationResult {
  target: string;
  suspicion_score: number;
  findings: Array<{ code: string; severity: number; detail: string }>;
  signals: Record<string, string>;
  expiry_warning: string | null;
  cross_source_mismatches: string[];
  auto_escalate: boolean;
  summary: string;
}

export function VerificationScore({ target = "营业执照.png" }: { target?: string }) {
  const [file, setFile] = useState<string>(target);
  const [expiry, setExpiry] = useState("2026-12-31");
  const [ocrText, setOcrText] = useState("ABC123");
  const [saicText, setSaicText] = useState("ABC123");
  const [result, setResult] = useState<VerificationResult | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/v8_1_p2/ps/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target: file,
          metadata: { software: "iPhone", creation_date: "2024-01-01" },
          expiry_text: expiry,
          sources: { ocr: ocrText, saic: saicText, legal: "ABC123", credit: "ABC123" },
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
        <CardTitle>资质核验 · Verification Score</CardTitle>
        <p className="text-sm text-muted-foreground">v8.1 T3702: ELA + 噪点 + 哈希 + EXIF + 跨源 + 过期</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs">证件名</label>
            <Input value={file} onChange={(e) => setFile(e.target.value)} />
          </div>
          <div>
            <label className="text-xs">有效期</label>
            <Input value={expiry} onChange={(e) => setExpiry(e.target.value)} />
          </div>
          <div>
            <label className="text-xs">OCR 字段</label>
            <Input value={ocrText} onChange={(e) => setOcrText(e.target.value)} />
          </div>
          <div>
            <label className="text-xs">工商字段</label>
            <Input value={saicText} onChange={(e) => setSaicText(e.target.value)} />
          </div>
        </div>
        <Button disabled={loading} onClick={run}>核验</Button>

        {result && (
          <div className="space-y-3 rounded border p-3">
            <div className="flex items-center justify-between">
              <div>
                <Badge variant={result.auto_escalate ? "destructive" : "secondary"}>
                  可疑度 {result.suspicion_score}
                </Badge>
                <p className="text-sm text-muted-foreground mt-2">{result.summary}</p>
              </div>
              <div className="text-right">
                <div className="text-xs">评分</div>
                <Progress value={result.suspicion_score} className="w-24" />
              </div>
            </div>
            {result.expiry_warning && (
              <Badge variant="destructive">{result.expiry_warning}</Badge>
            )}
            {result.findings.length > 0 && (
              <div>
                <div className="text-xs font-medium mb-1">发现项</div>
                <ul className="text-sm space-y-1">
                  {result.findings.map((f, i) => (
                    <li key={i} className="border-l-2 border-amber-400 pl-2">
                      <span className="font-mono text-xs">[{f.code}]</span> {f.detail} (严重度 {f.severity})
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {result.cross_source_mismatches.length > 0 && (
              <div>
                <div className="text-xs font-medium mb-1">跨源不匹配</div>
                <ul className="text-sm">
                  {result.cross_source_mismatches.map((m, i) => <li key={i}>{m}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default VerificationScore;
