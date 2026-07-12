"use client";
/**
 * T1501 - 单个 ATS 集成卡片
 */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface Integration {
  id: string;
  provider: string;
  display_name: string;
  active: boolean;
  last_synced_at: string | null;
  last_status: string | null;
  last_error: string | null;
}

const STATUS_COLOR: Record<string, "default" | "destructive" | "secondary" | "outline"> = {
  ok: "default",
  partial: "secondary",
  failed: "destructive",
  never: "outline",
};

export default function ATSIntegrationCard({ integration }: { integration: Integration }) {
  const status = integration.last_status || "never";
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{integration.display_name}</span>
          <Badge variant={integration.active ? "default" : "secondary"}>
            {integration.active ? "active" : "disabled"}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Provider</span>
          <span>{integration.provider}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">最近状态</span>
          <Badge variant={STATUS_COLOR[status] || "outline"}>{status}</Badge>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">最近同步</span>
          <span className="text-xs">
            {integration.last_synced_at
              ? new Date(integration.last_synced_at).toLocaleString()
              : "从未"}
          </span>
        </div>
        {integration.last_error && (
          <pre className="text-xs bg-red-50 text-red-700 p-2 rounded truncate">
            {integration.last_error}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}
