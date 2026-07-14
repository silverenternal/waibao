"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";
/**
 * T1501 - ATS 集成详情页 (单个 integration)
 *
 *  - 显示配置 + 最近同步详情
 *  - "立即同步" 按钮触发 sync-now
 *  - 链接到同步历史 / 冲突页
 */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import ATSSyncStatus from "@/components/ATSSyncStatus";
import ATSConflictResolver from "@/components/ATSConflictResolver";

interface Integration {
  id: string;
  provider: string;
  display_name: string;
  active: boolean;
  last_synced_at: string | null;
  last_status: string | null;
  last_error: string | null;
  api_base_url: string | null;
}

interface SyncOutcome {
  candidates: { status: string; succeeded: number; failed: number; conflicts: number };
  jobs: { status: string; succeeded: number; failed: number; conflicts: number };
}

export default function ATSIntegrationDetailPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const [item, setItem] = useState<Integration | null>(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<SyncOutcome | null>(null);
  const [conflicts, setConflicts] = useState<any[]>([]);

  async function load() {
    const res = await fetch(`/api/ats/integrations/${params.id}`);
    if (!res.ok) {
      router.push("/mothership/admin/ats");
      return;
    }
    setItem(await res.json());
    const cr = await fetch(`/api/ats/integrations/${params.id}/conflicts`);
    if (cr.ok) {
      setConflicts(await cr.json());
    }
  }

  useEffect(() => {
    load();
  }, [params.id]);

  async function triggerSync() {
    setBusy(true);
    setOutcome(null);
    try {
      const res = await fetch(`/api/ats/integrations/${params.id}/sync-now`, { method: "POST" });
      if (res.ok) {
        setOutcome(await res.json());
        await load();
      } else {
        alert("同步失败,请检查网络与 API Key");
      }
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm("确定删除此集成?历史日志会保留。")) return;
    const res = await fetch(`/api/ats/integrations/${params.id}`, { method: "DELETE" });
    if (res.ok) router.push("/mothership/admin/ats");
  }

  if (!item) return <p className="p-6">加载中...</p>;

  return (
    <ErrorBoundary>(<div className="space-y-6 p-6">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">{item.display_name}</h1>
            <p className="text-sm text-muted-foreground">Provider: {item.provider}</p>
          </div>
          <div className="flex gap-2">
            <Link href={`/mothership/admin/ats/${item.id}/history`}>
              <Button variant="outline">同步历史</Button>
            </Link>
            <Button onClick={triggerSync} disabled={busy}>
              {busy ? "同步中..." : "立即同步"}
            </Button>
            <Button variant="destructive" onClick={remove}>删除</Button>
          </div>
        </header>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardHeader><CardTitle>状态</CardTitle></CardHeader>
            <CardContent>
              <ATSSyncStatus
                status={item.last_status || "never"}
                lastSyncedAt={item.last_synced_at}
                lastError={item.last_error}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Base URL</CardTitle></CardHeader>
            <CardContent>
              <code className="text-xs">{item.api_base_url || "(默认)"}</code>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>激活</CardTitle></CardHeader>
            <CardContent>
              <Badge variant={item.active ? "default" : "secondary"}>
                {item.active ? "active" : "disabled"}
              </Badge>
            </CardContent>
          </Card>
        </div>
        {outcome && (
          <Card>
            <CardHeader><CardTitle>同步结果</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="font-medium">候选人</div>
                  <div>status: {outcome.candidates.status}</div>
                  <div>succeeded: {outcome.candidates.succeeded}</div>
                  <div>failed: {outcome.candidates.failed}</div>
                  <div>conflicts: {outcome.candidates.conflicts}</div>
                </div>
                <div>
                  <div className="font-medium">职位</div>
                  <div>status: {outcome.jobs.status}</div>
                  <div>succeeded: {outcome.jobs.succeeded}</div>
                  <div>failed: {outcome.jobs.failed}</div>
                  <div>conflicts: {outcome.jobs.conflicts}</div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
        <Card>
          <CardHeader>
            <CardTitle>未解决冲突</CardTitle>
          </CardHeader>
          <CardContent>
            <ATSConflictResolver
              integrationId={item.id}
              conflicts={conflicts}
              onResolved={load}
            />
          </CardContent>
        </Card>
      </div>)</ErrorBoundary>
  );
}
