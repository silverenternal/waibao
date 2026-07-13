"use client";

import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const ToneSimulator = dynamic(() => import("@/components/hr/ToneSimulator").then(m => m.ToneSimulator), { ssr: false });

export default function HRTonePage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">语气设置 · HR Tone</h1>
        <p className="text-sm text-muted-foreground mt-1">
          v8.1 T3701: 让 HR 沟通按你(老板)的历史语气。
        </p>
      </header>

      <ToneSimulator
        history={[
          "请您按时提交周报,我们一起 review。",
          "Q3 增长 30%,转化率达到 12%,辛苦了。",
          "咱们下周二开战略会,大家加油!",
        ]}
      />

      <Card>
        <CardHeader>
          <CardTitle>调优建议</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <p>1) 在 [手动覆盖] 选择你最常用的语气;</p>
          <p>2) 当自动识别与你的直觉不符时,选择「手动覆盖」并保存;</p>
          <p>3) 每次和候选人聊天后,系统会再学习一点点。</p>
        </CardContent>
      </Card>
    </div>
  );
}
