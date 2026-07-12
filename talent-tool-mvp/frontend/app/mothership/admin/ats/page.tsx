"use client";
/**
 * T1501 - ATS 集成管理列表 / 配置
 *
 * 功能:
 *  - 列出已绑定的 ATS 集成 (Greenhouse / Lever ...)
 *  - 显示最近同步状态 / 上次错误
 *  - 新建 / 编辑 / 删除集成
 *  - 切换激活状态
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ATSIntegrationCard from "@/components/ATSIntegrationCard";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

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

export default function ATSIntegrationsPage() {
  const [items, setItems] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    provider: "greenhouse",
    display_name: "",
    api_key: "",
    api_base_url: "",
  });

  async function load() {
    setLoading(true);
    try {
      const res = await fetch("/api/ats/integrations");
      const data = await res.json();
      setItems(data || []);
    } catch (e) {
      console.error("Failed to load integrations", e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function create() {
    const res = await fetch("/api/ats/integrations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    if (res.ok) {
      setOpen(false);
      setForm({ provider: "greenhouse", display_name: "", api_key: "", api_base_url: "" });
      await load();
    } else {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "Failed to create integration");
    }
  }

  return (
    <div className="space-y-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">ATS 集成</h1>
          <p className="text-sm text-muted-foreground">
            Greenhouse / Lever 双向同步,每 15 分钟自动拉取并解决冲突。
          </p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger>
            <Button>新建集成</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>新建 ATS 集成</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div>
                <Label>Provider</Label>
                <Select value={form.provider} onValueChange={(v) => setForm({ ...form, provider: typeof v === 'string' ? v : form.provider })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="greenhouse">Greenhouse (Harvest)</SelectItem>
                    <SelectItem value="lever">Lever</SelectItem>
                    <SelectItem value="mock_ats">Mock (开发)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>名称</Label>
                <Input
                  value={form.display_name}
                  onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                  placeholder="生产 - Greenhouse"
                />
              </div>
              <div>
                <Label>API Key</Label>
                <Input
                  type="password"
                  value={form.api_key}
                  onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                />
              </div>
              <div>
                <Label>Base URL (可选)</Label>
                <Input
                  value={form.api_base_url}
                  onChange={(e) => setForm({ ...form, api_base_url: e.target.value })}
                  placeholder="https://harvest.greenhouse.io/v1"
                />
              </div>
              <Button onClick={create} disabled={!form.display_name || !form.api_key}>
                保存
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </header>

      {loading ? (
        <p>加载中...</p>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            暂无 ATS 集成。点击"新建集成"开始绑定 Greenhouse 或 Lever。
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {items.map((it) => (
            <Link key={it.id} href={`/mothership/admin/ats/${it.id}`} className="block">
              <ATSIntegrationCard integration={it} />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
