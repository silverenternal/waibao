"use client";

import * as React from "react";
import { use } from "react";
import Link from "next/link";
import { rulesApi, type BuiltinTrigger, type RuleRow } from "@/lib/api-rules";
import { RuleEditor } from "@/components/rules/RuleEditor";
import { RuleTester } from "@/components/rules/RuleTester";
import { RuleRunHistory } from "@/components/rules/RuleRunHistory";

export default function RuleDetailPage(props: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(props.params);
  const [row, setRow] = React.useState<RuleRow | null>(null);
  const [triggers, setTriggers] = React.useState<BuiltinTrigger[]>([]);
  const [err, setErr] = React.useState<string | null>(null);
  const [tab, setTab] = React.useState<"edit" | "test" | "history">("edit");

  React.useEffect(() => {
    Promise.all([rulesApi.get(id), rulesApi.triggers()])
      .then(([r, tg]) => {
        setRow(r);
        setTriggers(tg.triggers);
      })
      .catch((e) => setErr(e?.message ?? "加载失败"));
  }, [id]);

  if (err)
    return (
      <div className="container mx-auto p-6 max-w-3xl text-red-600">
        错误: {err}
      </div>
    );
  if (!row)
    return <div className="container mx-auto p-6 text-slate-500">加载中...</div>;

  const t = triggers.find((x) => x.name === row.trigger);

  return (
    <div className="container mx-auto p-6 max-w-4xl space-y-4">
      <Link
        href="/mothership/admin/rules"
        className="text-xs text-blue-600 hover:underline"
      >
        ← 返回列表
      </Link>
      <header className="rounded-lg border bg-white p-4">
        <h1 className="text-xl font-semibold">{row.name}</h1>
        <div className="text-xs text-slate-500 mt-1 font-mono">
          {row.trigger}
          {t ? ` — ${t.description}` : ""}
        </div>
      </header>

      <div className="flex gap-1 border-b">
        {(["edit", "test", "history"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-xs font-medium border-b-2 ${
              tab === t
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            {t === "edit" ? "编辑" : t === "test" ? "测试" : "运行历史"}
          </button>
        ))}
      </div>

      {tab === "edit" && (
        <div className="rounded-lg border bg-white p-4">
          <RuleEditor
            triggers={triggers}
            initial={{
              name: row.name,
              description: row.description,
              trigger: row.trigger,
              condition: row.condition,
              actions: row.actions,
              cooldown_seconds: row.cooldown_seconds,
              tags: row.tags,
              enabled: row.enabled,
            }}
            onSubmit={async (body) => {
              await rulesApi.update(row.id, body);
              const fresh = await rulesApi.get(row.id);
              setRow(fresh);
            }}
            submitLabel="保存修改"
          />
        </div>
      )}

      {tab === "test" && (
        <RuleTester
          ruleId={row.id}
          defaultContext={
            (triggers.find((x) => x.name === row.trigger)
              ?.example_context as Record<string, unknown>) ?? {}
          }
        />
      )}

      {tab === "history" && <RuleRunHistory ruleId={row.id} />}
    </div>
  );
}
