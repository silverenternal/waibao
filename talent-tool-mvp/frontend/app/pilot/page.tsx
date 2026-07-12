"use client";

/**
 * T1702 — /pilot 公开页 (试用入口).
 *
 * - 普通用户视角: 提交 NPS + 主动反馈
 * - 显示当前激活项目 (如果有 token)
 * - 受邀用户从邀请链接落地
 */

import * as React from "react";
import { Rocket, BarChart3, Shield } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { NPSWidget } from "@/components/pilot/NPSWidget";
import { FeedbackDialog } from "@/components/pilot/FeedbackDialog";

export default function PilotPage() {
  const [programId, setProgramId] = React.useState<string | undefined>(undefined);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setProgramId(params.get("program_id") || undefined);
  }, []);

  return (
    <main className="mx-auto max-w-3xl space-y-8 px-4 py-12">
      <header className="space-y-3 text-center">
        <div className="mx-auto inline-flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <Rocket className="size-7" />
        </div>
        <h1 className="text-3xl font-semibold tracking-tight">Pilot 试用计划</h1>
        <p className="mx-auto max-w-xl text-sm text-muted-foreground">
          waibao Pilot 是一个为期 14 天的合作试用.
          我们希望了解您的真实使用体验 — 您的反馈直接影响产品路线图.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <Card className="p-4">
          <BarChart3 className="size-5 text-primary" />
          <h2 className="mt-2 font-semibold">核心指标</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            试用期跟踪 NPS / 周活 / Top 痛点. 目标: NPS ≥ 40, 周活 ≥ 70%.
          </p>
        </Card>
        <Card className="p-4">
          <Shield className="size-5 text-primary" />
          <h2 className="mt-2 font-semibold">数据透明</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            所有反馈匿名汇总,仅产品团队可见. 您随时可撤回.
          </p>
        </Card>
        <Card className="p-4">
          <Rocket className="size-5 text-primary" />
          <h2 className="mt-2 font-semibold">专属支持</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            试用期内 7×24 客户成功经理对接. 严重问题 4 小时内响应.
          </p>
        </Card>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">您愿意向同事推荐 waibao 吗?</h2>
        <NPSWidget programId={programId} featureUsed="pilot_overview" />
      </section>

      <section className="space-y-4 rounded-xl border bg-muted/30 p-6 text-center">
        <h2 className="text-lg font-semibold">有具体的反馈?</h2>
        <p className="text-sm text-muted-foreground">
          Bug / 新功能 / 表扬 — 我们都在听.
        </p>
        <FeedbackDialog programId={programId} />
      </section>

      <footer className="text-center text-xs text-muted-foreground">
        <p>有问题?联系您的客户成功经理或邮件 pilot@waibao.example.</p>
        <Button variant="link" size="sm" {...({ asChild: true } as any)}>
          <a href="/admin/pilot">管理员入口</a>
        </Button>
      </footer>
    </main>
  );
}