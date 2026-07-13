"use client";

/**
 * v8.0 T3506 — FeatureGateExamplePage.
 *
 * Concrete illustrations of how to use <FeatureGate> in the four
 * common patterns. Mounted at /admin/feature-gates so PMs can verify
 * the gate behaviour without writing glue code.
 *
 * Pattern A — hard block (hide the button entirely):
 *   <FeatureGate name="api.ai_interview">
 *     <Button>Start AI Interview</Button>
 *   </FeatureGate>
 *
 * Pattern B — fallback (show "upgrade" CTA when blocked):
 *   <FeatureGate name="integration.ats"
 *                fallback={<UpgradeCTA plan="pro" />}>
 *     <ATSImport />
 *   </FeatureGate>
 *
 * Pattern C — showHint mode (render + small enabled chip):
 *   <FeatureGate name="api.copilot" showHint>
 *     <CopilotBubble />
 *   </FeatureGate>
 *
 * Pattern D — imperative hook for non-JSX call sites:
 *   const state = useFeatureGate("api.predictive");
 *   if (state === "disabled") return <EmptyState />;
 *
 * The page itself uses ``useFeatureGate`` directly so the four blocks
 * also act as integration tests: when an admin disables a service in
 * /admin/services, the corresponding block here flips within ~5 s.
 */

import * as React from "react";
import Link from "next/link";
import { FeatureGate, useFeatureGate, GateState } from "@/components/FeatureGate";
import { useServiceDecision } from "@/hooks/use-service-toggle";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const SERVICES: Array<{
  name: string;
  description: string;
  plan?: string;
  role?: string;
}> = [
  {
    name: "api.ai_interview",
    description: "GPT-4o powered interview.",
    plan: "pro",
    role: "employer",
  },
  {
    name: "integration.ats",
    description: "Greenhouse / Lever sync.",
    plan: "enterprise",
    role: "employer",
  },
  {
    name: "api.copilot",
    description: "Q&A copilot (always-on free).",
    plan: "free",
  },
  {
    name: "analytics.predictive",
    description: "LightGBM attrition forecast.",
    plan: "enterprise",
    role: "employer",
  },
];

interface ServiceCardProps {
  name: string;
  description: string;
}

function ServiceStatusCard({ name, description }: ServiceCardProps) {
  const decision = useServiceDecision(name);
  const status = decision?.status || "missing";
  const available = decision?.available ?? false;
  const planRequired = decision?.plan_required || "free";

  return (
    <Card className="w-full max-w-md" data-testid={`svc-${name}`}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="text-sm font-mono">{name}</span>
          <Badge
            variant={
              available
                ? "default"
                : status === "missing"
                ? "secondary"
                : "destructive"
            }
          >
            {available ? "enabled" : status}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-slate-600">{description}</p>
        <p className="text-xs text-slate-400 mt-2">requires {planRequired}</p>
      </CardContent>
    </Card>
  );
}

function UpgradeHint({ plan }: { plan: string }) {
  return (
    <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm">
      该功能需要升级到 <b>{plan}</b> 计划 — 立即联系 CSM。
    </div>
  );
}

export function FeatureGateShowcase(): React.ReactElement {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <section>
        <h2 className="text-lg font-bold mb-2">模式 A — 硬隐藏</h2>
        {SERVICES.map((s) => (
          <FeatureGate key={s.name} name={s.name} plan={s.plan} role={s.role}>
            <Button data-testid={`btn-${s.name}`}>{s.description}</Button>
          </FeatureGate>
        ))}
      </section>

      <section>
        <h2 className="text-lg font-bold mb-2">模式 B — 降级 CTA</h2>
        {SERVICES.map((s) => (
          <div key={s.name} className="mb-2">
            <FeatureGate
              name={s.name}
              plan={s.plan}
              role={s.role}
              fallback={<UpgradeHint plan={s.plan || "pro"} />}
            >
              <span className="text-green-700 font-mono">已开通: {s.name}</span>
            </FeatureGate>
          </div>
        ))}
      </section>

      <section>
        <h2 className="text-lg font-bold mb-2">模式 C — 显示 + 标签</h2>
        {SERVICES.map((s) => (
          <FeatureGate key={s.name} name={s.name} plan={s.plan} showHint>
            <span className="text-blue-700 font-mono">{s.name}</span>
          </FeatureGate>
        ))}
      </section>

      <section>
        <h2 className="text-lg font-bold mb-2">服务状态卡</h2>
        {SERVICES.map((s) => (
          <ServiceStatusCard key={s.name} name={s.name} description={s.description} />
        ))}
      </section>

      <section className="lg:col-span-2">
        <h2 className="text-lg font-bold mb-2">模式 D — Hook 形式</h2>
        <HookUsageExample />
      </section>

      <section className="lg:col-span-2 text-sm text-slate-500">
        <Link href="/admin/services" className="underline">
          /admin/services
        </Link>{" "}
        可修改这里展示的服务开关。
      </section>
    </div>
  );
}

function HookUsageExample(): React.ReactElement {
  const state: GateState = useFeatureGate("api.copilot", {
    plan: "free",
    role: "jobseeker",
  });
  return (
    <div className="rounded-md bg-slate-100 p-3 font-mono text-xs">
      <pre>{`const state = useFeatureGate("api.copilot", { plan: "free" });
// state -> ${state}`}</pre>
    </div>
  );
}

export default FeatureGateShowcase;
